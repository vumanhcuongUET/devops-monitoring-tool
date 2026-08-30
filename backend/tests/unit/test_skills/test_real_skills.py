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
