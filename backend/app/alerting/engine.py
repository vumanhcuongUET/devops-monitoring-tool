import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.actions.autonomous_executor import get_autonomous_executor
from app.alerting.notifiers import EmailNotifier, SlackNotifier, WebhookNotifier
from app.alerting.rules import load_rules
from app.alerting.state import AlertHistory, AlertStateTracker
from app.config import settings

logger = logging.getLogger(__name__)


class AlertEngine:
    def __init__(self, use_redis: bool = False):
        """
        Initialize alert engine.

        Args:
            use_redis: If True, use Redis-backed state; otherwise file-based
        """
        self.use_redis = use_redis

        if use_redis:
            from app.alerting.redis_store import RedisAlertHistory, RedisAlertStore

            # Build Redis URL from settings or use REDIS_URL if provided
            if settings.REDIS_URL:
                redis_url = settings.REDIS_URL
            else:
                password_part = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""
                redis_url = f"redis://{password_part}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB_ALERTS}"

            # Parse URL components for Redis client
            from urllib.parse import urlparse
            parsed = urlparse(redis_url if settings.REDIS_URL else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB_ALERTS}")

            self.state_tracker = RedisAlertStore(
                redis_host=parsed.hostname or settings.REDIS_HOST,
                redis_port=parsed.port or settings.REDIS_PORT,
                redis_password=parsed.password or settings.REDIS_PASSWORD,
                redis_db=settings.REDIS_DB_ALERTS,
            )
            self.history = RedisAlertHistory(
                redis_host=parsed.hostname or settings.REDIS_HOST,
                redis_port=parsed.port or settings.REDIS_PORT,
                redis_password=parsed.password or settings.REDIS_PASSWORD,
                redis_db=settings.REDIS_DB_ALERTS,
            )
        else:
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
        app_state.alert_state = await self.state_tracker.get_all_state()
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
                state = await self.state_tracker.set_breached(rule.id)

                if state.get("status") != "firing":
                    from datetime import datetime as dt
                    first = dt.fromisoformat(state["first_breached_at"])
                    elapsed = (dt.now(timezone.utc) - first).total_seconds()
                    if elapsed >= rule.duration_seconds:
                        await self._fire(rule, value)
            else:
                state = await self.state_tracker.get(rule.id)

                if state and state.get("status") == "firing":
                    await self._resolve(rule, value)

        app_state.alert_state = await self.state_tracker.get_all_state()

    def _evaluate(self, condition: str, value: float, threshold: float) -> bool:
        ops = {"gt": lambda v, t: v > t, "gte": lambda v, t: v >= t, "lt": lambda v, t: v < t, "lte": lambda v, t: v <= t, "eq": lambda v, t: v == t}
        op = ops.get(condition, lambda v, t: False)
        return op(value, threshold)

    async def _fire(self, rule, value: float):
        await self.state_tracker.set_firing(rule.id)

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

        await self.history.add(event)

        await self._notify(rule, event)
        if self._ws_manager:
            await self._ws_manager.broadcast({"type": "alert_fired", "data": event})

        # Phase 4: Trigger autonomous remediation if configured
        if rule.autonomous_action and rule.autonomous_action.get("enabled"):
            await self._trigger_autonomous_remediation(rule, event)

    async def _trigger_autonomous_remediation(self, rule, event: dict):
        """Trigger autonomous remediation action.

        Args:
            rule: Alert rule that triggered
            event: Alert event data
        """
        try:
            from app.config import settings
            from app.models.alerts import AlertEvent

            # Create AlertEvent model
            alert_event = AlertEvent(
                id=event["id"],
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                status=event["status"],
                value=event["value"],
                threshold=rule.threshold,
                message=event["message"],
                timestamp=event["timestamp"],
            )

            # Get environment from labels or default
            environment = rule.labels.get("environment", settings.ENVIRONMENT)

            # Get autonomous executor and execute action
            autonomous_executor = get_autonomous_executor()
            result = await autonomous_executor.execute_autonomous_action(
                alert_rule=rule,
                alert_event=alert_event,
                environment=environment,
                dry_run=rule.autonomous_action.get("dry_run", False),
            )

            if result.success:
                logger.info(
                    f"Autonomous remediation executed successfully: "
                    f"{rule.autonomous_action.get('action_type')} for {rule.name}"
                )
                # Broadcast success via WebSocket
                if self._ws_manager:
                    await self._ws_manager.broadcast({
                        "type": "autonomous_action_executed",
                        "data": {
                            "alert_event_id": event["id"],
                            "action_type": rule.autonomous_action.get("action_type"),
                            "success": True,
                            "message": result.stdout or "Action completed",
                        }
                    })
            else:
                logger.warning(
                    f"Autonomous remediation failed: {result.error_message}"
                )
                # Broadcast failure via WebSocket
                if self._ws_manager:
                    await self._ws_manager.broadcast({
                        "type": "autonomous_action_failed",
                        "data": {
                            "alert_event_id": event["id"],
                            "action_type": rule.autonomous_action.get("action_type"),
                            "success": False,
                            "error": result.error_message,
                        }
                    })

        except Exception as e:
            logger.error(f"Failed to trigger autonomous remediation: {e}")

    async def _resolve(self, rule, value: float):
        await self.state_tracker.set_resolved(rule.id)

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

        await self.history.add(event)

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
        if rule.metric == "pods_crashloop":
            # Enhanced: Detect CrashLoopBackOff by restart count
            pods = await k8s.list_pods()
            restart_threshold = rule.labels.get("restart_threshold", 5)
            crashloop_count = sum(
                1 for p in pods
                if p.get("restarts", 0) >= restart_threshold
                or p["status"] in ("CrashLoopBackOff", "Error")
            )
            return float(crashloop_count)
        if rule.metric == "pod_restart_count":
            # Total restart count across all pods
            pods = await k8s.list_pods()
            return float(sum(p.get("restarts", 0) for p in pods))
        if rule.metric == "deployments_unavailable":
            deps = await k8s.list_deployments()
            return float(sum(1 for d in deps if d["available"] < d["replicas"]))
        return 0.0
