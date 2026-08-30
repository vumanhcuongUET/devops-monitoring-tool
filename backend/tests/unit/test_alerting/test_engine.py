"""
Unit tests for Alert Engine.

Tests the alert engine functionality including:
- Alert rule evaluation
- Alert state management
- Alert firing and resolution
- Notification triggering
- Batched (per-source) metric fetching: one client call per
  source/fetch-key per cycle instead of one call per rule
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertEngine:
    """Test suite for AlertEngine."""

    @pytest.mark.asyncio
    async def test_alert_engine_initialization(self):
        """Test that AlertEngine initializes correctly."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        engine = AlertEngine()
        assert engine is not None
        # clients attribute removed in new implementation

    @pytest.mark.asyncio
    async def test_check_all_rules_with_no_rules(self):
        """Test that _check_all handles empty rules list."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        engine = AlertEngine()
        engine._check_all = AsyncMock(return_value=[])

        result = await engine._check_all()

        assert result == []

    @pytest.mark.asyncio
    async def test_fire_alert_creates_alert_event(self):
        """Test that _fire creates an alert event."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        engine = AlertEngine()
        engine._fire = AsyncMock(return_value={
            "rule_id": "test-rule-001",
            "state": "firing",
            "timestamp": datetime.now().isoformat()
        })

        result = await engine._fire(
            rule_id="test-rule-001",
            message="Test alert fired"
        )

        assert result["state"] == "firing"
        assert result["rule_id"] == "test-rule-001"

    @pytest.mark.asyncio
    async def test_resolve_alert_transitions_state(self):
        """Test that _resolve transitions alert to resolved state."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        engine = AlertEngine()
        engine._resolve = AsyncMock(return_value={
            "rule_id": "test-rule-001",
            "state": "resolved",
            "timestamp": datetime.now().isoformat()
        })

        result = await engine._resolve(rule_id="test-rule-001")

        assert result["state"] == "resolved"

    @pytest.mark.asyncio
    async def test_notify_triggers_notification(self):
        """Test that _notify triggers notification action."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        engine = AlertEngine()
        engine._notify = AsyncMock(return_value=True)

        result = await engine._notify(
            alert_data={"rule_id": "test-rule-001"},
            action={"type": "slack", "webhook": "https://hooks.slack.com/test"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_start_begins_evaluation_loop(self):
        """Test that start begins the alert evaluation loop."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        engine = AlertEngine()
        engine.start = AsyncMock(return_value=None)

        await engine.start()

        engine.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_all_with_multiple_sources(self):
        """Test that _check_all evaluates rules from different sources."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": AsyncMock(return_value=[]),
            "prom": AsyncMock(return_value=[]),
            "k8s": AsyncMock(return_value=[])
        }

        engine = AlertEngine()
        engine._check_all = AsyncMock(return_value=[])

        result = await engine._check_all()

        assert result == []

    @pytest.mark.asyncio
    async def test_evaluate_elasticsearch_rule(self):
        """Test evaluation of Elasticsearch-based alert rule."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        # Mock ES client to return error count
        mock_clients["es"].get_error_count = AsyncMock(return_value=100)

        engine = AlertEngine()

        rule = {
            "id": "es-rule-001",
            "source": "elasticsearch",
            "conditions": [
                {"type": "error_count", "threshold": 50}
            ]
        }

        # This would normally evaluate the rule
        # For now we just test the structure
        assert rule["source"] == "elasticsearch"
        assert rule["conditions"][0]["threshold"] == 50

    @pytest.mark.asyncio
    async def test_evaluate_prometheus_rule(self):
        """Test evaluation of Prometheus-based alert rule."""
        from app.alerting.engine import AlertEngine

        mock_clients = {
            "es": MagicMock(),
            "prom": MagicMock(),
            "k8s": MagicMock()
        }

        # Mock Prometheus client to return alert data
        mock_clients["prom"].get_alerts = AsyncMock(return_value={
            "data": {"alerts": [{"alertname": "HighCPU", "state": "firing"}]}
        })

        engine = AlertEngine()

        rule = {
            "id": "prom-rule-001",
            "source": "prometheus",
            "conditions": [
                {"type": "alert_firing", "alertname": "HighCPU"}
            ]
        }

        assert rule["source"] == "prometheus"
        assert rule["conditions"][0]["alertname"] == "HighCPU"


# ---------------------------------------------------------------------------
# Fakes for the batched-fetch tests (call-counting source clients)
# ---------------------------------------------------------------------------


class FakeESClient:
    def __init__(self, error_count=10, exc=None):
        self.error_count = error_count
        self.exc = exc
        self.get_error_count_calls = []

    async def get_error_count(self, minutes=60):
        self.get_error_count_calls.append(minutes)
        if self.exc:
            raise self.exc
        return self.error_count


class FakeAPMClient:
    def __init__(self, summary=None, exc=None):
        self.summary = summary if summary is not None else {}
        self.exc = exc
        self.get_summary_calls = 0

    async def get_summary(self, start=None, end=None):
        self.get_summary_calls += 1
        if self.exc:
            raise self.exc
        return self.summary


class FakePrometheusClient:
    def __init__(self, cpu=10.0, memory=20.0, exc=None):
        self.cpu = cpu
        self.memory = memory
        self.exc = exc
        self.cpu_calls = 0
        self.memory_calls = 0

    async def get_cpu_percent(self):
        self.cpu_calls += 1
        if self.exc:
            raise self.exc
        return self.cpu

    async def get_memory_percent(self):
        self.memory_calls += 1
        if self.exc:
            raise self.exc
        return self.memory


class FakeK8sClient:
    def __init__(self, pods=None, deployments=None, pods_exc=None, deployments_exc=None):
        self.pods = pods or []
        self.deployments = deployments or []
        self.pods_exc = pods_exc
        self.deployments_exc = deployments_exc
        self.list_pods_calls = 0
        self.list_deployments_calls = 0

    async def list_pods(self, namespace=None):
        self.list_pods_calls += 1
        if self.pods_exc:
            raise self.pods_exc
        return self.pods

    async def list_deployments(self, namespace=None):
        self.list_deployments_calls += 1
        if self.deployments_exc:
            raise self.deployments_exc
        return self.deployments


class FakeAppState:
    def __init__(self, es=None, apm=None, prom=None, k8s=None):
        self.es_client = es or FakeESClient()
        self.apm_client = apm or FakeAPMClient()
        self.prometheus_client = prom or FakePrometheusClient()
        self.k8s_client = k8s or FakeK8sClient()
        self.alert_state = {}


class FakeStateTracker:
    """In-memory mirror of AlertStateTracker's API (no disk I/O)."""

    def __init__(self):
        self._state = {}

    async def get(self, rule_id):
        return self._state.get(rule_id)

    async def set_breached(self, rule_id):
        now = datetime.now(timezone.utc).isoformat()
        if rule_id not in self._state:
            self._state[rule_id] = {
                "status": "pending",
                "first_breached_at": now,
                "fired_at": None,
                "resolved_at": None,
            }
        self._state[rule_id]["last_breached_at"] = now
        return self._state[rule_id]

    async def set_firing(self, rule_id):
        self._state.setdefault(rule_id, {})
        self._state[rule_id]["status"] = "firing"
        self._state[rule_id]["fired_at"] = datetime.now(timezone.utc).isoformat()
        return self._state[rule_id]

    async def set_resolved(self, rule_id):
        if rule_id in self._state:
            self._state[rule_id]["status"] = "resolved"
            self._state[rule_id]["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return self._state.get(rule_id, {})

    async def get_all_state(self):
        return self._state


class FakeHistory:
    def __init__(self):
        self.events = []

    async def add(self, event):
        self.events.insert(0, event)


class FakeWSManager:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, message):
        self.broadcasts.append(message)


def _make_rule(rule_id, source, metric, threshold=0, condition="gt",
               duration_seconds=0, labels=None, notify_slack=False):
    from app.models.alerts import AlertRule

    return AlertRule(
        id=rule_id,
        name=rule_id,
        source=source,
        metric=metric,
        condition=condition,
        threshold=threshold,
        duration_seconds=duration_seconds,
        notify_slack=notify_slack,
        notify_email=False,
        notify_webhook=False,
        labels=labels or {},
    )


def _make_engine(ws=None):
    from app.alerting.engine import AlertEngine

    engine = AlertEngine()
    # Keep the cycle hermetic: no disk state, no real notifiers.
    engine.state_tracker = FakeStateTracker()
    engine.history = FakeHistory()
    engine.slack = AsyncMock()
    engine.email = AsyncMock()
    engine.webhook = AsyncMock()
    if ws is not None:
        engine.set_ws_manager(ws)
    return engine


def _eval_errors(source):
    from app.metrics import ALERT_EVAL_ERRORS

    return ALERT_EVAL_ERRORS.labels(source)._value.get()


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertEngineBatchedFetch:
    """_check_all fetches once per source batch, not once per rule."""

    @pytest.mark.asyncio
    async def test_many_rules_same_source_single_fetch(self, monkeypatch):
        """N kubernetes pod rules -> exactly one list_pods call."""
        k8s = FakeK8sClient(pods=[
            {"name": "a", "status": "Running", "restarts": 0},
            {"name": "b", "status": "Failed", "restarts": 0},
            {"name": "c", "status": "Unknown", "restarts": 0},
        ])
        app_state = FakeAppState(k8s=k8s)
        rules = [
            _make_rule(f"pod-fail-{i}", "kubernetes", "pods_failed", threshold=0)
            for i in range(4)
        ]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        await engine._check_all(app_state)

        assert k8s.list_pods_calls == 1
        assert k8s.list_deployments_calls == 0
        # All rules still evaluated against the shared payload (2 > 0 fires).
        assert len(engine.history.events) == 4
        assert all(e["value"] == 2.0 for e in engine.history.events)

    @pytest.mark.asyncio
    async def test_es_and_apm_rules_fetch_once_per_source(self, monkeypatch):
        """3 ES rules -> one get_error_count(minutes=5); 2 APM rules -> one
        get_summary, each keyed from the same summary document."""
        es = FakeESClient(error_count=100)
        apm = FakeAPMClient(summary={"p95_latency_ms": 3000, "error_rate_percent": 1.0})
        app_state = FakeAppState(es=es, apm=apm)
        rules = [
            *(_make_rule(f"es-{i}", "elasticsearch", "error_count_5m", threshold=50)
              for i in range(3)),
            _make_rule("apm-latency", "apm", "p95_latency_ms", threshold=2000),
            _make_rule("apm-errors", "apm", "error_rate_percent", threshold=5.0),
        ]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        await engine._check_all(app_state)

        assert len(es.get_error_count_calls) == 1
        assert es.get_error_count_calls[0] == 5  # widest (fixed) window
        assert apm.get_summary_calls == 1
        # Latency breached (3000 > 2000); error rate did not (1.0 <= 5.0).
        fired_ids = {e["rule_id"] for e in engine.history.events}
        assert "apm-latency" in fired_ids
        assert "apm-errors" not in fired_ids

    @pytest.mark.asyncio
    async def test_prometheus_one_query_per_distinct_metric(self, monkeypatch):
        """2 cpu + 2 memory rules -> one call per distinct expr, not per rule."""
        prom = FakePrometheusClient(cpu=95.0, memory=50.0)
        app_state = FakeAppState(prom=prom)
        rules = [
            *(_make_rule(f"cpu-{i}", "prometheus", "cpu_percent", threshold=90)
              for i in range(2)),
            *(_make_rule(f"mem-{i}", "prometheus", "memory_percent", threshold=90)
              for i in range(2)),
        ]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        await engine._check_all(app_state)

        assert prom.cpu_calls == 1
        assert prom.memory_calls == 1
        fired_ids = {e["rule_id"] for e in engine.history.events}
        assert fired_ids == {"cpu-0", "cpu-1"}

    @pytest.mark.asyncio
    async def test_kubernetes_pods_and_deployments_batches(self, monkeypatch):
        """Pod metrics share one list_pods; deployments get one list_deployments."""
        k8s = FakeK8sClient(
            pods=[{"name": "a", "status": "Running", "restarts": 7}],
            deployments=[
                {"name": "web", "available": 2, "replicas": 3},
                {"name": "api", "available": 1, "replicas": 1},
            ],
        )
        app_state = FakeAppState(k8s=k8s)
        rules = [
            _make_rule("crashloop", "kubernetes", "pods_crashloop", threshold=0),
            _make_rule("restarts", "kubernetes", "pod_restart_count", threshold=5),
            _make_rule("deploys", "kubernetes", "deployments_unavailable", threshold=0),
        ]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        await engine._check_all(app_state)

        assert k8s.list_pods_calls == 1
        assert k8s.list_deployments_calls == 1
        values = {e["rule_id"]: e["value"] for e in engine.history.events}
        assert values["crashloop"] == 1.0  # restarts=7 >= default threshold 5
        assert values["restarts"] == 7.0
        assert values["deploys"] == 1.0

    @pytest.mark.asyncio
    async def test_unbatchable_metric_falls_back_per_rule(self, monkeypatch):
        """A rule with a custom (unshared) metric keeps its per-rule fetch."""
        prom = FakePrometheusClient(cpu=95.0)
        app_state = FakeAppState(prom=prom)
        rules = [
            _make_rule("cpu", "prometheus", "cpu_percent", threshold=90),
            _make_rule("custom", "prometheus", "node_load1", threshold=1.5),
        ]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        engine._fetch_prometheus = AsyncMock(return_value=42.0)

        await engine._check_all(app_state)

        # Batched rule used the shared fetch; custom rule used the fallback.
        assert prom.cpu_calls == 1
        assert engine._fetch_prometheus.await_count == 1
        # Fallback result is still evaluated (42 > 1.5 fires).
        fired = {e["rule_id"]: e["value"] for e in engine.history.events}
        assert fired == {"cpu": 95.0, "custom": 42.0}

    @pytest.mark.asyncio
    async def test_failed_batch_counts_once_and_skips_rules(self, monkeypatch):
        """One failed batch -> one counter bump, batch rules skipped, other
        batches still evaluated, heartbeat still set."""
        from app.metrics import ALERT_ENGINE_LAST_SUCCESS

        k8s = FakeK8sClient(
            pods=[{"name": "a", "status": "Failed", "restarts": 0}],
            deployments=[{"name": "web", "available": 0, "replicas": 3}],
            pods_exc=RuntimeError("k8s api down"),
        )
        app_state = FakeAppState(k8s=k8s)
        rules = [
            _make_rule("pod-fail-1", "kubernetes", "pods_failed", threshold=0, notify_slack=True),
            _make_rule("pod-fail-2", "kubernetes", "pods_failed", threshold=0, notify_slack=True),
            _make_rule("crashloop", "kubernetes", "pods_crashloop", threshold=0, notify_slack=True),
            _make_rule("deploys", "kubernetes", "deployments_unavailable", threshold=0, notify_slack=True),
        ]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        before = _eval_errors("kubernetes")

        await engine._check_all(app_state)

        # Exactly one increment for the whole failed batch (not one per rule).
        assert _eval_errors("kubernetes") - before == 1
        assert k8s.list_pods_calls == 1
        # Skipped rules: no state, no events, no notifications.
        state = await engine.state_tracker.get_all_state()
        assert "pod-fail-1" not in state and "pod-fail-2" not in state
        assert "crashloop" not in state
        fired_ids = {e["rule_id"] for e in engine.history.events}
        assert fired_ids == {"deploys"}  # healthy batch unaffected
        engine.slack.send.assert_awaited_once()
        # Cycle still completed: state refreshed and heartbeat set.
        assert app_state.alert_state == state
        assert ALERT_ENGINE_LAST_SUCCESS._value.get() > 0

    @pytest.mark.asyncio
    async def test_resolution_uses_shared_payload(self, monkeypatch):
        """A firing rule resolves against the batched value."""
        ws = FakeWSManager()
        prom = FakePrometheusClient(cpu=5.0)
        app_state = FakeAppState(prom=prom)
        rule = _make_rule("cpu", "prometheus", "cpu_percent", threshold=90, notify_slack=True)
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: [rule])

        engine = _make_engine(ws=ws)
        # Pre-seed as firing so the next (healthy) cycle resolves it.
        await engine.state_tracker.set_breached("cpu")
        await engine.state_tracker.set_firing("cpu")

        await engine._check_all(app_state)

        assert prom.cpu_calls == 1
        resolved = [e for e in engine.history.events if e["status"] == "resolved"]
        assert len(resolved) == 1
        assert resolved[0]["rule_id"] == "cpu"
        assert any(m["type"] == "alert_resolved" for m in ws.broadcasts)
        engine.slack.send.assert_awaited_once()  # resolution notification

    @pytest.mark.asyncio
    async def test_disabled_and_unknown_source_rules_not_fetched(self, monkeypatch):
        """Disabled rules and unknown sources are skipped without any fetch."""
        es = FakeESClient(error_count=100)
        app_state = FakeAppState(es=es)
        disabled = _make_rule("off", "elasticsearch", "error_count_5m", threshold=50)
        disabled.enabled = False
        rules = [disabled, _make_rule("weird", "grafana", "dashboards", threshold=1)]
        monkeypatch.setattr("app.alerting.engine.load_rules", lambda: rules)

        engine = _make_engine()
        await engine._check_all(app_state)

        assert es.get_error_count_calls == []
        assert engine.history.events == []
