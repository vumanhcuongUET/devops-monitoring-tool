import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.alerting.rules import load_rules
from app.alerting.state import AlertStateTracker, AlertHistory
from app.alerting.notifiers import SlackNotifier, EmailNotifier, WebhookNotifier
from app.config import settings

logger = logging.getLogger(__name__)


class AlertEngine:
    def __init__(self):
        self.state_tracker = AlertStateTracker()
        self.history = AlertHistory()
        self.slack = SlackNotifier()
        self.email = EmailNotifier()
        self.webhook = WebhookNotifier()
        self._ws_manager = None
        self._running = False

    def set_ws_manager(self, manager):
        self._ws_manager = manager

    async def start(self, app_state):
        self._running = True
        app_state.alert_state = self.state_tracker.all_state()
        while self._running:
            try:
                await self._check_all(app_state)
            except Exception as e:
                logger.error("Alert check cycle failed: %s", e)
            await asyncio.sleep(settings.ALERT_CHECK_INTERVAL_SECONDS)

    def stop(self):
        self._running = False

    async def _check_all(self, app_state):
        rules = load_rules()
        metric_fetchers = {
            "elasticsearch": self._fetch_elasticsearch,
            "apm": self._fetch_apm,
            "prometheus": self._fetch_prometheus,
            "kubernetes": self._fetch_kubernetes,
        }

        for rule in rules:
            if not rule.enabled:
                continue
            fetcher = metric_fetchers.get(rule.source)
            if not fetcher:
                continue
            try:
                value = await fetcher(app_state, rule)
            except Exception:
                continue

            breached = self._evaluate(rule.condition, value, rule.threshold)

            if breached:
                state = self.state_tracker.set_breached(rule.id)
                if state.get("status") != "firing":
                    from datetime import datetime as dt
                    first = dt.fromisoformat(state["first_breached_at"])
                    elapsed = (dt.now(timezone.utc) - first).total_seconds()
                    if elapsed >= rule.duration_seconds:
                        await self._fire(rule, value)
            else:
                state = self.state_tracker.get(rule.id)
                if state and state.get("status") == "firing":
                    await self._resolve(rule, value)

        app_state.alert_state = self.state_tracker.all_state()

    def _evaluate(self, condition: str, value: float, threshold: float) -> bool:
        ops = {"gt": lambda v, t: v > t, "gte": lambda v, t: v >= t, "lt": lambda v, t: v < t, "lte": lambda v, t: v <= t, "eq": lambda v, t: v == t}
        op = ops.get(condition, lambda v, t: False)
        return op(value, threshold)

    async def _fire(self, rule, value: float):
        self.state_tracker.set_firing(rule.id)
        event = {
            "id": str(uuid.uuid4()),
            "rule_id": rule.id,
            "rule_name": rule.name,
            "severity": rule.severity.value,
            "status": "firing",
            "value": value,
            "threshold": rule.threshold,
            "message": f"{rule.name}: {rule.metric} is {value} (threshold: {rule.condition} {rule.threshold})",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.history.add(event)
        await self._notify(rule, event)
        if self._ws_manager:
            await self._ws_manager.broadcast({"type": "alert_fired", "data": event})

    async def _resolve(self, rule, value: float):
        self.state_tracker.set_resolved(rule.id)
        event = {
            "id": str(uuid.uuid4()),
            "rule_id": rule.id,
            "rule_name": rule.name,
            "severity": rule.severity.value,
            "status": "resolved",
            "value": value,
            "threshold": rule.threshold,
            "message": f"{rule.name}: resolved (current: {value})",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.history.add(event)
        await self._notify(rule, event)
        if self._ws_manager:
            await self._ws_manager.broadcast({"type": "alert_resolved", "data": event})

    async def _notify(self, rule, event: dict):
        if rule.notify_slack:
            await self.slack.send(event)
        if rule.notify_email:
            await self.email.send(event)
        if rule.notify_webhook:
            await self.webhook.send(event)

    async def _fetch_elasticsearch(self, app_state, rule) -> float:
        es = app_state.es_client
        if rule.metric == "error_count_5m":
            return float(await es.get_error_count(minutes=5))
        return 0.0

    async def _fetch_apm(self, app_state, rule) -> float:
        apm = app_state.apm_client
        summary = await apm.get_summary()
        return float(summary.get(rule.metric, 0))

    async def _fetch_prometheus(self, app_state, rule) -> float:
        prom = app_state.prometheus_client
        if rule.metric == "cpu_percent":
            return await prom.get_cpu_percent()
        if rule.metric == "memory_percent":
            return await prom.get_memory_percent()
        return 0.0

    async def _fetch_kubernetes(self, app_state, rule) -> float:
        k8s = app_state.k8s_client
        if rule.metric == "pods_failed":
            pods = await k8s.list_pods()
            return float(sum(1 for p in pods if p["status"] in ("Failed", "Unknown")))
        if rule.metric == "deployments_unavailable":
            deps = await k8s.list_deployments()
            return float(sum(1 for d in deps if d["available"] < d["replicas"]))
        return 0.0
