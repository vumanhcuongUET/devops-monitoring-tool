"""
Baseline Measurement Script - Measure current system performance.

This script establishes baseline metrics for token usage, accuracy,
and processing time before optimization is applied.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class BaselineMetrics:
    """Baseline performance metrics."""
    timestamp: str
    incident_id: str
    incident_type: str
    severity: str

    # Token metrics
    input_tokens: int
    output_tokens: int
    total_tokens: int

    # Performance metrics
    processing_time_ms: float
    context_collection_time_ms: float
    llm_generation_time_ms: float

    # Quality metrics (if available)
    finding_count: int = 0
    recommendation_count: int = 0
    confidence_score: float = 0.0

    # Context breakdown
    context_sources: List[str] = None
    context_sizes: Dict[str, int] = None

    def __post_init__(self):
        if self.context_sources is None:
            self.context_sources = []
        if self.context_sizes is None:
            self.context_sizes = {}


@dataclass
class BaselineSummary:
    """Summary of baseline measurements."""
    measurement_date: str
    total_incidents: int

    # Averages
    avg_input_tokens: float
    avg_output_tokens: float
    avg_total_tokens: float
    avg_processing_time_ms: float

    # Ranges
    min_input_tokens: int
    max_input_tokens: int
    min_processing_time_ms: float
    max_processing_time_ms: float

    # By incident type
    by_incident_type: Dict[str, Dict[str, float]] = None

    # By severity
    by_severity: Dict[str, Dict[str, float]] = None

    # Estimated costs
    estimated_monthly_cost_baseline: float = 0.0

    def __post_init__(self):
        if self.by_incident_type is None:
            self.by_incident_type = {}
        if self.by_severity is None:
            self.by_severity = {}


class BaselineMeasurer:
    """
    Measure baseline performance of current triage card generation.

    Establish metrics before optimization for comparison.
    """

    def __init__(self, output_dir: str = "data/baseline"):
        """Initialize baseline measurer."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.output_dir / "baseline_metrics.jsonl"
        self.summary_file = self.output_dir / "baseline_summary.json"

        # Claude API pricing (Sonnet 4)
        self.input_cost_per_1k_tokens = 0.003  # $3 per million
        self.output_cost_per_1k_tokens = 0.015  # $15 per million

    async def measure_incident(
        self,
        incident_id: str,
        incident_type: str,
        severity: str,
        context_data: Dict[str, Any],
        triage_generation_func
    ) -> BaselineMetrics:
        """
        Measure baseline for a single incident.

        Args:
            incident_id: Unique incident identifier
            incident_type: Type of incident
            severity: Severity level
            context_data: Raw context data
            triage_generation_func: Function to generate triage card

        Returns:
            BaselineMetrics with measurements
        """
        # Estimate input tokens
        input_tokens = self._estimate_tokens(context_data)

        # Measure context collection time
        context_start = time.time()

        # Simulate context collection (in real use, this would be actual collection)
        await asyncio.sleep(0.01)  # Simulate 10ms collection time

        context_time = (time.time() - context_start) * 1000

        # Measure triage generation time
        generation_start = time.time()

        try:
            triage_card = await triage_generation_func(context_data)

            generation_time = (time.time() - generation_start) * 1000

            # Extract metrics from triage card
            output_tokens = triage_card.get("tokens_used", self._estimate_tokens(triage_card))

            metrics = BaselineMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                incident_id=incident_id,
                incident_type=incident_type,
                severity=severity,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                processing_time_ms=context_time + generation_time,
                context_collection_time_ms=context_time,
                llm_generation_time_ms=generation_time,
                finding_count=len(triage_card.get("findings", [])),
                recommendation_count=len(triage_card.get("recommendations", [])),
                confidence_score=triage_card.get("confidence", 0.0),
                context_sources=list(context_data.keys()),
                context_sizes={k: self._estimate_tokens(v) for k, v in context_data.items()},
            )

            # Save to metrics file
            self._save_metrics(metrics)

            return metrics

        except Exception as e:
            generation_time = (time.time() - generation_start) * 1000
            # Return partial metrics on error
            return BaselineMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                incident_id=incident_id,
                incident_type=incident_type,
                severity=severity,
                input_tokens=input_tokens,
                output_tokens=0,
                total_tokens=input_tokens,
                processing_time_ms=context_time + generation_time,
                context_collection_time_ms=context_time,
                llm_generation_time_ms=generation_time,
            )

    def _estimate_tokens(self, data: Any) -> int:
        """
        Rough token estimation.

        Approximate: 1 token ≈ 4 characters
        """
        import json
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
            return len(text) // 4
        except Exception:
            return 0

    def _save_metrics(self, metrics: BaselineMetrics):
        """Append metrics to metrics file."""
        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(asdict(metrics)) + "\n")

    def generate_summary(self, min_samples: int = 10) -> BaselineSummary:
        """
        Generate summary from collected metrics.

        Args:
            min_samples: Minimum samples required for summary

        Returns:
            BaselineSummary with aggregated metrics
        """
        # Read all metrics
        metrics = self._read_metrics()

        if len(metrics) < min_samples:
            raise ValueError(
                f"Need at least {min_samples} samples, got {len(metrics)}"
            )

        # Calculate aggregates
        input_tokens = [m.input_tokens for m in metrics]
        output_tokens = [m.output_tokens for m in metrics]
        total_tokens = [m.total_tokens for m in metrics]
        processing_times = [m.processing_time_ms for m in metrics]

        # Group by incident type
        by_type = {}
        for m in metrics:
            if m.incident_type not in by_type:
                by_type[m.incident_type] = {
                    "count": 0,
                    "avg_input_tokens": 0,
                    "avg_processing_time_ms": 0,
                }
            by_type[m.incident_type]["count"] += 1
            by_type[m.incident_type]["avg_input_tokens"] += m.input_tokens
            by_type[m.incident_type]["avg_processing_time_ms"] += m.processing_time_ms

        # Calculate averages
        for incident_type in by_type:
            count = by_type[incident_type]["count"]
            by_type[incident_type]["avg_input_tokens"] /= count
            by_type[incident_type]["avg_processing_time_ms"] /= count

        # Group by severity
        by_severity = {}
        for m in metrics:
            if m.severity not in by_severity:
                by_severity[m.severity] = {
                    "count": 0,
                    "avg_input_tokens": 0,
                    "avg_processing_time_ms": 0,
                }
            by_severity[m.severity]["count"] += 1
            by_severity[m.severity]["avg_input_tokens"] += m.input_tokens
            by_severity[m.severity]["avg_processing_time_ms"] += m.processing_time_ms

        for severity in by_severity:
            count = by_severity[severity]["count"]
            by_severity[severity]["avg_input_tokens"] /= count
            by_severity[severity]["avg_processing_time_ms"] /= count

        # Estimate monthly cost (assuming 100 requests/day)
        avg_total = sum(total_tokens) / len(total_tokens)
        daily_cost = (
            (avg_total / 1000 * self.input_cost_per_1k_tokens) +
            ((avg_total * 0.3) / 1000 * self.output_cost_per_1k_tokens)  # ~30% output
        ) * 100
        monthly_cost = daily_cost * 30

        summary = BaselineSummary(
            measurement_date=datetime.now(timezone.utc).isoformat(),
            total_incidents=len(metrics),
            avg_input_tokens=sum(input_tokens) / len(input_tokens),
            avg_output_tokens=sum(output_tokens) / len(output_tokens),
            avg_total_tokens=sum(total_tokens) / len(total_tokens),
            avg_processing_time_ms=sum(processing_times) / len(processing_times),
            min_input_tokens=min(input_tokens),
            max_input_tokens=max(input_tokens),
            min_processing_time_ms=min(processing_times),
            max_processing_time_ms=max(processing_times),
            by_incident_type=by_type,
            by_severity=by_severity,
            estimated_monthly_cost_baseline=round(monthly_cost, 2),
        )

        # Save summary
        with open(self.summary_file, "w") as f:
            json.dump(asdict(summary), f, indent=2)

        return summary

    def _read_metrics(self) -> List[BaselineMetrics]:
        """Read all metrics from file."""
        metrics = []

        if not self.metrics_file.exists():
            return metrics

        with open(self.metrics_file, "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    metrics.append(BaselineMetrics(**data))
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"Warning: Failed to parse metrics line: {e}")

        return metrics

    def get_baseline_report(self) -> str:
        """Generate human-readable baseline report."""
        try:
            summary = self.generate_summary()
        except ValueError as e:
            return f"Cannot generate summary: {e}"

        report = f"""
# Baseline Measurement Report

**Measurement Date**: {summary.measurement_date}
**Total Incidents Measured**: {summary.total_incidents}

## Token Usage

| Metric | Value |
|--------|-------|
| Average Input Tokens | {summary.avg_input_tokens:.0f} |
| Average Output Tokens | {summary.avg_output_tokens:.0f} |
| Average Total Tokens | {summary.avg_total_tokens:.0f} |
| Input Token Range | {summary.min_input_tokens} - {summary.max_input_tokens} |

## Performance

| Metric | Value |
|--------|-------|
| Average Processing Time | {summary.avg_processing_time_ms:.0f} ms |
| Min Processing Time | {summary.min_processing_time_ms:.0f} ms |
| Max Processing Time | {summary.max_processing_time_ms:.0f} ms |

## Cost Estimate

- **Daily Cost (100 req/day)**: ${summary.estimated_monthly_cost_baseline / 30:.2f}
- **Monthly Cost**: ${summary.estimated_monthly_cost_baseline:.2f}

## By Incident Type

"""

        for incident_type, stats in summary.by_incident_type.items():
            report += f"### {incident_type}\n"
            report += f"- Count: {stats['count']}\n"
            report += f"- Avg Input Tokens: {stats['avg_input_tokens']:.0f}\n"
            report += f"- Avg Processing Time: {stats['avg_processing_time_ms']:.0f} ms\n\n"

        report += "## By Severity\n\n"

        for severity, stats in summary.by_severity.items():
            report += f"### {severity}\n"
            report += f"- Count: {stats['count']}\n"
            report += f"- Avg Input Tokens: {stats['avg_input_tokens']:.0f}\n"
            report += f"- Avg Processing Time: {stats['avg_processing_time_ms']:.0f} ms\n\n"

        return report


# Sample incident generator for testing
SAMPLE_INCIDENTS = [
    {
        "incident_id": "baseline-test-001",
        "incident_type": "high_latency",
        "severity": "high",
        "context": {
            "logs": [{"message": "API slow response"}] * 50,
            "apm": {"latency_p95_ms": 2300, "error_rate_percent": 2.5},
            "metrics": {"cpu_percent": 75.2, "memory_percent": 68.5},
            "kubernetes": {"pods_total": 10, "unhealthy_deployments": []},
            "alerts": [{"rule_name": "HighLatency", "severity": "high"}] * 5,
        }
    },
    {
        "incident_id": "baseline-test-002",
        "incident_type": "high_error_rate",
        "severity": "critical",
        "context": {
            "logs": [{"message": "Connection timeout error"}] * 50,
            "apm": {"latency_p95_ms": 500, "error_rate_percent": 15.2},
            "metrics": {"cpu_percent": 92.1, "memory_percent": 88.5},
            "kubernetes": {"pods_total": 8, "unhealthy_deployments": ["api"]},
            "alerts": [{"rule_name": "HighErrorRate", "severity": "critical"}] * 10,
        }
    },
]


async def main():
    """Run baseline measurement with sample incidents."""
    measurer = BaselineMeasurer()

    print("Running baseline measurement with sample incidents...")

    for incident in SAMPLE_INCIDENTS:
        # Mock triage generation function
        async def mock_triage_gen(context):
            await asyncio.sleep(0.5)  # Simulate LLM call
            return {
                "findings": [{"type": "root_cause"}] * 3,
                "recommendations": [{"action": "restart"}] * 2,
                "tokens_used": 1500,
                "confidence": 0.85,
            }

        metrics = await measurer.measure_incident(
            incident_id=incident["incident_id"],
            incident_type=incident["incident_type"],
            severity=incident["severity"],
            context_data=incident["context"],
            triage_generation_func=mock_triage_gen,
        )

        print(f"✅ Measured {incident['incident_id']}: {metrics.total_tokens} tokens")

    # Generate summary
    try:
        summary = measurer.generate_summary(min_samples=2)
        print(f"\n📊 Baseline Summary:")
        print(f"   Avg Input Tokens: {summary.avg_input_tokens:.0f}")
        print(f"   Avg Processing Time: {summary.avg_processing_time_ms:.0f} ms")
        print(f"   Est. Monthly Cost: ${summary.estimated_monthly_cost_baseline:.2f}")

        # Print report
        print("\n" + measurer.get_baseline_report())

    except ValueError as e:
        print(f"Cannot generate summary: {e}")


if __name__ == "__main__":
    asyncio.run(main())
