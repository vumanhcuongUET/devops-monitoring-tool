"""Contract tests for /health/ready (Phase 14 residual #2).

The old readiness probe hit /health, which answers liveness — a pod whose
Elasticsearch/Prometheus/K8s clients were all dead still served "ok". These
tests pin the honest contract: per-source up/down/skipped, the 503-only-when-
everything-is-down policy, auth exemption, and the alert-engine heartbeat
metrics wired into the fetch-error path.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.metrics import ALERT_ENGINE_LAST_SUCCESS, ALERT_EVAL_ERRORS

# Every Redis toggle the endpoint consults — force all off so Redis reads as
# "skipped" regardless of the environment the suite runs in.
_REDIS_FLAGS = (
    "REDIS_URL",
    "ALERT_STATE_USE_REDIS",
    "APPROVAL_STATE_USE_REDIS",
    "RATE_LIMIT_USE_REDIS",
    "WS_FANOUT_USE_REDIS",
    "ALERT_ENGINE_LEADER_LOCK",
)


def _no_redis(monkeypatch):
    monkeypatch.setattr("app.settings.settings.REDIS_URL", None)
    for flag in _REDIS_FLAGS[1:]:
        monkeypatch.setattr(f"app.settings.settings.{flag}", False)


class _FakeES:
    def __init__(self, up=True):
        self.up = up

    async def get_cluster_health(self):
        if not self.up:
            raise ConnectionError("es unreachable")
        return {"status": "green"}


class _FakeProm:
    def __init__(self, up=True):
        self.up = up

    async def query(self, expr):
        if not self.up:
            raise ConnectionError("prom unreachable")
        return []


class _FakeK8s:
    def __init__(self, available=True, nodes=("node-1",)):
        self.available = available
        self._nodes = nodes

    async def list_nodes(self):
        return [{"name": n} for n in self._nodes]


def _install(monkeypatch, **clients):
    """Attach fake clients to app.state; absent ones are removed entirely."""
    from app.main import app

    for name in ("es_client", "prometheus_client", "k8s_client"):
        if name in clients:
            monkeypatch.setattr(app.state, name, clients[name], raising=False)
        else:
            monkeypatch.delattr(app.state, name, raising=False)


def test_health_ready_all_up(monkeypatch):
    from app.main import app

    _no_redis(monkeypatch)
    _install(
        monkeypatch,
        es_client=_FakeES(),
        prometheus_client=_FakeProm(),
        k8s_client=_FakeK8s(),
    )
    monkeypatch.setattr("app.settings.settings.AUTH_ENABLED", False)
    client = TestClient(app)  # no lifespan — the endpoint probes app.state

    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    sources = body["sources"]
    assert set(sources) == {"elasticsearch", "prometheus", "kubernetes", "redis"}
    for name in ("elasticsearch", "prometheus", "kubernetes"):
        assert sources[name]["status"] == "up", name
        assert isinstance(sources[name]["latency_ms"], int)
    assert sources["redis"]["status"] == "skipped"  # nothing configured to use it


def test_health_ready_one_down_is_degraded_not_503(monkeypatch):
    from app.main import app

    _no_redis(monkeypatch)
    _install(
        monkeypatch,
        es_client=_FakeES(up=False),
        prometheus_client=_FakeProm(),
        k8s_client=_FakeK8s(),
    )
    monkeypatch.setattr("app.settings.settings.AUTH_ENABLED", False)
    client = TestClient(app)

    resp = client.get("/health/ready")
    assert resp.status_code == 200  # one flaky dep must not flap the pod
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["sources"]["elasticsearch"]["status"] == "down"
    assert body["sources"]["elasticsearch"]["error"] == "ConnectionError"
    assert body["sources"]["prometheus"]["status"] == "up"


def test_health_ready_all_down_returns_503(monkeypatch):
    from app.main import app

    _no_redis(monkeypatch)
    _install(
        monkeypatch,
        es_client=_FakeES(up=False),
        prometheus_client=_FakeProm(up=False),
        k8s_client=_FakeK8s(available=False),
    )
    monkeypatch.setattr("app.settings.settings.AUTH_ENABLED", False)
    client = TestClient(app)

    resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "down"
    # k8s client present but its API unusable: down, not skipped
    assert body["sources"]["kubernetes"]["status"] == "down"
    assert body["sources"]["redis"]["status"] == "skipped"  # still not "down"


def test_health_ready_k8s_empty_node_list_is_down(monkeypatch):
    from app.main import app

    _no_redis(monkeypatch)
    _install(
        monkeypatch,
        es_client=_FakeES(),
        prometheus_client=_FakeProm(),
        k8s_client=_FakeK8s(available=True, nodes=()),  # list_nodes swallows errors
    )
    monkeypatch.setattr("app.settings.settings.AUTH_ENABLED", False)
    client = TestClient(app)

    body = client.get("/health/ready").json()
    assert body["status"] == "degraded"
    assert body["sources"]["kubernetes"]["status"] == "down"


def test_health_ready_missing_clients_are_skipped(monkeypatch):
    from app.main import app

    _no_redis(monkeypatch)
    _install(monkeypatch)  # no clients attached at all (lifespan never ran)
    monkeypatch.setattr("app.settings.settings.AUTH_ENABLED", False)
    client = TestClient(app)

    resp = client.get("/health/ready")
    assert resp.status_code == 200  # absent is not down
    body = resp.json()
    assert body["status"] == "ok"
    assert all(s["status"] == "skipped" for s in body["sources"].values())


def test_health_ready_is_auth_exempt(monkeypatch):
    """No API key / bearer token -> 200, not 401 (kubelet sends no headers)."""
    from app.main import app

    _no_redis(monkeypatch)
    _install(monkeypatch)
    monkeypatch.setattr("app.settings.settings.AUTH_ENABLED", True)
    monkeypatch.setattr("app.settings.settings.API_KEYS", [])
    client = TestClient(app)

    assert client.get("/health/ready").status_code == 200
    # sanity: a protected path does 401 with the same credentials (none)
    assert client.get("/api/v1/alerts/rules").status_code == 401


async def test_engine_counts_eval_errors_and_beats(monkeypatch):
    """A failing rule fetch bumps alert_eval_errors_total; a finished cycle
    stamps the heartbeat gauge — silent `continue` used to hide both."""
    from app.alerting.engine import AlertEngine

    monkeypatch.setattr("app.settings.settings.ALERT_STATE_USE_REDIS", False)
    engine = AlertEngine()
    monkeypatch.setattr(
        engine, "_fetch_prometheus", AsyncMock(side_effect=ConnectionError("prom down"))
    )
    rule = SimpleNamespace(id="test-rule", enabled=True, source="prometheus")
    monkeypatch.setattr("app.alerting.engine.load_rules", lambda: [rule])

    def errors():
        return REGISTRY.get_sample_value("alert_eval_errors_total", {"source": "prometheus"}) or 0

    before = errors()
    await engine._check_all(SimpleNamespace())

    assert errors() == before + 1
    assert REGISTRY.get_sample_value("alert_engine_last_success_timestamp") > 0
    # the family exists for /metrics scraping
    assert ALERT_EVAL_ERRORS is not None and ALERT_ENGINE_LAST_SUCCESS is not None
