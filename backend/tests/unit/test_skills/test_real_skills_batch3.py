"""Phase 13 batch 3: twelve more skills read live client data or lint real input."""

import pytest


def _ctx(**clients):
    return {"clients": clients}


# ---------- observability_metrics_analyzer ----------


class FakePromInstant:
    """Prometheus double answering the metrics-analyzer query set."""

    async def query(self, expr):
        if "histogram_quantile(0.5" in expr:
            return [{"metric": {}, "value": [0, "0.045"]}]
        if "histogram_quantile(0.95" in expr:
            return [{"metric": {}, "value": [0, "0.234"]}]
        if "histogram_quantile(0.99" in expr:
            return [{"metric": {}, "value": [0, "1.2"]}]
        if "status=~\"5..\"" in expr:
            return [{"metric": {}, "value": [0, "2.5"]}]  # 2.5% error rate
        return []

    async def get_cpu_percent(self):
        return 85.0

    async def get_memory_percent(self):
        return 60.0


@pytest.mark.asyncio
async def test_metrics_analyzer_real_numbers():
    from app.skills.observability.metrics_analyzer import MetricsAnalyzerSkill

    result = await MetricsAnalyzerSkill().analyze(
        "p", {"time_range_hours": 1}, _ctx(prometheus=FakePromInstant())
    )
    assert result.success
    assert result.data["latency_ms"]["p50"] == 45.0  # seconds -> ms
    assert result.data["latency_ms"]["p95"] == 234.0
    assert result.data["error_rate_percent"] == 2.5
    assert "Elevated error rate" in result.warnings[0]
    assert result.data["resource_utilization"]["cpu_percent"] == 85.0


@pytest.mark.asyncio
async def test_metrics_analyzer_reports_missing_metrics():
    from app.skills.observability.metrics_analyzer import MetricsAnalyzerSkill

    class EmptyProm(FakePromInstant):
        async def query(self, expr):
            return []

    result = await MetricsAnalyzerSkill().analyze("p", {}, _ctx(prometheus=EmptyProm()))
    assert result.success
    assert result.data["metrics_missing"] == ["error_rate", "p50", "p95", "p99"]
    assert result.data["message"]


@pytest.mark.asyncio
async def test_metrics_analyzer_without_client_refuses():
    from app.skills.observability.metrics_analyzer import MetricsAnalyzerSkill

    result = await MetricsAnalyzerSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "Prometheus client" in result.errors[0]


# ---------- observability_anomaly_detector ----------


@pytest.mark.asyncio
async def test_anomaly_detector_real_series():
    from app.skills.observability.anomaly_detector import AnomalyDetectorSkill

    class FakeRangeProm:
        async def query_range(self, expr, start, end, step="60s"):
            values = [[i * 60, str(10 + (i % 2))] for i in range(50)]
            values[25] = [25 * 60, "500"]  # obvious spike
            return [{"metric": {}, "values": values}]

    result = await AnomalyDetectorSkill().analyze(
        "p", {"expression": "node_load1", "time_window_hours": 12},
        _ctx(prometheus=FakeRangeProm()),
    )
    assert result.success
    assert result.data["points"] == 50
    assert result.data["anomalies"]
    assert all(a["method"] in ("z_score", "iqr") for a in result.data["anomalies"])
    assert not any("mock" in str(a) for a in result.data["anomalies"])


@pytest.mark.asyncio
async def test_anomaly_detector_insufficient_data_fails():
    from app.skills.observability.anomaly_detector import AnomalyDetectorSkill

    class EmptyRangeProm:
        async def query_range(self, expr, start, end, step="60s"):
            return []

    result = await AnomalyDetectorSkill().analyze(
        "p", {"metric": "nope"}, _ctx(prometheus=EmptyRangeProm())
    )
    assert not result.success
    assert "Insufficient data" in result.errors[0]


@pytest.mark.asyncio
async def test_anomaly_detector_without_client_refuses():
    from app.skills.observability.anomaly_detector import AnomalyDetectorSkill

    result = await AnomalyDetectorSkill().analyze("p", {"metric": "x"}, _ctx())
    assert not result.success
    assert "Prometheus client" in result.errors[0]


# ---------- capacity_bottleneck_detector ----------


@pytest.mark.asyncio
async def test_bottleneck_detector_flags_saturation():
    from app.skills.capacity.bottleneck_detector import BottleneckDetectorSkill

    class SatProm:
        async def query_range(self, expr, start, end, step="60s"):
            if "node_cpu" in expr:
                # Rising to 95% — critical now
                return [{"metric": {"instance": "n1"}, "values": [[0, "70"], [3600, "95"]]}]
            if "MemAvailable" in expr:
                return [{"metric": {"instance": "n1"}, "values": [[0, "50"], [3600, "55"]]}]
            return []

    result = await BottleneckDetectorSkill().analyze("p", {}, _ctx(prometheus=SatProm()))
    assert result.success
    cpu = result.data["resources"]["cpu"]
    assert cpu["status"] == "bottleneck"
    assert {b["resource"] for b in result.data["bottlenecks"]} == {"cpu"}
    assert result.data["resources"]["disk"]["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_bottleneck_detector_without_client_refuses():
    from app.skills.capacity.bottleneck_detector import BottleneckDetectorSkill

    result = await BottleneckDetectorSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "Prometheus client" in result.errors[0]


# ---------- monitoring_sli_calculator ----------


@pytest.mark.asyncio
async def test_sli_calculator_real_slis():
    from app.skills.monitoring.sli_calculator import SLICalculatorSkill

    class SliProm:
        async def query(self, expr):
            if "avg_over_time(up" in expr:
                return [
                    {"metric": {"job": "api"}, "value": [0, "100"]},
                    {"metric": {"job": "worker"}, "value": [0, "98.5"]},
                ]
            if "status=~\"5..\"" in expr:
                return [{"metric": {}, "value": [0, "0.05"]}]
            if 'le="0.5"' in expr:
                return [{"metric": {}, "value": [0, "99.8"]}]
            if "http_requests_total[24h]))" in expr and "rate" in expr:
                return [{"metric": {}, "value": [0, "120.5"]}]
            return []

    result = await SLICalculatorSkill().analyze(
        "p", {"time_window_hours": 24}, _ctx(prometheus=SliProm())
    )
    assert result.success
    slis = result.data["slis"]
    assert slis["availability_percent"] == 99.25
    assert slis["availability_percent_by_job"]["worker"] == 98.5
    assert slis["error_rate_percent"] == 0.05
    assert slis["latency_sli_percent"] == 99.8


@pytest.mark.asyncio
async def test_sli_calculator_no_metrics_fails():
    from app.skills.monitoring.sli_calculator import SLICalculatorSkill

    class EmptyProm:
        async def query(self, expr):
            return []

    result = await SLICalculatorSkill().analyze("p", {}, _ctx(prometheus=EmptyProm()))
    assert not result.success
    assert "No SLI source metrics" in result.errors[0]


@pytest.mark.asyncio
async def test_sli_calculator_without_client_refuses():
    from app.skills.monitoring.sli_calculator import SLICalculatorSkill

    result = await SLICalculatorSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "Prometheus client" in result.errors[0]


# ---------- reliability_scaling_analyzer ----------


class FakeScalingK8s:
    async def list_deployments(self, namespace=None):
        return [
            {"name": "api", "namespace": "prod", "replicas": 3, "available": 3, "image": "api"},
            {"name": "web", "namespace": "prod", "replicas": 2, "available": 1, "image": "web"},
        ]

    async def list_pods(self, namespace=None):
        return [
            {"name": "web-x", "namespace": "prod", "status": "Pending", "restarts": 0},
            {"name": "api-x", "namespace": "prod", "status": "Running", "restarts": 9},
        ]

    async def get_events(self, namespace=None):
        return [
            {"reason": "FailedScheduling", "type": "Warning", "message": "0/3 nodes available",
             "object": "Pod/web-x", "timestamp": "2026-08-30T10:00:00"},
            {"reason": "Pulled", "type": "Normal", "message": "image pulled",
             "object": "Pod/api-x", "timestamp": "2026-08-30T09:00:00"},
        ]


@pytest.mark.asyncio
async def test_scaling_analyzer_real_cluster_state():
    from app.skills.reliability.scaling_analyzer import ScalingAnalyzerSkill

    result = await ScalingAnalyzerSkill().analyze("p", {}, _ctx(k8s=FakeScalingK8s()))
    assert result.success
    by_name = {d["name"]: d for d in result.data["deployments"]}
    assert by_name["api"]["state"] == "ready"
    assert by_name["web"]["state"] == "degraded"
    assert len(result.data["blocked_pods"]) == 2  # Pending + restart loop
    assert len(result.data["scaling_events"]) == 1  # FailedScheduling only


@pytest.mark.asyncio
async def test_scaling_analyzer_without_client_refuses():
    from app.skills.reliability.scaling_analyzer import ScalingAnalyzerSkill

    result = await ScalingAnalyzerSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "Kubernetes client" in result.errors[0]


# ---------- reliability_sla_compliance + observability_slo_tracker ----------


class FakeSloClient:
    async def calculate_slo(self, config):
        from app.models.slo import SloResult

        return SloResult(
            config_id="c1",
            service_name=config.service_name,
            slo_type=config.slo_type,
            target=99.9,
            current_value=99.95 if config.service_name == "good" else 99.0,
            total_requests=1000,
            good_requests=999,
            bad_requests=1,
            error_budget_remaining_percent=80.0,
            error_budget_total=10,
            error_budget_consumed=2,
            status="healthy" if config.service_name == "good" else "warning",
            window_days=30,
        )


def _slo_configs():
    from app.models.slo import SloConfig

    return [
        SloConfig(service_name="good", slo_type="availability", target=99.9, window_days=30),
        SloConfig(service_name="bad", slo_type="availability", target=99.9, window_days=30),
    ]


@pytest.mark.asyncio
async def test_sla_compliance_real_results(monkeypatch):
    from app.skills.reliability.sla_compliance import SLAComplianceSkill

    skill = SLAComplianceSkill()
    monkeypatch.setattr(
        "app.services.slo_config_store.load_configs",
        lambda: [c.model_dump() for c in _slo_configs()],
    )
    result = await skill.analyze("", {}, _ctx(slo=FakeSloClient()))
    assert result.success
    assert result.data["summary"]["compliant"] == 1
    assert result.data["summary"]["breached"] == 1
    assert result.data["breaches"][0]["service"] == "bad"


@pytest.mark.asyncio
async def test_observability_slo_tracker_shares_real_data(monkeypatch):
    from app.skills.observability.slo_tracker import SLOTrackerSkill

    skill = SLOTrackerSkill()
    monkeypatch.setattr(
        "app.services.slo_config_store.load_configs",
        lambda: [c.model_dump() for c in _slo_configs()],
    )
    result = await skill.analyze("good", {}, _ctx(slo=FakeSloClient()))
    assert result.success
    assert result.data["services"][0]["service"] == "good"
    assert result.data["services"][0]["compliant"] is True
    assert result.data["services"][0]["burn_rate"] is not None


@pytest.mark.asyncio
async def test_sla_compliance_without_client_refuses():
    from app.skills.reliability.sla_compliance import SLAComplianceSkill

    result = await SLAComplianceSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "SloClient" in result.errors[0]


# ---------- observability_tracing_analyzer ----------


class FakeApmEs:
    """ES double behind ApmClient: pre-baked aggregation responses."""

    async def search(self, index, body):
        aggs = body.get("aggs", {})
        if "transactions" in aggs:
            # get_transactions per-name agg
            return {
                "aggregations": {
                    "transactions": {
                        "buckets": [
                            {"key": "GET /api/users", "doc_count": 3000,
                             "p50": {"values": {"50.0": 40000, "95.0": 90000, "99.0": 200000}},
                             "throughput": {"value": 3000}},
                            {"key": "POST /api/orders", "doc_count": 2000,
                             "p50": {"values": {"50.0": 120000, "95.0": 600000, "99.0": 900000}},
                             "throughput": {"value": 2000}},
                        ]
                    }
                },
                "hits": {"total": {"value": 5000}},
            }
        if "latency" in aggs:
            # get_summary latency agg
            return {
                "aggregations": {
                    "latency": {"values": {"50.0": 45000, "95.0": 234000, "99.0": 1200000}},
                    "total": {"value": 5000},
                },
                "hits": {"total": {"value": 5000}},
            }
        # error index count
        return {"hits": {"total": {"value": 50}}}


@pytest.mark.asyncio
async def test_tracing_analyzer_real_apm():
    from app.skills.observability.tracing_analyzer import TracingAnalyzerSkill

    result = await TracingAnalyzerSkill().analyze(
        "api", {"time_range_hours": 1}, _ctx(es=type("Es", (), {"client": FakeApmEs()})())
    )
    assert result.success
    assert result.data["summary"]["throughput"] == 5000
    assert result.data["summary"]["error_rate_percent"] == 1.0
    slowest = result.data["slowest_transactions"]
    assert slowest[0]["name"] == "POST /api/orders"  # sorted by p95 desc


@pytest.mark.asyncio
async def test_tracing_analyzer_without_client_refuses():
    from app.skills.observability.tracing_analyzer import TracingAnalyzerSkill

    result = await TracingAnalyzerSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "Elasticsearch client" in result.errors[0]


# ---------- reliability_dlq_monitor ----------


@pytest.mark.asyncio
async def test_dlq_monitor_real_logs():
    from app.skills.reliability.dlq_monitor import DLQMonitorSkill

    class FakeEsLogs:
        async def search_logs(self, query, level=None, service=None, start=None,
                              end=None, page=1, size=50):
            assert level == "ERROR"
            hits = [
                {"@timestamp": "2026-08-30T10:00:00Z", "service": "billing",
                 "message": "moved to dead letter queue: timeout"},
                {"@timestamp": "2026-08-30T11:00:00Z", "service": "billing",
                 "message": "moved to dead letter queue: timeout"},
                {"@timestamp": "2026-08-30T11:30:00Z", "service": "notify",
                 "message": "dlq: invalid payload"},
            ]
            return hits, len(hits)

    result = await DLQMonitorSkill().analyze("p", {}, _ctx(es=FakeEsLogs()))
    assert result.success
    assert result.data["total_dlq_signals"] == 3
    assert result.data["by_service"]["billing"] == 2
    assert result.data["trend"] == "increasing"


@pytest.mark.asyncio
async def test_dlq_monitor_zero_signals_is_success():
    from app.skills.reliability.dlq_monitor import DLQMonitorSkill

    class EmptyEs:
        async def search_logs(self, **kwargs):
            return [], 0

    result = await DLQMonitorSkill().analyze("p", {}, _ctx(es=EmptyEs()))
    assert result.success
    assert result.data["total_dlq_signals"] == 0
    assert result.data["message"]


@pytest.mark.asyncio
async def test_dlq_monitor_without_client_refuses():
    from app.skills.reliability.dlq_monitor import DLQMonitorSkill

    result = await DLQMonitorSkill().analyze("p", {}, _ctx())
    assert not result.success
    assert "Elasticsearch client" in result.errors[0]


# ---------- code complexity / duplication / smell ----------


MESSY_SOURCE = '''\
import os


def process(data, flag, mode, limit, offset, user, tenant):
    result = []
    try:
        for item in data:
            if item:
                if flag:
                    for sub in item:
                        if sub and mode == "x":
                            if limit > 0:
                                if offset:
                                    while limit:
                                        if user:
                                            result.append(sub)
                                        limit -= 1
    except:
        pass
    print(result)
    return result
'''


@pytest.mark.asyncio
async def test_complexity_analyzer_flags_hotspot():
    from app.skills.code.complexity_analyzer import ComplexityAnalyzerSkill

    result = await ComplexityAnalyzerSkill().analyze(
        "p", {"filename": "messy.py", "content": MESSY_SOURCE}, {}
    )
    assert result.success
    hotspot = result.data["hotspots"][0]
    assert hotspot["function"] == "process"
    assert hotspot["complexity"] >= 7  # 1 + branches + boolop


@pytest.mark.asyncio
async def test_complexity_analyzer_requires_input():
    from app.skills.code.complexity_analyzer import ComplexityAnalyzerSkill

    result = await ComplexityAnalyzerSkill().analyze("p", {}, {})
    assert not result.success
    assert "No source provided" in result.errors[0]


@pytest.mark.asyncio
async def test_duplication_detector_finds_real_clones():
    from app.skills.code.duplication_detector import DuplicationDetectorSkill

    block = "\n".join(f"line_{i} = {i}" for i in range(8))
    files = {"a.py": f"def f():\n    {block.replace(chr(10), chr(10) + '    ')}\n",
             "b.py": f"def g():\n    {block.replace(chr(10), chr(10) + '    ')}\n"}
    result = await DuplicationDetectorSkill().analyze("p", {"files": files}, {})
    assert result.success
    assert result.data["duplicated_windows"] > 0
    assert result.data["duplicate_percent"] > 0
    files_in_blocks = {
        occ["file"] for b in result.data["duplicate_blocks"] for occ in b["occurrences"]
    }
    assert files_in_blocks == {"a.py", "b.py"}


@pytest.mark.asyncio
async def test_duplication_detector_clean_code_low():
    from app.skills.code.duplication_detector import DuplicationDetectorSkill

    content = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    result = await DuplicationDetectorSkill().analyze(
        "p", {"filename": "x.py", "content": content}, {}
    )
    assert result.success
    assert result.data["duplicated_windows"] == 0
    assert result.data["summary"]["level"] == "acceptable"


@pytest.mark.asyncio
async def test_smell_detector_flags_real_smells():
    from app.skills.code.smell_detector import CodeSmellDetectorSkill

    result = await CodeSmellDetectorSkill().analyze(
        "p", {"filename": "messy.py", "content": MESSY_SOURCE}, {}
    )
    assert result.success
    types = {i["type"] for i in result.data["issues"]}
    assert {"too_many_arguments", "bare_except", "deep_nesting", "print_debug"} <= types
    # every flagged issue is line-accurate
    assert all(i["line"] for i in result.data["issues"])


@pytest.mark.asyncio
async def test_smell_detector_requires_input():
    from app.skills.code.smell_detector import CodeSmellDetectorSkill

    result = await CodeSmellDetectorSkill().analyze("p", {}, {})
    assert not result.success
    assert "No source provided" in result.errors[0]


# ---------- registry accounting ----------


def test_batch3_skills_no_longer_stubbed():
    from app.skills.registry import STUB_SKILLS, get_skill_registry

    promoted = [
        "observability_metrics_analyzer",
        "observability_tracing_analyzer",
        "observability_anomaly_detector",
        "observability_slo_tracker",
        "reliability_sla_compliance",
        "reliability_dlq_monitor",
        "reliability_scaling_analyzer",
        "capacity_bottleneck_detector",
        "monitoring_sli_calculator",
        "code_complexity_analyzer",
        "code_duplication_detector",
        "code_smell_detector",
    ]
    assert not (set(promoted) & STUB_SKILLS)
    registry = get_skill_registry()
    for skill_id in promoted:
        assert registry.get_skill(skill_id).implemented is True
    assert len(STUB_SKILLS) == 23  # 44 registered, 21 implemented
