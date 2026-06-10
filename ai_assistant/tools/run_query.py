#!/usr/bin/env python3
"""
Cross-platform query runner for DevOps monitoring.
Executes ELK (Elasticsearch) and Prometheus queries from YAML definitions.

Usage:
    python tools/run_query.py --project meinvoice --section errors
    python tools/run_query.py --project meinvoice --section alerts --time-range now-30m
    python tools/run_query.py --project meinvoice --section errors --output pretty
"""

import argparse
import json
import os
import sys
import yaml
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("[ERROR] Missing dependency: run `pip install -r requirements.txt`", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(project: str) -> dict:
    global_cfg = yaml.safe_load((ROOT / "config" / "global.yaml").read_text("utf-8"))

    p_path = ROOT / "projects" / project / "config.yaml"
    if not p_path.exists():
        print(f"[WARN] No config found for project '{project}', using global defaults", file=sys.stderr)
        project_cfg = {"project": project}
    else:
        project_cfg = yaml.safe_load(p_path.read_text("utf-8"))

    # Merge sources: global + project (respects inherit flag)
    g_sources = global_cfg.get("sources", {})
    p_sources = project_cfg.get("sources", {})
    merged_sources = dict(g_sources)
    for src_type, src_def in p_sources.items():
        if isinstance(src_def, dict):
            inherit = src_def.get("inherit", True)
            extra = src_def.get("extra", [])
            base = g_sources.get(src_type, []) if inherit else []
            merged_sources[src_type] = base + extra
        else:
            merged_sources[src_type] = src_def

    # Merge query vars: global defaults < project overrides
    g_vars = dict(global_cfg.get("defaults", {}))
    p_vars = project_cfg.get("query_vars", {})

    result = {**global_cfg, **project_cfg}
    result["sources"] = merged_sources
    result["query_vars"] = {**g_vars, **p_vars}
    return result


# ---------------------------------------------------------------------------
# Query definition loading
# ---------------------------------------------------------------------------

def load_query_def(project: str, section: str) -> dict:
    """Project override takes priority over common."""
    candidates = [
        ROOT / "projects" / project / "queries" / f"{section}.yaml",
        ROOT / "queries" / "common" / f"{section}.yaml",
    ]
    for path in candidates:
        if path.exists():
            return yaml.safe_load(path.read_text("utf-8"))
    raise FileNotFoundError(
        f"No query definition found for section '{section}'. "
        f"Checked: {[str(p) for p in candidates]}"
    )


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render(template: str, vars_: dict) -> str:
    """Replace {{ key }} placeholders. Missing keys become empty string."""
    result = template
    for k, v in vars_.items():
        result = result.replace("{{ " + k + " }}", str(v) if v is not None else "")
    return result


# ---------------------------------------------------------------------------
# HTTP execution
# ---------------------------------------------------------------------------

def _auth_headers(auth_env: str | None) -> dict:
    if not auth_env:
        return {}
    val = os.environ.get(auth_env, "")
    return {"Authorization": f"Basic {val}"} if val else {}


def query_elk(source: dict, body: dict, timeout: int) -> dict:
    url = f"{source['url']}/{source.get('index', '*')}/_search"
    headers = {"Content-Type": "application/json", **_auth_headers(source.get("auth_env"))}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
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


def query_prometheus(source: dict, promql: str, timeout: int) -> dict:
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
# Section runner
# ---------------------------------------------------------------------------

def run_section(config: dict, section: str, time_range_override: str | None) -> dict:
    project = config.get("project", "unknown")
    qdef = load_query_def(project, section)

    vars_ = dict(config.get("query_vars", {}))
    if time_range_override:
        vars_["time_range"] = time_range_override

    # Computed convenience vars
    namespace = config.get("namespace", "")
    vars_.setdefault("namespace", namespace)
    # namespace_filter: dùng BÊN TRONG {} có sẵn, vd {phase!="x"{{ namespace_filter }}}
    vars_["namespace_filter"] = f', namespace="{namespace}"' if namespace else ""
    # namespace_selector: dùng khi metric KHÔNG có label nào khác, vd metric{{ namespace_selector }}[1h]
    vars_["namespace_selector"] = f'{{namespace="{namespace}"}}' if namespace else ""

    node_job = config.get("node_job", "")
    vars_["node_filter"] = f', job="{node_job}"' if node_job else ""

    # prom_range: range duration cho Prometheus subquery (bỏ "now-" prefix)
    # "now-2h" → "2h", "now-30m" → "30m"
    tr = vars_.get("time_range", "now-1h")
    vars_["prom_range"] = tr.replace("now-", "") if tr.startswith("now-") else tr

    vars_.setdefault("project_filter", "")
    # apm_filter: APM-specific filter (labels.app_id + service.name).
    # Falls back to project_filter if not explicitly set in project config.
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
        if qtype == "elk":
            body_str = render(qdef["elk_body_template"], vars_)
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError as e:
                return {"status": "template_error", "source": source["name"], "error": str(e), "data": None}
            return query_elk(source, body, timeout)

        elif qtype == "prometheus":
            # Support single promql_template or multiple queries[]
            if "queries" in qdef:
                sub_results = []
                for q in qdef["queries"]:
                    promql = render(q["promql_template"], vars_)
                    res = query_prometheus(source, promql, timeout)
                    res["query_id"] = q["id"]
                    sub_results.append(res)
                return {"source": source["name"], "sub_queries": sub_results}
            else:
                promql = render(qdef["promql_template"], vars_)
                return query_prometheus(source, promql, timeout)

        return {"status": "unknown_query_type", "source": source["name"], "data": None}

    workers = min(len(all_sources), 8)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(execute, src) for src in all_sources]
        results = [f.result() for f in as_completed(futures)]

    return {"section": section, "results": results}


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
    args = parser.parse_args()

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
