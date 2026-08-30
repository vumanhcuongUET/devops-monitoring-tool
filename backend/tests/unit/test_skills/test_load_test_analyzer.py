"""Phase 14: performance_load_test_analyzer parses real uploaded artifacts.

Same contract as the dockerfile/kubernetes linters: only numbers present in
the artifact are reported; missing/unparseable input is refused with an
error instead of fabricated data.
"""

import json

import pytest

from app.skills.performance.load_test_analyzer import LoadTestAnalyzerSkill


def _k6_summary(p95: float = 620.0, failed_value: float = 0.01) -> dict:
    return {
        "metrics": {
            "http_reqs": {"values": {"count": 1000, "rate": 16.6}},
            "http_req_failed": {"values": {"passes": 990, "fails": 10, "value": failed_value}},
            "http_req_duration": {
                "contains": "time",
                "values": {
                    "avg": 120.3, "max": 950.0, "med": 95.0, "min": 12.0,
                    "p(90)": 210.0, "p(95)": p95,
                },
            },
        }
    }


LOCUST_STATS = {
    "stats": [
        {
            "method": "GET", "name": "/api/users",
            "num_requests": 500, "num_failures": 30,
            "Median": 120, "95%": 300, "99%": 450, "current_rps": 8.3,
        },
        {
            "method": "POST", "name": "/api/orders",
            "num_requests": 500, "num_failures": 0,
            "Median": 90, "95%": 180, "99%": 260, "current_rps": 8.3,
        },
        {
            "method": "", "name": "Total",
            "num_requests": 1000, "num_failures": 30,
            "Median": 105, "95%": 240, "current_rps": 16.6,
        },
    ]
}

# Modern locust --json key naming for the same data shape
LOCUST_STATS_MODERN_KEYS = {
    "stats": [
        {
            "method": "GET", "name": "/api/users",
            "num_requests": 200, "num_failures": 8,
            "median_response_time": 100,
            "ninety_fifth_response_time": 310,
            "ninety_ninth_response_time": 400,
            "current_rps": 3.3,
        },
    ]
}


def _k6_raw_ndjson() -> str:
    lines = []
    for i in range(10):
        lines.append(json.dumps({
            "type": "Point",
            "metric": "http_req_duration",
            "data": {
                "time": f"2026-08-30T10:00:{i:02d}Z",
                "value": (i + 1) * 100,  # 100..1000ms, sorted == insertion order
                "tags": {
                    "name": "https://api.example.com/search",
                    "method": "GET",
                    "status": "500" if i == 9 else "200",
                    "expected_response": "true" if i != 9 else "false",
                },
            },
        }))
    return "\n".join(lines)


@pytest.mark.asyncio
async def test_k6_summary_slow_endpoint_flagged():
    result = await LoadTestAnalyzerSkill().analyze(
        "api", {"results": json.dumps(_k6_summary()), "format": "auto"}
    )
    assert result.success
    assert result.data["format"] == "k6"
    ep = result.data["endpoints"][0]
    assert ep["name"] == "overall"
    assert ep["aggregate"] is True
    assert ep["num_requests"] == 1000
    assert ep["num_failures"] == 10
    assert ep["p50_ms"] == 95.0
    assert ep["p95_ms"] == 620.0
    assert ep["p99_ms"] is None  # p(99) absent from the artifact -> not invented
    # 1% failure rate is at the budget, not above it; p95 620ms is
    assert ep["flagged"] is True
    assert any("p95" in r for r in ep["reasons"])
    assert not any("failure rate" in r for r in ep["reasons"])
    assert result.data["summary"]["verdict"] == "issues_found"
    assert result.data["summary"]["total_throughput_rps"] == 16.6


@pytest.mark.asyncio
async def test_locust_failure_rate_flagged():
    result = await LoadTestAnalyzerSkill().analyze(
        "api", {"results": LOCUST_STATS, "format": "locust"}
    )
    assert result.success
    assert result.data["format"] == "locust"
    by_name = {e["name"]: e for e in result.data["endpoints"]}
    users = by_name["/api/users"]
    assert users["method"] == "GET"
    assert users["num_requests"] == 500
    assert users["failure_rate_percent"] == 6.0
    assert users["p50_ms"] == 120 and users["p95_ms"] == 300 and users["p99_ms"] == 450
    assert users["flagged"] is True
    assert any("failure rate" in r for r in users["reasons"])
    orders = by_name["/api/orders"]
    assert orders["flagged"] is False  # 0% failures, p95 180 < 500
    assert by_name["Total"]["aggregate"] is True
    assert result.data["summary"]["overall_failure_rate_percent"] == 3.0
    assert result.data["summary"]["total_requests"] == 1000


@pytest.mark.asyncio
async def test_locust_modern_key_naming_supported():
    result = await LoadTestAnalyzerSkill().analyze(
        "api", {"results": json.dumps(LOCUST_STATS_MODERN_KEYS)}
    )
    assert result.success
    ep = result.data["endpoints"][0]
    assert ep["p50_ms"] == 100
    assert ep["p95_ms"] == 310
    assert ep["p99_ms"] == 400
    assert ep["failure_rate_percent"] == 4.0


@pytest.mark.asyncio
async def test_k6_raw_ndjson_percentiles_and_failures():
    result = await LoadTestAnalyzerSkill().analyze(
        "api", {"results": _k6_raw_ndjson(), "format": "k6"}
    )
    assert result.success
    assert result.data["format"] == "k6"
    ep = result.data["endpoints"][0]
    assert ep["method"] == "GET"
    # linear interpolation over 100..1000: p50 rank 4.5 -> 550, p95 rank 8.55 -> 955
    assert ep["p50_ms"] == pytest.approx(550.0)
    assert ep["p95_ms"] == pytest.approx(955.0)
    assert ep["num_failures"] == 1  # one 500 / expected_response=false
    assert ep["failure_rate_percent"] == 10.0
    assert ep["flagged"] is True
    assert ep["rps"] == pytest.approx(10 / 9, rel=1e-6)  # 10 points over a 9s span


@pytest.mark.asyncio
async def test_baseline_regression_detection():
    skill = LoadTestAnalyzerSkill()
    result = await skill.analyze(
        "api",
        {
            "results": json.dumps(_k6_summary(p95=620.0)),
            "baseline": json.dumps(_k6_summary(p95=480.0)),
        },
    )
    assert result.success
    comp = result.data["baseline_comparison"][0]
    assert comp["baseline_p95_ms"] == 480.0
    assert comp["p95_ms"] == 620.0
    assert comp["delta_percent"] == pytest.approx(29.17, abs=0.01)
    assert comp["regression"] is True
    assert result.data["summary"]["verdict"] == "issues_found"
    assert any("baseline" in w or "regress" in w for w in result.warnings)

    # Within +10% of baseline is not a regression
    ok = await skill.analyze(
        "api",
        {
            "results": json.dumps(_k6_summary(p95=500.0)),
            "baseline": json.dumps(_k6_summary(p95=480.0)),
        },
    )
    assert ok.data["baseline_comparison"][0]["regression"] is False


@pytest.mark.asyncio
async def test_unparseable_input_refused():
    result = await LoadTestAnalyzerSkill().analyze("api", {"results": "not json {{{"})
    assert not result.success
    assert "unparseable" in result.errors[0]


@pytest.mark.asyncio
async def test_unknown_shape_refused():
    result = await LoadTestAnalyzerSkill().analyze(
        "api", {"results": json.dumps({"hello": "world"}), "format": "auto"}
    )
    assert not result.success
    assert "k6" in result.errors[0] and "locust" in result.errors[0]


@pytest.mark.asyncio
async def test_no_input_refused():
    skill = LoadTestAnalyzerSkill()
    result = await skill.analyze("api", {})
    assert not result.success
    assert "results" in result.errors[0]

    empty = await skill.analyze("api", {"results": "   "})
    assert not empty.success


@pytest.mark.asyncio
async def test_empty_artifact_refused():
    result = await LoadTestAnalyzerSkill().analyze("api", {"results": "{}"})
    assert not result.success


def test_validate_parameters_requires_results():
    skill = LoadTestAnalyzerSkill()
    valid, errors = skill.validate_parameters({"results": "{}"})
    assert valid and not errors
    valid, errors = skill.validate_parameters({})
    assert not valid and errors
    valid, errors = skill.validate_parameters({"results": "x", "format": "xml"})
    assert not valid
