"""Phase 13: the first three real skills read live client data."""

import pytest



def _ctx(**clients):
    return {"clients": clients}


class FakeK8s:
    async def list_deployments(self, namespace=None):
        return [
            {"name": "api", "namespace": "prod", "replicas": 3, "available": 3, "image": "api:1"},
            {"name": "web", "namespace": "prod", "replicas": 2, "available": 1, "image": "web:1"},
            {"name": "batch", "namespace": "prod", "replicas": 0, "available": 0, "image": "b:1"},
        ]


@pytest.mark.asyncio
async def test_deployment_health_real_classification():
    from app.skills.devops.deployment_health_check import DeploymentHealthCheckSkill

    result = await DeploymentHealthCheckSkill().analyze("p", {}, _ctx(k8s=FakeK8s()))
    assert result.success
    hs = result.data["health_status"]
    assert hs["healthy"] == 1 and hs["unhealthy"] == 1 and hs["pending"] == 1
    by_name = {d["name"]: d for d in result.data["deployments"]}
    assert by_name["web"]["reason"] == "1/2 replicas available"
    assert by_name["batch"]["health"] == "pending"


@pytest.mark.asyncio
async def test_deployment_health_without_client_refuses():
    from app.skills.devops.deployment_health_check import DeploymentHealthCheckSkill

    result = await DeploymentHealthCheckSkill().analyze("p", {}, {"clients": {}})
    assert not result.success
    assert "Kubernetes client" in result.errors[0]


class FakeProm:
    def __init__(self, rows):
        self.rows = rows

    async def query(self, expr):
        if "rate(container_cpu" in expr:
            return self.rows["cpu"]
        if "working_set" in expr:
            return self.rows["mem"]
        if 'resource="cpu"' in expr:
            return self.rows["req_cpu"]
        if 'resource="memory"' in expr:
            return self.rows["req_mem"]
        return []


@pytest.mark.asyncio
async def test_resource_optimizer_flags_over_and_under():
    from app.skills.devops.resource_optimizer import ResourceOptimizerSkill

    prom = FakeProm(rows={
        "cpu": [{"metric": {"namespace": "n", "pod": "a-123"}, "value": [0, "0.05"]}],
        "mem": [{"metric": {"namespace": "n", "pod": "a-123"}, "value": [0, "104857600"]}],
        "req_cpu": [{"metric": {"namespace": "n", "pod": "a-123"}, "value": [0, "1"]}],
        "req_mem": [{"metric": {"namespace": "n", "pod": "a-123"}, "value": [0, "536870912"]}],
    })
    result = await ResourceOptimizerSkill().analyze("p", {"days": 7}, _ctx(prometheus=prom))
    assert result.success
    assert len(result.data["over_provisioned"]) == 1  # 0.05/1 cpu = 5%
    assert result.data["monthly_savings"] == 0.0


@pytest.mark.asyncio
async def test_resource_optimizer_without_client_refuses():
    from app.skills.devops.resource_optimizer import ResourceOptimizerSkill

    result = await ResourceOptimizerSkill().analyze("p", {}, {"clients": {}})
    assert not result.success
    assert "Prometheus" in result.errors[0]


class FakeSlo:
    async def calculate_slo(self, config):
        from app.models.slo import SloResult

        return SloResult(
            config_id="c1",
            service_name=config.service_name,
            slo_type=config.slo_type,
            target=99.9,
            current_value=99.5,
            total_requests=1000,
            good_requests=995,
            bad_requests=5,
            error_budget_remaining_percent=50.0,
            error_budget_total=10,
            error_budget_consumed=5,
            status="warning",
            window_days=30,
        )


@pytest.mark.asyncio
async def test_slo_tracker_real_results(user_store=None):
    from app.skills.reliability.slo_tracker import SLOTrackerSkill

    from app.models.slo import SloConfig
    from unittest.mock import patch

    skill = SLOTrackerSkill()
    configs = [SloConfig(
        service_name="meinvoice", slo_type="availability",
        target=99.9, window_days=30,
    )]
    with patch.object(skill, "_load_configs", return_value=configs):
        result = await skill.analyze("meinvoice", {}, _ctx(slo=FakeSlo()))
    assert result.success
    svc = result.data["services"][0]
    assert svc["current_percent"] == 99.5
    assert svc["burn_rate"] == 5.0  # (100-99.5)/(100-99.9)
    assert result.data["summary"]["compliant"] == 0


@pytest.mark.asyncio
async def test_slo_tracker_without_client_refuses():
    from app.skills.reliability.slo_tracker import SLOTrackerSkill

    result = await SLOTrackerSkill().analyze("p", {}, {"clients": {}})
    assert not result.success
    assert "SloClient" in result.errors[0]


# ---------- Phase 13 batch 2 ----------


@pytest.mark.asyncio
async def test_dependency_health_probes_real_endpoints(monkeypatch):
    from app.skills.reliability.dependency_health import DependencyHealthSkill

    skill = DependencyHealthSkill()
    probes = {
        "http://auth-service:8080/health": {"healthy": False, "latency_ms": 5000, "detail": "connect timeout"},
        "http://user-service:8080/health": {"healthy": True, "latency_ms": 30, "detail": "HTTP 200"},
    }

    async def fake_probe(endpoint):
        return probes.get(endpoint) or {"healthy": True, "latency_ms": 10, "detail": "HTTP 200"}

    monkeypatch.setattr(skill, "_probe", fake_probe)
    result = await skill.analyze("p", {}, {})
    assert result.success
    # auth-service is the only upstream (unhealthy, critical); user-service
    # lands in downstream
    assert result.data["upstream_health"]["healthy_count"] == 0
    assert result.data["upstream_health"]["unhealthy_critical"]
    assert result.data["downstream_health"]["healthy_count"] == 2  # user + notification


@pytest.mark.asyncio
async def test_alert_optimizer_reads_engine_history(monkeypatch):
    from app.skills.monitoring.alert_optimizer import AlertOptimizerSkill

    class FakeHistory:
        entries = [{"rule_id": "cpu_high", "duration_minutes": 1, "severity": "warning"}]

    skill = AlertOptimizerSkill()
    monkeypatch.setattr(
        "app.alerting.rules.load_rules",
        lambda: [type("R", (), {"id": "cpu_high", "name": "HighCPU", "metric": "cpu",
                                "condition": "gt", "threshold": 80, "severity": "warning",
                                "enabled": True})()],
    )
    result = await skill.analyze("p", {}, {"clients": {"alert_history": FakeHistory()}})
    assert result.success


@pytest.mark.asyncio
async def test_alert_optimizer_without_history_refuses():
    from app.skills.monitoring.alert_optimizer import AlertOptimizerSkill

    result = await AlertOptimizerSkill().analyze("p", {}, {"clients": {}})
    assert not result.success
    assert "alert history" in result.data["error"]


class FakeRangeProm:
    async def query_range(self, expr, start, end, step="60s"):
        if "node_cpu" in expr:
            return [{"metric": {"instance": "n1"}, "values": [[0, "40"], [3600, "60"]]}]
        if "MemAvailable" in expr:
            return [{"metric": {"instance": "n1"}, "values": [[0, "55"], [3600, "65"]]}]
        if "node_filesystem" in expr:
            return [{"metric": {"instance": "n1"}, "values": [[0, "30"], [3600, "35"]]}]
        return []


@pytest.mark.asyncio
async def test_capacity_planner_uses_real_series():
    from app.skills.capacity.planner import CapacityPlannerSkill

    result = await CapacityPlannerSkill().analyze("p", {}, {"clients": {"prometheus": FakeRangeProm()}})
    assert result.success
    assert "cpu" in result.data  # forecasts derived from the real series


@pytest.mark.asyncio
async def test_capacity_planner_without_prometheus_refuses():
    from app.skills.capacity.planner import CapacityPlannerSkill

    result = await CapacityPlannerSkill().analyze("p", {}, {"clients": {}})
    assert not result.success
    assert "Prometheus" in result.errors[0]


@pytest.mark.asyncio
async def test_growth_predictor_uses_real_series():
    from app.skills.capacity.growth_predictor import GrowthPredictorSkill

    result = await GrowthPredictorSkill().analyze("p", {"months": 2}, {"clients": {"prometheus": FakeRangeProm()}})
    assert result.success
    assert result.data["predictions"] is not None


def _df(content):
    from app.skills.devops.dockerfile_best_practices import DockerfileBestPracticesSkill

    skill = DockerfileBestPracticesSkill()
    import asyncio

    return asyncio.run(skill._analyze_dockerfile("Dockerfile", ".", content=content))


def test_dockerfile_lint_flags_real_issues():
    issues = _df("FROM ubuntu\nRUN curl -s https://x.sh | sh\nCMD [\"x\"]\n")
    types = {i["type"] for i in issues}
    assert {"unpinned_base", "root_user", "piped_shell_install", "no_multi_stage"} <= types


def test_dockerfile_lint_clean_file_scores_high():
    good = (
        "FROM python:3.12-slim AS build\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN pip install .\n"
        "FROM python:3.12-slim\n"
        "COPY --from=build /app /app\n"
        "USER 1000\n"
        "HEALTHCHECK CMD curl -f http://localhost:8080/health\n"
        "CMD [\"python\", \"-m\", \"app\"]\n"
    )
    issues = _df(good)
    assert not {i["type"] for i in issues} & {"unpinned_base", "root_user", "piped_shell_install"}


@pytest.mark.asyncio
async def test_manifest_validator_flags_gaps():
    from app.skills.devops.kubernetes_manifest_validator import KubernetesManifestValidatorSkill

    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    spec:
      containers:
        - name: web
          image: nginx
"""
    result = await KubernetesManifestValidatorSkill().analyze(
        "p", {"manifest": manifest}, {}
    )
    assert result.success
    types = {i["type"] for i in result.data["issues"]}
    assert {"unpinned_image", "run_as_root", "no_resource_requests",
            "no_liveness_probe", "no_readiness_probe"} <= types


@pytest.mark.asyncio
async def test_manifest_validator_requires_input():
    from app.skills.devops.kubernetes_manifest_validator import KubernetesManifestValidatorSkill

    result = await KubernetesManifestValidatorSkill().analyze("p", {}, {})
    assert not result.success
