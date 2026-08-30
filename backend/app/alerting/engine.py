import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from app.actions.autonomous_executor import get_autonomous_executor
from app.alerting.notifiers import EmailNotifier, SlackNotifier, WebhookNotifier
from app.alerting.rules import load_rules
from app.alerting.state import AlertHistory, AlertStateTracker
from app.config import settings
from app.metrics import ALERT_ENGINE_LAST_SUCCESS, ALERT_EVAL_ERRORS

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
        enabled = [r for r in rules if r.enabled]

        # ---- Fetch layer: one shared client call per (source, fetch key) ----
        # Previously every rule issued its own ES/APM/Prometheus/K8s request
        # each cycle. Now rules are grouped per source behind a shared fetch
        # (one ES error-count query, one APM summary, one Prometheus call per
        # distinct metric expr — cached per cycle — and one K8s list per pod /
        # deployment batch), and every rule in the group evaluates against the
        # shared payload. Rules whose metric cannot be expressed as a shared
        # query fall back to the per-rule fetchers below.
        groups: dict[tuple[str, str], list] = {}
        for rule in enabled:
            key = self._batch_key(rule)
            if key is None:
                continue  # not batchable -> per-rule fallback
            groups.setdefault((rule.source, key), []).append(rule)

        payloads: dict[tuple[str, str], object] = {}
        failed_batches: set[tuple[str, str]] = set()
        for group_key, group_rules in groups.items():
            try:
                payloads[group_key] = await self._fetch_shared(app_state, group_key)
            except Exception as e:
                # Phase 14 residual #2 semantics, batched: a failed fetch
                # must not look like "no data". One counter bump + one log
                # line per failed batch (same `source` label); every rule in
                # the batch is skipped this cycle.
                ALERT_EVAL_ERRORS.labels(group_key[0]).inc()
                logger.warning(
                    "Metric fetch failed for %d rule(s) (source=%s, fetch=%s): %s",
                    len(group_rules), group_key[0], group_key[1], e,
                )
                failed_batches.add(group_key)

        metric_fetchers = {
            "elasticsearch": self._fetch_elasticsearch,
            "apm": self._fetch_apm,
            "prometheus": self._fetch_prometheus,
            "kubernetes": self._fetch_kubernetes,
        }

        for rule in enabled:
            fetcher = metric_fetchers.get(rule.source)
            if not fetcher:
                continue
            key = self._batch_key(rule)
            if key is not None:
                group_key = (rule.source, key)
                if group_key in failed_batches:
                    continue  # already counted + logged once for the batch
                value = self._extract_value(rule, key, payloads[group_key])
            else:
                # Fallback: metric not expressible as a shared query.
                try:
                    value = await fetcher(app_state, rule)
                except Exception as e:
                    # Phase 14 residual #2: a failed fetch used to be a bare
                    # `continue` — rules silently going dark looked identical to
                    # "no data". Count it so alert_eval_errors_total can page.
                    ALERT_EVAL_ERRORS.labels(rule.source).inc()
                    logger.warning(
                        "Metric fetch failed for rule %s (source=%s): %s",
                        rule.id, rule.source, e,
                    )
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

        # Phase 14 residual #2 heartbeat: a completed cycle means the loop is
        # alive (per-rule fetch failures `continue` and don't abort the cycle
        # — ALERT_EVAL_ERRORS covers those separately). time_absent-style
        # alerting on this gauge detects a hung/cancelled engine.
        ALERT_ENGINE_LAST_SUCCESS.set(time.time())

    # Metrics each source can serve from one shared fetch per cycle.
    ES_ERROR_METRIC = "error_count_5m"
    PROM_METRICS = ("cpu_percent", "memory_percent")
    K8S_POD_METRICS = ("pods_failed", "pods_crashloop", "pod_restart_count")

    def _batch_key(self, rule) -> str | None:
        """Return the shared-fetch key for a rule, or None if the rule must
        keep its own per-rule fetch (fallback path).

        `metric` is read defensively — minimal rule stand-ins (tests, older
        serialized rules) may lack it, and an unbatchable rule must fall
        back, not crash the cycle."""
        metric = getattr(rule, "metric", None)
        if rule.source == "elasticsearch":
            # Single fixed-window error-count query covers every ES rule.
            return metric if metric == self.ES_ERROR_METRIC else None
        if rule.source == "apm":
            # Every APM metric is a key into one summary document.
            return "__summary__"
        if rule.source == "prometheus":
            # One query per distinct metric expr, cached for the cycle.
            return metric if metric in self.PROM_METRICS else None
        if rule.source == "kubernetes":
            if metric in self.K8S_POD_METRICS:
                return "list_pods"
            if metric == "deployments_unavailable":
                return "list_deployments"
            return None
        return None

    async def _fetch_shared(self, app_state, group_key: tuple[str, str]):
        """Fetch the shared payload for a (source, fetch key) batch."""
        source, key = group_key
        if source == "elasticsearch":
            es = app_state.es_client
            return float(await es.get_error_count(minutes=5))
        if source == "apm":
            apm = app_state.apm_client
            return await apm.get_summary()
        if source == "prometheus":
            prom = app_state.prometheus_client
            if key == "cpu_percent":
                return await prom.get_cpu_percent()
            if key == "memory_percent":
                return await prom.get_memory_percent()
        elif source == "kubernetes":
            k8s = app_state.k8s_client
            if key == "list_pods":
                return await k8s.list_pods()
            if key == "list_deployments":
                return await k8s.list_deployments()
        raise ValueError(f"Unknown fetch batch: source={source} key={key}")

    def _extract_value(self, rule, key: str, payload) -> float:
        """Derive a rule's metric value from the shared batch payload.

        Pure per-rule evaluation logic — identical expressions to the
        per-rule fetchers, just applied to shared data.
        """
        if rule.source == "elasticsearch":
            return float(payload)
        if rule.source == "apm":
            return float(payload.get(rule.metric, 0))
        if rule.source == "prometheus":
            return float(payload)
        if rule.source == "kubernetes":
            if key == "list_pods":
                pods = payload
                if rule.metric == "pods_failed":
                    return float(sum(1 for p in pods if p["status"] in ("Failed", "Unknown")))
                if rule.metric == "pods_crashloop":
                    # Enhanced: Detect CrashLoopBackOff by restart count
                    restart_threshold = rule.labels.get("restart_threshold", 5)
                    return float(sum(
                        1 for p in pods
                        if p.get("restarts", 0) >= restart_threshold
                        or p["status"] in ("CrashLoopBackOff", "Error")
                    ))
                if rule.metric == "pod_restart_count":
                    # Total restart count across all pods
                    return float(sum(p.get("restarts", 0) for p in pods))
            if key == "list_deployments":
                deps = payload
                return float(sum(1 for d in deps if d["available"] < d["replicas"]))
        raise ValueError(
            f"Cannot extract metric {rule.metric!r} from batch {rule.source}/{key}"
        )

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

            # Phase 14 security: environment is server-side truth. Rule
            # labels are client-influenced data and must never select the
            # execution environment.
            if "environment" in rule.labels:
                logger.warning(
                    "Rule %s carries labels.environment=%r — ignored; "
                    "using server ENVIRONMENT=%r",
                    rule.id, rule.labels["environment"], settings.ENVIRONMENT,
                )
            environment = settings.ENVIRONMENT

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
        # Phase 13 fencing: skip side effects if leadership was lost
        # mid-cycle (the wrapper only cancels between renew ticks).
        fence = getattr(self, "leadership", None)
        if fence is not None and not await fence.is_mine():
            logger.warning("Lost leadership — skipping notifications for %s", event.get("rule_name"))
            return
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
