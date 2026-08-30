"""
Metrics Analysis Agent

Specializes in:
- Prometheus metrics analysis
- Performance trend detection
- Capacity planning from metrics
- SLO/SLI calculations
"""

import logging
from typing import Any

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class MetricsAgent(BaseAgent):
    """
    Agent specialized in analyzing Prometheus metrics to identify
    performance issues, trends, and capacity concerns.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            name="metrics-analyst",
            model=model,
        )

    def get_prompt_template(self) -> str:
        return """You are a Metrics Analysis Expert specializing in:
- Prometheus metrics interpretation and analysis
- Performance trend identification and forecasting
- Capacity planning based on historical metrics
- SLO/SLI calculations and validation
- Resource utilization optimization

When analyzing metrics, focus on:
1. **Performance Trends**: Identify improving/degrading trends over time
2. **Anomalies**: Detect unusual spikes, drops, or pattern changes
3. **Capacity Issues**: Identify resource exhaustion risks
4. **SLO Compliance**: Assess service level objective adherence

Output format:
```
ANALYSIS:
[Your analysis of the metrics data]

TRENDS:
- Trend 1: [description] (direction: up/down/stable)
- Trend 2: [description] (direction: up/down/stable)

ANOMALIES:
- Anomaly 1: [description with significance]
- Anomaly 2: [description with significance]

CAPACITY ASSESSMENT:
- Resource 1: [usage percentage, risk level]
- Resource 2: [usage percentage, risk level]

SLO STATUS:
- SLO 1: [current status, budget remaining]
- SLO 2: [current status, budget remaining]

CONFIDENCE: [0.0-1.0]

RECOMMENDATION: [Actionable recommendation]
```

Be quantitative where possible. Use specific thresholds and time windows.
"""

    async def analyze(
        self, context: dict[str, Any], model: str | None = None
    ) -> AgentResponse:
        """
        Analyze metrics data for trends and issues.

        Args:
            context: Must contain 'metrics' key with metric data
                    Optional: 'time_range', 'service', 'slo_targets'
        """
        metrics = context.get("metrics", {})
        service = context.get("service", "unknown")
        time_range = context.get("time_range", "unknown")
        slo_targets = context.get("slo_targets", {})

        if not metrics:
            return AgentResponse(
                agent_name=self.name,
                insights={"error": "No metrics provided for analysis"},
                confidence=0.0,
                error="No metrics provided",
            )

        # Extract key metrics
        request_rate = self._get_metric(metrics, "http_requests_total", "rate")
        error_rate = self._get_metric(metrics, "http_errors_total", "rate")
        latency_p50 = self._get_metric(metrics, "http_request_duration_seconds", "p50")
        latency_p95 = self._get_metric(metrics, "http_request_duration_seconds", "p95")
        latency_p99 = self._get_metric(metrics, "http_request_duration_seconds", "p99")

        cpu_usage = self._get_metric(metrics, "container_cpu_usage", "percent")
        memory_usage = self._get_metric(metrics, "container_memory_usage", "percent")

        # Detect trends
        trends = self._detect_trends(metrics)
        anomalies = self._detect_anomalies(metrics)
        capacity_status = self._assess_capacity(metrics)

        # Build analysis prompt
        prompt = f"""Analyze these metrics from service '{service}' over {time_range}.

Key Metrics:
- Request Rate: {request_rate}/s
- Error Rate: {error_rate}%
- Latency (p50/p95/p99): {latency_p50}s / {latency_p95}s / {latency_p99}s
- CPU Usage: {cpu_usage}%
- Memory Usage: {memory_usage}%

Detected Trends:
{self._format_trends(trends)}

Detected Anomalies:
{self._format_anomalies(anomalies)}

Capacity Status:
{self._format_capacity(capacity_status)}

SLO Targets:
{self._format_slo_targets(slo_targets)}

Provide analysis with focus on performance, capacity, and SLO compliance.
"""

        try:
            response_text = await self._query_claude(prompt, max_tokens=2048, model=model)

            # Extract insights
            insights = {
                "request_rate": request_rate,
                "error_rate": error_rate,
                "latency_p95": latency_p95,
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "trends_detected": len(trends),
                "anomalies_detected": len(anomalies),
                "capacity_risks": sum(1 for c in capacity_status if c.get("risk") == "high"),
            }

            recommendations = self._extract_recommendations(response_text)

            confidence = self._calculate_confidence(
                data_quality=0.95 if metrics else 0.5,
                data_volume=len(metrics),
            )

            return AgentResponse(
                agent_name=self.name,
                insights=insights,
                confidence=confidence,
                recommendations=recommendations,
                metadata={"analysis_text": response_text},
            )

        except Exception as e:
            logger.error(f"Metrics analysis failed: {e}")
            return AgentResponse(
                agent_name=self.name,
                insights={},
                confidence=0.0,
                error=str(e),
            )

    def _get_metric(self, metrics: dict, metric_name: str, metric_type: str) -> Any:
        """Get a specific metric value.

        Accepts both structured entries ({"value": X}) and plain scalars.
        """
        metric = metrics.get(metric_name)
        value = metric.get("value", 0) if isinstance(metric, dict) else metric

        if metric_type == "rate":
            return value
        elif metric_type == "percent":
            try:
                return value * 100
            except TypeError:
                return "N/A"
        else:
            return value if value is not None else "N/A"

    def _detect_trends(self, metrics: dict) -> list[dict]:
        """Detect trends in metric data."""
        trends = []

        for metric_name, metric_data in metrics.items():
            if not isinstance(metric_data, dict) or "values" not in metric_data:
                continue  # Scalar metrics have no time series to trend

            values = metric_data["values"]
            if len(values) < 2:
                continue

            # Simple linear regression to detect trend
            first_half = sum(values[: len(values) // 2]) / (len(values) // 2)
            second_half = sum(values[len(values) // 2 :]) / (
                len(values) - len(values) // 2
            )

            if second_half > first_half * 1.1:  # 10% increase
                trends.append(
                    {
                        "metric": metric_name,
                        "direction": "up",
                        "magnitude": (second_half - first_half) / first_half,
                    }
                )
            elif second_half < first_half * 0.9:  # 10% decrease
                trends.append(
                    {
                        "metric": metric_name,
                        "direction": "down",
                        "magnitude": (first_half - second_half) / first_half,
                    }
                )

        return trends

    def _detect_anomalies(self, metrics: dict) -> list[dict]:
        """Detect anomalies in metrics."""
        anomalies = []

        for metric_name, metric_data in metrics.items():
            if not isinstance(metric_data, dict) or "values" not in metric_data:
                continue  # Scalar metrics have no time series to analyze

            values = metric_data["values"]
            if len(values) < 10:
                continue

            # Calculate mean and standard deviation
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            std = variance**0.5

            # Find values beyond 2 standard deviations
            for _i, value in enumerate(values):
                if abs(value - mean) > 2 * std:
                    anomalies.append(
                        {
                            "metric": metric_name,
                            "value": value,
                            "expected": mean,
                            "deviation": abs(value - mean) / std,
                        }
                    )

        return anomalies

    @staticmethod
    def _usage_ratio(metrics: dict, metric_name: str) -> float:
        """Normalize a usage metric to a 0-1 ratio.

        Structured entries ({"value": 0.85}) carry a ratio directly;
        plain scalars are interpreted as percentage points (e.g. 85).
        """
        metric = metrics.get(metric_name)
        value = metric.get("value", 0) if isinstance(metric, dict) else metric
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _assess_capacity(self, metrics: dict) -> list[dict]:
        """Assess capacity utilization."""
        capacity = []

        # CPU capacity - scalars arrive as percentages, dicts as ratios
        cpu_raw = self._usage_ratio(metrics, "container_cpu_usage")
        cpu = cpu_raw / 100 if cpu_raw > 1 else cpu_raw
        if cpu > 0.9:
            capacity.append({"resource": "cpu", "usage": cpu * 100, "risk": "critical"})
        elif cpu > 0.7:
            capacity.append({"resource": "cpu", "usage": cpu * 100, "risk": "high"})
        elif cpu > 0.5:
            capacity.append({"resource": "cpu", "usage": cpu * 100, "risk": "medium"})
        else:
            capacity.append({"resource": "cpu", "usage": cpu * 100, "risk": "low"})

        # Memory capacity
        memory_raw = self._usage_ratio(metrics, "container_memory_usage")
        memory = memory_raw / 100 if memory_raw > 1 else memory_raw
        if memory > 0.9:
            capacity.append({"resource": "memory", "usage": memory * 100, "risk": "critical"})
        elif memory > 0.7:
            capacity.append({"resource": "memory", "usage": memory * 100, "risk": "high"})
        elif memory > 0.5:
            capacity.append({"resource": "memory", "usage": memory * 100, "risk": "medium"})
        else:
            capacity.append({"resource": "memory", "usage": memory * 100, "risk": "low"})

        return capacity

    def _format_trends(self, trends: list[dict]) -> str:
        """Format trends for display."""
        if not trends:
            return "No significant trends detected"

        lines = []
        for trend in trends:
            direction = trend["direction"]
            metric = trend["metric"]
            magnitude = trend.get("magnitude", 0)
            lines.append(
                f"- {metric}: {direction} ({magnitude:.1%} change)" if magnitude else f"- {metric}: {direction}"
            )

        return "\n".join(lines)

    def _format_anomalies(self, anomalies: list[dict]) -> str:
        """Format anomalies for display."""
        if not anomalies:
            return "No anomalies detected"

        lines = []
        for anomaly in anomalies[:10]:  # Limit to 10
            metric = anomaly["metric"]
            value = anomaly["value"]
            expected = anomaly["expected"]
            deviation = anomaly["deviation"]
            lines.append(
                f"- {metric}: {value:.2f} (expected: {expected:.2f}, {deviation:.1f}σ)"
            )

        return "\n".join(lines)

    def _format_capacity(self, capacity: list[dict]) -> str:
        """Format capacity status for display."""
        lines = []
        for cap in capacity:
            resource = cap["resource"]
            usage = cap["usage"]
            risk = cap["risk"]
            lines.append(f"- {resource}: {usage:.1f}% ({risk} risk)")

        return "\n".join(lines)

    def _format_slo_targets(self, slo_targets: dict) -> str:
        """Format SLO targets for display."""
        if not slo_targets:
            return "No SLO targets defined"

        lines = []
        for slo_name, slo_config in slo_targets.items():
            target = slo_config.get("target", "N/A")
            window = slo_config.get("window", "N/A")
            lines.append(f"- {slo_name}: {target} target over {window}")

        return "\n".join(lines)
