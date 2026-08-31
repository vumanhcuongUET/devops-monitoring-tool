#!/usr/bin/env python3
"""
Cross-platform query runner for DevOps monitoring.
Executes ELK (Elasticsearch) and Prometheus queries from YAML definitions.

Usage:
    python tools/run_query.py --project meinvoice --section errors
    python tools/run_query.py --project meinvoice --section alerts --time-range now-30m
    python tools/run_query.py --project meinvoice --section errors --output pretty
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("[ERROR] Missing dependency: run `pip install -r requirements.txt`", file=sys.stderr)
    sys.exit(1)

# Add core module to path for imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config_loader import (
    load_config,
    load_query_def,
    render_template,
    is_feature_enabled
)
from core.logging_config import (
    setup_logging,
    track_time,
    get_metrics
)
from core.audit import get_audit_logger, AuditLogEntry
from core.cache import cached, get_cache_stats
from core.single_flight import single_flight
from core.output_optimizer import get_output_optimizer

# Setup logging
_logger = setup_logging()


# ---------------------------------------------------------------------------
# HTTP execution
# ---------------------------------------------------------------------------

def _auth_headers(auth_env: str | None) -> dict:
    """Get authorization headers from environment variable."""
    if not auth_env:
        return {}
    val = os.environ.get(auth_env, "")
    return {"Authorization": f"Basic {val}"} if val else {}


def query_elk_http(source: dict, body: dict, timeout: int) -> dict:
    """
    Execute Elasticsearch query via direct HTTP (fallback method).

    Args:
        source: Source configuration with url, index, auth_env
        body: Elasticsearch query body
        timeout: Request timeout in seconds

    Returns:
        Result dict with status, source, and data
    """
    import time
    start_time = time.time()
    source_name = source.get("name", "unknown")

    _logger.debug("Executing ELK HTTP query", extra={"source": source_name, "index": source.get("index")})

    # Validate URL before using it
    from core.security import InputValidator
    source_url = source.get('url', '')
    is_valid, error = InputValidator.validate_url(source_url, allow_credentials=True)
    if not is_valid:
        _logger.error("Invalid source URL", extra={"source": source_name, "error": error})
        return {"status": "error", "source": source["name"], "error": f"Invalid URL: {error}", "data": None}

    url = f"{source['url']}/{source.get('index', '*')}/_search"
    headers = {"Content-Type": "application/json", **_auth_headers(source.get("auth_env"))}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()

        duration = time.time() - start_time
        get_metrics().observe("elk_http_query_duration_seconds", duration,
                             {"source": source_name, "status": "ok"})
        get_metrics().increment("elk_http_query_total", labels={"source": source_name, "status": "ok"})

        _logger.info("ELK HTTP query successful", extra={"source": source_name, "duration": duration})

        return {"status": "ok", "source": source["name"], "data": resp.json()}
    except requests.exceptions.ConnectionError as e:
        duration = time.time() - start_time
        get_metrics().observe("elk_http_query_duration_seconds", duration,
                             {"source": source_name, "status": "error"})
        get_metrics().increment("elk_http_query_total", labels={"source": source_name, "status": "connection_error"})
        _logger.warning("ELK HTTP query connection error", extra={"source": source_name, "error": str(e)})
        return {"status": "unreachable", "source": source["name"], "data": None}
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        get_metrics().observe("elk_http_query_duration_seconds", duration,
                             {"source": source_name, "status": "timeout"})
        get_metrics().increment("elk_http_query_total", labels={"source": source_name, "status": "timeout"})
        _logger.warning("ELK HTTP query timeout", extra={"source": source_name})
        return {"status": "timeout", "source": source["name"], "data": None}
    except requests.exceptions.HTTPError as e:
        duration = time.time() - start_time
        get_metrics().observe("elk_http_query_duration_seconds", duration,
                             {"source": source_name, "status": "http_error"})
        get_metrics().increment("elk_http_query_total", labels={"source": source_name, "status": f"http_{e.response.status_code}"})
        _logger.error("ELK HTTP query HTTP error", extra={"source": source_name, "status_code": e.response.status_code})
        return {"status": f"http_{e.response.status_code}", "source": source["name"], "data": None}
    except Exception as e:
        duration = time.time() - start_time
        get_metrics().observe("elk_http_query_duration_seconds", duration,
                             {"source": source_name, "status": "error"})
        get_metrics().increment("elk_http_query_total", labels={"source": source_name, "status": "error"})
        _logger.error("ELK HTTP query unexpected error", extra={"source": source_name, "error": str(e)})
        return {"status": "error", "source": source["name"], "error": str(e), "data": None}


def query_prometheus_http(source: dict, promql: str, timeout: int) -> dict:
    """
    Execute Prometheus query via direct HTTP (fallback method).

    Args:
        source: Source configuration with url and auth_env
        promql: PromQL query string
        timeout: Request timeout in seconds

    Returns:
        Result dict with status, source, and data
    """
    # Validate URL before using it
    from core.security import InputValidator
    source_url = source.get('url', '')
    is_valid, error = InputValidator.validate_url(source_url, allow_credentials=True)
    if not is_valid:
        _logger.error("Invalid source URL", extra={"source": source.get("name"), "error": error})
        return {"status": "error", "source": source["name"], "error": f"Invalid URL: {error}", "data": None}

    headers = _auth_headers(source.get("auth_env"))
    try:
        resp = requests.get(
            f"{source['url']}/api/v1/query",
            headers=headers,
            params={"query": promql},
            timeout=timeout,
        )
        resp.raise_for_status()
        return {"status": "ok", "source": source["name"], "data": resp.json()}
    except requests.exceptions.ConnectionError:
        return {"status": "unreachable", "source": source["name"], "data": None}
    except requests.exceptions.Timeout:
        return {"status": "timeout", "source": source["name"], "data": None}
    except requests.exceptions.HTTPError as e:
        return {"status": f"http_{e.response.status_code}", "source": source["name"], "data": None}
    except Exception as e:
        return {"status": "error", "source": source["name"], "error": str(e), "data": None}


# ---------------------------------------------------------------------------
# Query execution dispatcher
# ---------------------------------------------------------------------------

@single_flight(lambda source, body, timeout: f"elk:{source.get('name')}:{hash(str(body))}")
def execute_elk_query(source: dict, body: dict, timeout: int) -> dict:
    """
    Execute Elasticsearch query via direct HTTP.

    Concurrent requests with same source+body will deduplicate.

    Args:
        source: Source configuration
        body: Query body
        timeout: Timeout in seconds

    Returns:
        Result dictionary
    """
    source_name = source.get("name", "unknown")

    # Log query start
    audit_logger = get_audit_logger()
    audit_logger.log(AuditLogEntry(
        event_type="query",
        action="execute_elk_query",
        resource=source_name,
        details={"timeout": timeout},
    ))

    result = query_elk_http(source, body, timeout)

    # Log query completion
    audit_logger.log(AuditLogEntry(
        event_type="query_result",
        action="execute_elk_query",
        resource=source_name,
        status=result.get("status", "unknown"),
        details={"result_sources": 1 if result.get("data") else 0},
    ))

    return result


@single_flight(lambda source, promql, timeout: f"prom:{source.get('name')}:{hash(promql)}")
def execute_prometheus_query(source: dict, promql: str, timeout: int) -> dict:
    """
    Execute Prometheus query via direct HTTP.

    Concurrent requests with same source+promql will deduplicate.

    Args:
        source: Source configuration
        promql: PromQL query string
        timeout: Timeout in seconds

    Returns:
        Result dictionary
    """
    source_name = source.get("name", "unknown")

    # Log query start
    audit_logger = get_audit_logger()
    audit_logger.log(AuditLogEntry(
        event_type="query",
        action="execute_prometheus_query",
        resource=source_name,
        details={"timeout": timeout},
    ))

    result = query_prometheus_http(source, promql, timeout)

    # Log query completion
    audit_logger.log(AuditLogEntry(
        event_type="query_result",
        action="execute_prometheus_query",
        resource=source_name,
        status=result.get("status", "unknown"),
        details={"result_sources": 1 if result.get("data") else 0},
    ))

    return result


# ---------------------------------------------------------------------------
# Section runner
# ---------------------------------------------------------------------------

@cached(ttl=60)  # 60-second cache for query results
@track_time("query_section_duration", {"section": "args[1]"})
def run_section(config: dict, section: str, time_range_override: str | None) -> dict:
    """
    Execute a query section using configured sources.

    Results are cached for 60 seconds to reduce duplicate queries.
    Different time_range_override values result in separate cache entries.

    Args:
        config: Merged project configuration
        section: Query section identifier (e.g., 'errors', 'alerts')
        time_range_override: Optional time range override

    Returns:
        Result dictionary with section and results
    """
    project = config.get("project", "unknown")
    qdef = load_query_def(project, section)

    vars_ = dict(config.get("query_vars", {}))
    if time_range_override:
        vars_["time_range"] = time_range_override

    # Computed convenience vars
    namespace = config.get("namespace", "")
    vars_.setdefault("namespace", namespace)
    vars_["namespace_filter"] = f', namespace="{namespace}"' if namespace else ""
    vars_["namespace_selector"] = f'{{namespace="{namespace}"}}' if namespace else ""

    node_job = config.get("node_job", "")
    vars_["node_filter"] = f', job="{node_job}"' if node_job else ""

    # prom_range: range duration for Prometheus subquery
    tr = vars_.get("time_range", "now-1h")
    vars_["prom_range"] = tr.replace("now-", "") if tr.startswith("now-") else tr

    vars_.setdefault("project_filter", "")
    if "apm_filter" not in vars_:
        vars_["apm_filter"] = vars_.get("project_filter", "")

    vars_.setdefault("max_results", 10)
    timeout = int(vars_.get("timeout_seconds", 10))

    # Collect sources
    source_types = qdef.get("source_types", [])
    sources_map = config.get("sources", {})
    all_sources = []
    for st in source_types:
        all_sources.extend(sources_map.get(st, []))

    if not all_sources:
        return {"section": section, "warning": f"No sources configured for types: {source_types}", "results": []}

    qtype = qdef.get("type", "elk")

    def execute(source: dict) -> dict:
        """Execute query against a single source."""
        if qtype == "elk":
            template = qdef.get("elk_body_template", "")
            # Validate template content
            from core.security import InputValidator
            is_valid, error = InputValidator.validate_template_content(template)
            if not is_valid:
                _logger.error("Invalid ELK template", extra={"source": source["name"], "error": error})
                return {"status": "template_error", "source": source["name"], "error": f"Invalid template: {error}", "data": None}

            # Phase 15 P2-13: a missing template var is a loud config error,
            # not a silently-widened query.
            try:
                body_str = render_template(template, vars_)
            except KeyError as e:
                _logger.error("Missing template variable", extra={"source": source["name"], "error": str(e)})
                return {"status": "template_error", "source": source["name"], "error": str(e), "data": None}
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError as e:
                return {"status": "template_error", "source": source["name"], "error": str(e), "data": None}
            return execute_elk_query(source, body, timeout)

        elif qtype == "prometheus":
            if "queries" in qdef:
                sub_results = []
                for q in qdef["queries"]:
                    template = q.get("promql_template", "")
                    # Validate template content
                    from core.security import InputValidator
                    is_valid, error = InputValidator.validate_template_content(template, max_length=2000)
                    if not is_valid:
                        _logger.error("Invalid PromQL template", extra={"source": source["name"], "error": error})
                        return {"status": "template_error", "source": source["name"], "error": f"Invalid template: {error}", "data": None}
                    try:
                        promql = render_template(template, vars_)
                    except KeyError as e:
                        _logger.error("Missing template variable", extra={"source": source["name"], "error": str(e)})
                        return {"status": "template_error", "source": source["name"], "error": str(e), "data": None}
                    res = execute_prometheus_query(source, promql, timeout)
                    res["query_id"] = q["id"]
                    sub_results.append(res)
                return {"source": source["name"], "sub_queries": sub_results}
            else:
                template = qdef.get("promql_template", "")
                # Validate template content
                from core.security import InputValidator
                is_valid, error = InputValidator.validate_template_content(template, max_length=2000)
                if not is_valid:
                    _logger.error("Invalid PromQL template", extra={"source": source["name"], "error": error})
                    return {"status": "template_error", "source": source["name"], "error": f"Invalid template: {error}", "data": None}
                try:
                    promql = render_template(template, vars_)
                except KeyError as e:
                    _logger.error("Missing template variable", extra={"source": source["name"], "error": str(e)})
                    return {"status": "template_error", "source": source["name"], "error": str(e), "data": None}
                return execute_prometheus_query(source, promql, timeout)

        return {"status": "unknown_query_type", "source": source["name"], "data": None}

    # Parallel execution
    max_workers = vars_.get("max_parallel_workers", 8)
    if is_feature_enabled("optimization.parallel_queries"):
        workers = min(len(all_sources), max_workers)
    else:
        workers = 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(execute, src) for src in all_sources]
        results = [f.result() for f in as_completed(futures)]

    result = {"section": section, "results": results}

    # Apply output optimization if enabled
    if is_feature_enabled("output.truncate_results"):
        optimizer = get_output_optimizer()
        result = optimizer.optimize_section(result)

        # Log token estimate
        original_tokens = optimizer.estimate_tokens({"section": section, "results": results})
        optimized_tokens = optimizer.estimate_tokens(result)
        if original_tokens > 0:
            savings = original_tokens - optimized_tokens
            savings_percent = (savings / original_tokens * 100) if original_tokens > 0 else 0
            _logger.info("Output optimization applied",
                        extra={"section": section,
                               "original_tokens": original_tokens,
                               "optimized_tokens": optimized_tokens,
                               "savings": savings,
                               "savings_percent": f"{savings_percent:.1f}%"})

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DevOps AI Monitoring Query Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--project", required=True, help="Project name (must exist in projects/)")
    parser.add_argument("--section", required=True,
                        help="Query section: alerts | errors | slow_endpoints | disk_usage | pod_status")
    parser.add_argument("--time-range", default=None, help="Override time range, e.g. now-30m, now-2h")
    parser.add_argument("--output", choices=["json", "pretty"], default="pretty",
                        help="Output format (default: pretty)")
    parser.add_argument("--reload-features", action="store_true",
                        help="Force reload feature flags from disk")
    parser.add_argument("--show-cache-stats", action="store_true",
                        help="Show cache statistics and exit")
    parser.add_argument("--show-optimization-stats", action="store_true",
                        help="Show all optimization statistics (cache, single-flight) and exit")
    args = parser.parse_args()

    # Validate inputs using InputValidator
    from core.security import InputValidator

    # Validate project name
    is_valid, error = InputValidator.validate_project_name(args.project)
    if not is_valid:
        print(json.dumps({"error": f"Invalid project name: {error}"}))
        sys.exit(1)

    # Validate section name
    is_valid, error = InputValidator.validate_section_name(args.section)
    if not is_valid:
        print(json.dumps({"error": f"Invalid section name: {error}"}))
        sys.exit(1)

    # Validate time range if provided
    if args.time_range:
        is_valid, error = InputValidator.validate_time_range(args.time_range)
        if not is_valid:
            print(json.dumps({"error": f"Invalid time range: {error}"}))
            sys.exit(1)

    # Reload feature flags if requested
    if args.reload_features:
        from core.config_loader import reload_feature_flags
        reload_feature_flags()

    # Show cache statistics if requested
    if args.show_cache_stats:
        stats = get_cache_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Show all optimization statistics if requested
    if args.show_optimization_stats:
        from core.single_flight import get_single_flight_stats

        cache_stats = get_cache_stats()
        sf_stats = get_single_flight_stats()

        # Calculate hit rate if possible
        _hit_count = cache_stats.get("size", 0)  # Approximate
        optimization_stats = {
            "cache": cache_stats,
            "single_flight": sf_stats,
            "summary": {
                "caching_enabled": is_feature_enabled("optimization.cache_enabled"),
                "deduplication_enabled": is_feature_enabled("optimization.deduplication_enabled"),
                "parallel_queries_enabled": is_feature_enabled("optimization.parallel_queries"),
            }
        }
        print(json.dumps(optimization_stats, indent=2, ensure_ascii=False))
        sys.exit(0)

    try:
        config = load_config(args.project)
        result = run_section(config, args.section, args.time_range)
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    indent = 2 if args.output == "pretty" else None
    print(json.dumps(result, indent=indent, ensure_ascii=False))


if __name__ == "__main__":
    main()
