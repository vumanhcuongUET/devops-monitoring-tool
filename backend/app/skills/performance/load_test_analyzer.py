"""Performance Load Test Analyzer Skill - parse real k6/Locust artifacts.

Phase 14 (stub -> real, same precedent as the dockerfile/kubernetes static
linters): the skill analyzes UPLOADED load-test artifacts with stdlib json
only. No number is invented — whatever the artifact does not contain is
reported as missing, and unparseable input is refused with an error rather
than guessed at.

Supported artifact shapes:

- k6 summary export (``k6 run --summary-export=``): top-level ``metrics``
  object; ``http_req_duration`` percentiles (``med``/``p(95)``/``p(99)``),
  ``http_reqs`` count/rate and ``http_req_failed`` rate form the aggregate
  entry, tagged duration sub-metrics (``http_req_duration{...}``) become
  per-endpoint entries when present.
- k6 raw JSON export (``k6 run --out=json=``): newline-delimited points;
  per-endpoint percentiles are computed from the actual ``http_req_duration``
  samples (linear interpolation), failures from status/expected_response
  tags, throughput from the point-time span.
- Locust stats JSON (``locust --json`` / web UI ``/stats/requests`` and
  variants): entries keyed by ``name``/``method`` with request/failure counts
  and response-time percentiles under several naming conventions
  (``Median``/``95%``/``99%``, ``median_response_time``/
  ``ninety_fifth_response_time``, CSV-style ``95%tile (ms)``).

Pass criteria (reported, never fabricated): failure rate > 1% or p95 above
``p95_threshold_ms`` (default 500). Against a baseline artifact, a p95
delta above +10% is a regression.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillPriority,
)

# Flag thresholds (kept as constants so tests/recommendations agree)
FAILURE_RATE_FLAG_PERCENT = 1.0
BASELINE_REGRESSION_PERCENT = 10.0

# Locust stat-entry key aliases across versions/export styles
_REQUESTS_KEYS = ("num_requests", "# Requests", "request_count")
_FAILURES_KEYS = ("num_failures", "# Fails", "failure_count")
_P50_KEYS = ("Median", "median_response_time", "Median (ms)")
_P95_KEYS = ("95%", "95%tile", "95%tile (ms)", "ninety_fifth_response_time")
_P99_KEYS = ("99%", "99%tile", "99%tile (ms)", "ninety_ninth_response_time")
_RPS_KEYS = ("current_rps", "Req/s", "rps")
_AGGREGATE_NAMES = {"Total", "Aggregated", "total", "aggregated"}


class _Unparseable(Exception):
    """Raised when an artifact does not match any supported shape."""


def _num(value: object) -> float | None:
    """Return value as float when it is a real number, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _first_number(entry: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        number = _num(entry.get(key))
        if number is not None:
            return number
    return None


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile over a pre-sorted sample list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[int(rank)]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (rank - low)


def _point_timestamp(value: object) -> float | None:
    """Parse a k6 point timestamp (RFC3339 string) to epoch seconds."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _endpoint(
    name: str,
    method: str | None,
    *,
    aggregate: bool = False,
    num_requests: float | None = None,
    num_failures: float | None = None,
    p50_ms: float | None = None,
    p95_ms: float | None = None,
    p99_ms: float | None = None,
    rps: float | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "method": method,
        "aggregate": aggregate,
        "num_requests": num_requests,
        "num_failures": num_failures,
        "failure_rate_percent": None,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "p99_ms": p99_ms,
        "rps": rps,
        "flagged": False,
        "reasons": [],
    }


def _finish_rates(endpoints: list[dict[str, Any]]) -> None:
    """Derive failure rates where both counts exist."""
    for ep in endpoints:
        if ep["num_requests"] and ep["num_failures"] is not None:
            ep["failure_rate_percent"] = round(
                ep["num_failures"] / ep["num_requests"] * 100.0, 3
            )
        elif ep["num_requests"] == 0:
            ep["failure_rate_percent"] = 0.0


def _parse_k6_summary(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a k6 summary-export document (``metrics`` object with values)."""
    metrics = doc.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise _Unparseable("k6 summary export needs a non-empty 'metrics' object")

    endpoints: list[dict[str, Any]] = []
    for metric_name, metric in metrics.items():
        if not isinstance(metric, dict) or not isinstance(metric.get("values"), dict):
            continue
        values = metric["values"]
        base, _, tag = str(metric_name).partition("{")
        if base != "http_req_duration":
            continue
        name = tag.rstrip("}") or "overall"
        endpoints.append(_endpoint(
            name=name,
            method=None,
            aggregate=name == "overall",
            p50_ms=_num(values.get("med")),
            p95_ms=_num(values.get("p(95)")),
            p99_ms=_num(values.get("p(99)")),
        ))

    # Attach aggregate request/failure counts to the overall duration entry
    overall = next((e for e in endpoints if e["aggregate"]), None)
    if overall is None:
        overall = _endpoint("overall", None, aggregate=True)
        endpoints.insert(0, overall)

    req_values = metrics.get("http_reqs")
    if isinstance(req_values, dict) and isinstance(req_values.get("values"), dict):
        overall["num_requests"] = _num(req_values["values"].get("count"))
        overall["rps"] = _num(req_values["values"].get("rate"))

    failed_values = metrics.get("http_req_failed")
    if isinstance(failed_values, dict) and isinstance(failed_values.get("values"), dict):
        values = failed_values["values"]
        passes, fails = _num(values.get("passes")), _num(values.get("fails"))
        if passes is not None and fails is not None:
            overall["num_failures"] = fails
        else:
            rate = _num(values.get("value"))
            if rate is not None and overall["num_requests"]:
                overall["num_failures"] = rate * overall["num_requests"]

    if len(endpoints) == 1 and overall["p95_ms"] is None and overall["p50_ms"] is None:
        raise _Unparseable("'metrics' has no http_req_duration values")

    _finish_rates(endpoints)
    return endpoints


def _parse_k6_raw(text: str) -> list[dict[str, Any]]:
    """Parse k6 raw JSON output (newline-delimited points) — per-endpoint
    stats are computed from the actual samples."""
    durations: dict[tuple[str, str | None], list[tuple[float, str | None]]] = {}
    request_counts: dict[tuple[str, str | None], int] = {}
    time_spans: dict[tuple[str, str | None], tuple[float, float]] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            point = json.loads(line)
        except ValueError:
            continue  # k6 interleaves non-JSON progress lines
        if not isinstance(point, dict) or not isinstance(point.get("data"), dict):
            continue

        data = point["data"]
        tags = data.get("tags") if isinstance(data.get("tags"), dict) else {}
        key = (str(tags.get("name") or "overall"), tags.get("method"))
        value = _num(data.get("value"))
        if value is None:
            continue

        if point.get("metric") == "http_req_duration":
            status = _num(tags.get("status"))
            failed = status is not None and status >= 400
            failed = failed or tags.get("expected_response") == "false"
            durations.setdefault(key, []).append((value, "fail" if failed else "ok"))
            timestamp = _point_timestamp(data.get("time"))
            if timestamp is not None:
                lo, hi = time_spans.get(key, (timestamp, timestamp))
                time_spans[key] = (min(lo, timestamp), max(hi, timestamp))
        elif point.get("metric") == "http_reqs":
            request_counts[key] = request_counts.get(key, 0) + int(value)

    if not durations:
        raise _Unparseable("no http_req_duration points found in k6 raw output")

    endpoints: list[dict[str, Any]] = []
    for (name, method), samples in durations.items():
        values = sorted(sample[0] for sample in samples)
        num_requests = request_counts.get((name, method), len(samples))
        num_failures = sum(1 for _, outcome in samples if outcome == "fail")
        span = time_spans.get((name, method))
        rps = num_requests / (span[1] - span[0]) if span and span[1] > span[0] else None
        endpoints.append(_endpoint(
            name=name,
            method=method,
            aggregate=name == "overall" and method is None,
            num_requests=num_requests,
            num_failures=num_failures,
            p50_ms=_percentile(values, 50),
            p95_ms=_percentile(values, 95),
            p99_ms=_percentile(values, 99),
            rps=rps,
        ))

    _finish_rates(endpoints)
    return endpoints


def _parse_locust(doc: Any) -> list[dict[str, Any]]:
    """Parse Locust stats JSON (dict with 'stats' or a bare list of entries)."""
    entries = doc.get("stats") if isinstance(doc, dict) else doc
    if not isinstance(entries, list) or not entries:
        raise _Unparseable("locust stats JSON needs a non-empty 'stats' list")
    if not all(isinstance(e, dict) for e in entries):
        raise _Unparseable("locust 'stats' entries must be objects")

    endpoints: list[dict[str, Any]] = []
    for entry in entries:
        name = str(entry.get("name") or entry.get("Name") or "")
        method = entry.get("method") or entry.get("Type") or None
        method = str(method) if method else None
        endpoints.append(_endpoint(
            name=name or "unnamed",
            method=method or None,
            aggregate=name in _AGGREGATE_NAMES or (not name and not method),
            num_requests=_first_number(entry, _REQUESTS_KEYS),
            num_failures=_first_number(entry, _FAILURES_KEYS),
            p50_ms=_first_number(entry, _P50_KEYS),
            p95_ms=_first_number(entry, _P95_KEYS),
            p99_ms=_first_number(entry, _P99_KEYS),
            rps=_first_number(entry, _RPS_KEYS),
        ))

    _finish_rates(endpoints)
    return endpoints


def _parse_results(results: Any, fmt: str) -> tuple[str, list[dict[str, Any]]]:
    """Detect and parse the artifact; returns (format_name, endpoints)."""
    if fmt not in ("auto", "k6", "locust"):
        raise _Unparseable(f"unknown format {fmt!r} (expected 'k6', 'locust' or 'auto')")

    doc: Any = results
    if isinstance(results, str):
        text = results.strip()
        if not text:
            raise _Unparseable("load-test artifact is empty")
        try:
            doc = json.loads(text)
        except ValueError as json_err:
            # Not one JSON document — k6 raw output is newline-delimited JSON
            if fmt in ("auto", "k6"):
                try:
                    return "k6", _parse_k6_raw(text)
                except _Unparseable as e:
                    raise _Unparseable(
                        f"artifact is neither valid JSON nor k6 raw output ({e})"
                    ) from e
            raise _Unparseable("artifact is not valid JSON") from json_err

    attempts: list[tuple[str, Any]] = []
    if fmt in ("auto", "k6") and isinstance(doc, dict) and isinstance(doc.get("metrics"), dict):
        attempts.append(("k6", _parse_k6_summary))
    if fmt in ("auto", "locust"):
        attempts.append(("locust", _parse_locust))

    errors: list[str] = []
    for format_name, parse in attempts:
        try:
            return format_name, parse(doc)
        except _Unparseable as e:
            errors.append(f"{format_name}: {e}")

    detail = f" ({'; '.join(errors)})" if errors else ""
    raise _Unparseable(
        "could not parse artifact as k6 or locust output — supported: k6 "
        f"summary/raw JSON, locust stats JSON{detail}"
    )


class LoadTestAnalyzerSkill(BaseSkill):
    """Analyze real k6/Locust load-test artifacts uploaded via parameters.

    Checks per-endpoint request counts, failure rates, p50/p95/p99 latency
    and throughput against a p95 threshold and (optionally) a baseline
    artifact. Refuses missing or unparseable input instead of inventing data.
    """

    skill_id = "performance_load_test_analyzer"
    name = "Performance Load Test Analyzer"
    description = (
        "Analyze load test results (Locust/k6), detect regressions, "
        "estimate capacity, and identify bottlenecks."
    )
    category = SkillCategory.PERFORMANCE
    priority = SkillPriority.MEDIUM
    version = "2.0.0"

    DEFAULT_P95_THRESHOLD_MS = 500.0

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Analyze an uploaded load-test artifact.

        Args:
            project: Project/service name
            parameters: Analysis parameters
                - results: Artifact content (JSON string, parsed dict, or list)
                - format: "k6" | "locust" | "auto" (default "auto")
                - baseline: Optional baseline artifact (same shapes)
                - p95_threshold_ms: p95 flag threshold (default 500)
            context: Registry context

        Returns:
            AnalysisResult with per-endpoint stats and flags
        """
        try:
            results = parameters.get("results")
            if results is None or (isinstance(results, str) and not results.strip()):
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["no load-test results provided — pass the artifact "
                            "content in parameters['results']"],
                )

            fmt = str(parameters.get("format") or "auto").lower()
            threshold = float(parameters.get("p95_threshold_ms", self.DEFAULT_P95_THRESHOLD_MS))

            artifact_format, endpoints = _parse_results(results, fmt)

            baseline_comparison = None
            if parameters.get("baseline") is not None:
                _, baseline_endpoints = _parse_results(parameters["baseline"], "auto")
                baseline_comparison = self._compare_baseline(endpoints, baseline_endpoints)

            warnings = self._flag(endpoints, threshold)
            for comparison in baseline_comparison or []:
                if comparison["regression"]:
                    warnings.append(
                        f"{_label(comparison)}: p95 regressed "
                        f"{comparison['delta_percent']:+.1f}% vs baseline "
                        f"({comparison['baseline_p95_ms']:.0f}ms -> "
                        f"{comparison['p95_ms']:.0f}ms)"
                    )

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "project": project,
                    "format": artifact_format,
                    "p95_threshold_ms": threshold,
                    "endpoints": endpoints,
                    "summary": self._summarize(endpoints, baseline_comparison),
                    "baseline_comparison": baseline_comparison,
                },
                warnings=warnings,
            )
        except _Unparseable as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"unparseable load-test artifact: {e}"],
            )
        except (TypeError, ValueError) as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"invalid parameters: {e}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate recommendations from a completed analysis."""
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        endpoints = result.data.get("endpoints", [])
        regressions = [c for c in result.data.get("baseline_comparison") or [] if c["regression"]]

        recommendations: list[Recommendation] = []

        failing = [e for e in endpoints if e["flagged"]
                   and any("failure rate" in r for r in e["reasons"])]
        if failing:
            recommendations.append(Recommendation(
                title=f"Investigate failing requests on {len(failing)} endpoint(s)",
                description=(
                    "Endpoints exceeded the 1% failure-rate budget: "
                    + "; ".join(f"{_label(e)} ({e['failure_rate_percent']}%)" for e in failing)
                    + ". Correlate failures with error logs and saturation signals."
                ),
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="low",
            ))

        slow = [e for e in endpoints if e["flagged"] and any("p95" in r for r in e["reasons"])]
        if slow:
            recommendations.append(Recommendation(
                title=f"Reduce p95 latency on {len(slow)} endpoint(s)",
                description=(
                    "Endpoints exceeded the p95 threshold: "
                    + "; ".join(
                        f"{_label(e)} (p95 {e['p95_ms']:.0f}ms)" for e in slow if e["p95_ms"]
                    )
                    + ". Profile the slow path, check downstream timeouts and pool sizes."
                ),
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="2-4 hours",
                risk_level="low",
            ))

        if regressions:
            recommendations.append(Recommendation(
                title=f"Latency regression vs baseline on {len(regressions)} endpoint(s)",
                description=(
                    "p95 regressed more than 10% against the baseline artifact: "
                    + "; ".join(
                        f"{_label(c)} ({c['baseline_p95_ms']:.0f}ms -> {c['p95_ms']:.0f}ms, "
                        f"{c['delta_percent']:+.1f}%)"
                        for c in regressions if c["baseline_p95_ms"] and c["p95_ms"]
                    )
                ),
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-3 hours",
                risk_level="low",
            ))

        if not recommendations:
            recommendations.append(Recommendation(
                title="Load test within thresholds",
                description=(
                    "No endpoint exceeded the p95 threshold or failure budget"
                    + (" and no baseline regression was detected"
                       if result.data.get("baseline_comparison") is not None else "")
                    + ". Re-run before releases to catch regressions early."
                ),
                priority=SkillPriority.LOW,
                action_type="manual",
                risk_level="low",
            ))

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate that an artifact was provided and the format is known."""
        errors: list[str] = []
        results = parameters.get("results")
        if results is None or (isinstance(results, str) and not results.strip()):
            errors.append("parameters['results'] (k6 or locust artifact) is required")
        fmt = parameters.get("format", "auto")
        if fmt not in ("auto", "k6", "locust"):
            errors.append(f"format must be 'k6', 'locust' or 'auto', got {fmt!r}")
        return not errors, errors

    def _flag(self, endpoints: list[dict[str, Any]], threshold: float) -> list[str]:
        """Flag endpoints failing >1% or with p95 above threshold; warnings."""
        warnings: list[str] = []
        for ep in endpoints:
            label = _label(ep)
            if ep["failure_rate_percent"] is not None and ep["failure_rate_percent"] > FAILURE_RATE_FLAG_PERCENT:
                ep["flagged"] = True
                ep["reasons"].append(
                    f"failure rate {ep['failure_rate_percent']}% exceeds 1%"
                )
            if ep["p95_ms"] is not None and ep["p95_ms"] > threshold:
                ep["flagged"] = True
                ep["reasons"].append(
                    f"p95 {ep['p95_ms']:.0f}ms exceeds threshold {threshold:.0f}ms"
                )
            if ep["flagged"]:
                warnings.append(f"{label}: {'; '.join(ep['reasons'])}")
        return warnings

    def _compare_baseline(
        self,
        endpoints: list[dict[str, Any]],
        baseline_endpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Compare current p95 per endpoint against the baseline artifact.

        Regression = p95 delta above +10%. Endpoints without a baseline
        match are reported with baseline_p95_ms=None.
        """
        baseline_by_key = {
            (b["name"], b["method"]): b["p95_ms"] for b in baseline_endpoints
        }
        comparison: list[dict[str, Any]] = []
        for ep in endpoints:
            baseline_p95 = baseline_by_key.get((ep["name"], ep["method"]))
            entry: dict[str, Any] = {
                "name": ep["name"],
                "method": ep["method"],
                "baseline_p95_ms": baseline_p95,
                "p95_ms": ep["p95_ms"],
                "delta_percent": None,
                "regression": False,
            }
            if baseline_p95 and ep["p95_ms"] is not None:
                delta = (ep["p95_ms"] - baseline_p95) / baseline_p95 * 100.0
                entry["delta_percent"] = round(delta, 2)
                entry["regression"] = delta > BASELINE_REGRESSION_PERCENT
            comparison.append(entry)
        return comparison

    def _summarize(
        self,
        endpoints: list[dict[str, Any]],
        baseline_comparison: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Overall totals — prefer the artifact's own aggregate row/counts."""
        aggregate = next((e for e in endpoints if e["aggregate"]), None)
        per_endpoint = [e for e in endpoints if not e["aggregate"]] or endpoints

        def _total(field: str) -> float | None:
            if aggregate is not None and aggregate[field] is not None:
                return aggregate[field]
            values = [e[field] for e in per_endpoint if e[field] is not None]
            return sum(values) if values else None

        total_requests = _total("num_requests")
        total_failures = _total("num_failures")
        overall_rate = None
        if total_requests and total_failures is not None:
            overall_rate = round(total_failures / total_requests * 100.0, 3)
        total_rps = _total("rps")

        flagged = sum(1 for e in endpoints if e["flagged"])
        regressions = sum(
            1 for c in (baseline_comparison or []) if c["regression"]
        )

        return {
            "total_requests": total_requests,
            "total_failures": total_failures,
            "overall_failure_rate_percent": overall_rate,
            "total_throughput_rps": total_rps,
            "endpoint_count": len(per_endpoint),
            "endpoints_flagged": flagged,
            "baseline_regressions": regressions,
            "verdict": "pass" if flagged == 0 and regressions == 0 else "issues_found",
        }


def _label(endpoint: dict[str, Any]) -> str:
    """Human label for an endpoint entry."""
    method = endpoint.get("method") or ""
    name = endpoint.get("name") or "unnamed"
    return f"{method} {name}".strip()
