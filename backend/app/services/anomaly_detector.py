"""
Anomaly Detector Service - Detect and filter anomalous metrics.

This module identifies metrics that deviate from normal ranges,
allowing the system to focus on actionable data.

Phase 6: AI Input Optimization & Cost Efficiency
Enhanced for Day 2: Support 6 metric types with adaptive thresholds
"""

from typing import Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import asyncio


@dataclass
class AnomalyThresholds:
    """Thresholds for anomaly detection."""
    cpu_high: float = 80.0
    cpu_low: float = 20.0
    memory_high: float = 85.0
    disk_high: float = 90.0
    error_rate_high: float = 5.0

    # Network I/O thresholds (multipliers for baseline)
    network_io_high_multiplier: float = 3.0
    network_io_critical_multiplier: float = 5.0

    # Disk I/O thresholds (multipliers for baseline)
    disk_io_high_multiplier: float = 3.0
    disk_io_critical_multiplier: float = 5.0


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    is_anomalous: bool
    metric_name: str
    value: float
    threshold: float
    reason: str
    severity: str = "high"  # low, medium, high, critical
    baseline_value: float = 0.0
    deviation_pct: float = 0.0


class AnomalyDetector:
    """
    Detect anomalous metrics to filter normal data.

    Enhanced for Day 2 with 6 metric types:
    - CPU, Memory, Disk (original)
    - Network I/O (new)
    - Disk I/O (new)
    - Error Rate (new)

    Only metrics exceeding thresholds are included in optimized context,
    significantly reducing token usage for healthy systems.
    """

    def __init__(self, config):
        """Initialize anomaly detector with configuration."""
        self.thresholds = AnomalyThresholds(
            cpu_high=config.anomaly_cpu_high,
            cpu_low=config.anomaly_cpu_low,
            memory_high=config.anomaly_memory_high,
            disk_high=config.anomaly_disk_high,
            error_rate_high=config.anomaly_error_rate_high,
            network_io_high_multiplier=getattr(config, 'anomaly_network_io_high_multiplier', 3.0),
            network_io_critical_multiplier=getattr(config, 'anomaly_network_io_critical_multiplier', 5.0),
            disk_io_high_multiplier=getattr(config, 'anomaly_disk_io_high_multiplier', 3.0),
            disk_io_critical_multiplier=getattr(config, 'anomaly_disk_io_critical_multiplier', 5.0),
        )

        # For adaptive thresholds (Day 2 enhancement)
        self.historical_metrics = {}
        self.baseline_window = 10  # Number of samples for baseline

    async def detect_metrics_anomaly(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Detect and filter anomalous metrics.

        Args:
            metrics: Raw metrics dictionary

        Returns:
            Filtered metrics with only anomalous values + summary for normal
        """
        if not metrics:
            return {"status": "no_metrics_available"}

        result = {}
        anomalies = []
        normal_count = 0

        # Check CPU (existing)
        if "cpu_percent" in metrics:
            cpu = metrics["cpu_percent"]
            if cpu >= self.thresholds.cpu_high or cpu <= self.thresholds.cpu_low:
                result["cpu_percent"] = cpu
                anomalies.append(AnomalyResult(
                    is_anomalous=True,
                    metric_name="cpu_percent",
                    value=cpu,
                    threshold=self.thresholds.cpu_high,
                    reason=f"CPU {'high' if cpu >= self.thresholds.cpu_high else 'low'}",
                    severity="critical" if cpu >= 90 else "high"
                ))
            else:
                normal_count += 1

        # Check Memory (existing)
        if "memory_percent" in metrics:
            memory = metrics["memory_percent"]
            if memory >= self.thresholds.memory_high:
                result["memory_percent"] = memory
                anomalies.append(AnomalyResult(
                    is_anomalous=True,
                    metric_name="memory_percent",
                    value=memory,
                    threshold=self.thresholds.memory_high,
                    reason="Memory high",
                    severity="critical" if memory >= 95 else "high"
                ))
            else:
                normal_count += 1

        # Check Disk usage (existing)
        if "disk_percent" in metrics:
            disk = metrics["disk_percent"]
            if disk >= self.thresholds.disk_high:
                result["disk_percent"] = disk
                anomalies.append(AnomalyResult(
                    is_anomalous=True,
                    metric_name="disk_percent",
                    value=disk,
                    threshold=self.thresholds.disk_high,
                    reason="Disk usage high",
                    severity="critical" if disk >= 95 else "high"
                ))
            else:
                normal_count += 1

        # NEW: Check Network I/O (Day 2)
        network_anomalies = await self._detect_network_io_anomaly(metrics)
        if network_anomalies:
            anomalies.extend(network_anomalies)
            result["_network_io_anomaly"] = [a.__dict__ for a in network_anomalies]

        # NEW: Check Disk I/O (Day 2)
        disk_io_anomalies = await self._detect_disk_io_anomaly(metrics)
        if disk_io_anomalies:
            anomalies.extend(disk_io_anomalies)
            result["_disk_io_anomaly"] = [a.__dict__ for a in disk_io_anomalies]

        # NEW: Check Error Rate (Day 2)
        if "error_rate" in metrics:
            error_rate = metrics["error_rate"]
            if error_rate >= self.thresholds.error_rate_high:
                result["error_rate"] = error_rate
                anomalies.append(AnomalyResult(
                    is_anomalous=True,
                    metric_name="error_rate",
                    value=error_rate,
                    threshold=self.thresholds.error_rate_high,
                    reason="Error rate high",
                    severity="critical" if error_rate >= 10 else "high"
                ))
            else:
                normal_count += 1

        # Add summary for normal metrics
        if normal_count > 0 and not anomalies:
            result["_summary"] = "All metrics within normal range"
        elif normal_count > 0:
            result["_normal_metrics_count"] = normal_count

        # Add anomaly details for debugging
        if anomalies:
            result["_anomalies"] = [
                {
                    "metric": a.metric_name,
                    "value": a.value,
                    "threshold": a.threshold,
                    "reason": a.reason,
                    "severity": a.severity
                }
                for a in anomalies
            ]

        return result

    async def _detect_network_io_anomaly(self, metrics: dict[str, Any]) -> List[AnomalyResult]:
        """
        Detect network I/O anomalies (NEW for Day 2).

        Anomaly if current > 3x baseline (high) or 5x baseline (critical)

        Returns:
            List of AnomalyResult objects
        """
        anomalies = []

        # Check network input
        if "network_in_bytes" in metrics:
            current_in = metrics["network_in_bytes"]
            baseline_in = self._get_baseline("network_in_bytes")

            if baseline_in > 0:
                ratio_in = current_in / baseline_in
                if ratio_in >= self.thresholds.network_io_critical_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="network_in_bytes",
                        value=current_in,
                        threshold=baseline_in * self.thresholds.network_io_critical_multiplier,
                        reason=f"Network input spike: {ratio_in:.1f}x baseline",
                        severity="critical"
                    ))
                elif ratio_in >= self.thresholds.network_io_high_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="network_in_bytes",
                        value=current_in,
                        threshold=baseline_in * self.thresholds.network_io_high_multiplier,
                        reason=f"Network input elevated: {ratio_in:.1f}x baseline",
                        severity="high"
                    ))

        # Check network output
        if "network_out_bytes" in metrics:
            current_out = metrics["network_out_bytes"]
            baseline_out = self._get_baseline("network_out_bytes")

            if baseline_out > 0:
                ratio_out = current_out / baseline_out
                if ratio_out >= self.thresholds.network_io_critical_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="network_out_bytes",
                        value=current_out,
                        threshold=baseline_out * self.thresholds.network_io_critical_multiplier,
                        reason=f"Network output spike: {ratio_out:.1f}x baseline",
                        severity="critical"
                    ))
                elif ratio_out >= self.thresholds.network_io_high_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="network_out_bytes",
                        value=current_out,
                        threshold=baseline_out * self.thresholds.network_io_high_multiplier,
                        reason=f"Network output elevated: {ratio_out:.1f}x baseline",
                        severity="high"
                    ))

        return anomalies

    async def _detect_disk_io_anomaly(self, metrics: dict[str, Any]) -> List[AnomalyResult]:
        """
        Detect disk I/O anomalies (NEW for Day 2).

        Anomaly if current > 3x baseline (high) or 5x baseline (critical)

        Returns:
            List of AnomalyResult objects
        """
        anomalies = []

        # Check disk read I/O
        if "disk_read_bytes" in metrics:
            current_read = metrics["disk_read_bytes"]
            baseline_read = self._get_baseline("disk_read_bytes")

            if baseline_read > 0:
                ratio_read = current_read / baseline_read
                if ratio_read >= self.thresholds.disk_io_critical_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="disk_read_bytes",
                        value=current_read,
                        threshold=baseline_read * self.thresholds.disk_io_critical_multiplier,
                        reason=f"Disk read spike: {ratio_read:.1f}x baseline",
                        severity="critical"
                    ))
                elif ratio_read >= self.thresholds.disk_io_high_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="disk_read_bytes",
                        value=current_read,
                        threshold=baseline_read * self.thresholds.disk_io_high_multiplier,
                        reason=f"Disk read elevated: {ratio_read:.1f}x baseline",
                        severity="high"
                    ))

        # Check disk write I/O
        if "disk_write_bytes" in metrics:
            current_write = metrics["disk_write_bytes"]
            baseline_write = self._get_baseline("disk_write_bytes")

            if baseline_write > 0:
                ratio_write = current_write / baseline_write
                if ratio_write >= self.thresholds.disk_io_critical_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="disk_write_bytes",
                        value=current_write,
                        threshold=baseline_write * self.thresholds.disk_io_critical_multiplier,
                        reason=f"Disk write spike: {ratio_write:.1f}x baseline",
                        severity="critical"
                    ))
                elif ratio_write >= self.thresholds.disk_io_high_multiplier:
                    anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name="disk_write_bytes",
                        value=current_write,
                        threshold=baseline_write * self.thresholds.disk_io_high_multiplier,
                        reason=f"Disk write elevated: {ratio_write:.1f}x baseline",
                        severity="high"
                    ))

        return anomalies

    def _get_baseline(self, metric_name: str) -> float:
        """
        Get baseline value for a metric.

        Uses historical data to calculate baseline.
        Returns 1.0 if no baseline available (to avoid division by zero).
        """
        if metric_name in self.historical_metrics:
            values = self.historical_metrics[metric_name]
            if values:
                return sum(values) / len(values)
        return 1.0

    def update_historical_metrics(self, metrics: dict[str, Any]):
        """
        Update historical metrics for adaptive baseline calculation.

        Args:
            metrics: Current metrics to add to history
        """
        for metric_name, value in metrics.items():
            if isinstance(value, (int, float)):
                if metric_name not in self.historical_metrics:
                    self.historical_metrics[metric_name] = []

                self.historical_metrics[metric_name].append(value)

                # Keep only the most recent values
                if len(self.historical_metrics[metric_name]) > self.baseline_window:
                    self.historical_metrics[metric_name].pop(0)

    def detect_all(self, metrics: List[dict]) -> List[AnomalyResult]:
        """
        Detect anomalies across all metric types in a list of metrics.

        Args:
            metrics: List of metric dictionaries

        Returns:
            List of all detected anomalies
        """
        all_anomalies = []

        for metric_dict in metrics:
            result = asyncio.run(self.detect_metrics_anomaly(metric_dict))
            if "_anomalies" in result:
                for anomaly_data in result["_anomalies"]:
                    all_anomalies.append(AnomalyResult(
                        is_anomalous=True,
                        metric_name=anomaly_data["metric"],
                        value=anomaly_data["value"],
                        threshold=anomaly_data["threshold"],
                        reason=anomaly_data["reason"],
                        severity=anomaly_data.get("severity", "high")
                    ))

        return all_anomalies

    # ========== Day 2: Adaptive Thresholds ==========

    def calculate_baseline(self, historical_metrics: List[dict]) -> dict:
        """
        Calculate dynamic baseline from historical data (NEW for Day 2).

        Returns:
            {
                'cpu': {'mean': 45.2, 'std': 12.3, 'p95': 68.5},
                'memory': {'mean': 62.1, 'std': 8.4, 'p95': 75.0},
                ...
            }
        """
        baselines = {}

        # Group by metric name
        metric_values = {}
        for metric in historical_metrics:
            for key, value in metric.items():
                if isinstance(value, (int, float)):
                    if key not in metric_values:
                        metric_values[key] = []
                    metric_values[key].append(value)

        # Calculate statistics for each metric
        for metric_name, values in metric_values.items():
            if len(values) >= 3:  # Need minimum samples
                baselines[metric_name] = self._calculate_statistics(values)

        return baselines

    def _calculate_statistics(self, values: List[float]) -> dict:
        """Calculate comprehensive statistics from values."""
        arr = np.array(values)

        return {
            'mean': float(np.mean(arr)),
            'std': float(np.std(arr)),
            'min': float(np.min(arr)),
            'max': float(np.max(arr)),
            'p50': float(np.percentile(arr, 50)),
            'p90': float(np.percentile(arr, 90)),
            'p95': float(np.percentile(arr, 95)),
            'count': len(arr)
        }

    def detect_with_baseline(self, current: dict, baseline: dict) -> List[AnomalyResult]:
        """
        Detect anomalies using calculated baseline (NEW for Day 2).

        Anomaly if:
        - current > baseline[p95] + 2*std (high)
        - current > baseline[p95] + 3*std (critical)
        - OR current > mean * 1.2 (high), mean * 1.3 (critical) for uniform data

        Returns:
            List of AnomalyResult objects
        """
        anomalies = []

        for metric_type, current_value in current.items():
            if not isinstance(current_value, (int, float)):
                continue

            if metric_type not in baseline:
                continue

            metric_baseline = baseline[metric_type]

            # Calculate threshold with minimum variance for uniform data
            std = max(metric_baseline['std'], metric_baseline['mean'] * 0.05)  # At least 5% variance
            upper_bound = metric_baseline['p95'] + (2 * std)
            critical_bound = metric_baseline['p95'] + (3 * std)

            # Also use percentage-based threshold as fallback
            percent_high = metric_baseline['mean'] * 1.2
            percent_critical = metric_baseline['mean'] * 1.3

            # Use more lenient threshold
            upper_bound = max(upper_bound, percent_high)
            critical_bound = max(critical_bound, percent_critical)

            if current_value > critical_bound:
                anomalies.append(AnomalyResult(
                    is_anomalous=True,
                    metric_name=metric_type,
                    value=current_value,
                    baseline_value=metric_baseline['mean'],
                    threshold=critical_bound,
                    deviation_pct=((current_value - metric_baseline['mean']) / metric_baseline['mean']) * 100 if metric_baseline['mean'] > 0 else 0,
                    reason=f"Critical deviation from baseline",
                    severity="critical"
                ))
            elif current_value > upper_bound:
                anomalies.append(AnomalyResult(
                    is_anomalous=True,
                    metric_name=metric_type,
                    value=current_value,
                    baseline_value=metric_baseline['mean'],
                    threshold=upper_bound,
                    deviation_pct=((current_value - metric_baseline['mean']) / metric_baseline['mean']) * 100 if metric_baseline['mean'] > 0 else 0,
                    reason=f"High deviation from baseline",
                    severity="high"
                ))

        return anomalies

    # ========== Day 2: Anomaly Scoring ==========

    def score_anomaly(self, metric: str, current: float, baseline: dict) -> 'AnomalyScore':
        """
        Calculate comprehensive anomaly score (NEW for Day 2).

        Severity Classification:
        - low: deviation 20-50%, confidence <0.7
        - medium: deviation 50-100%, confidence 0.7-0.8
        - high: deviation 100-200%, confidence 0.8-0.9
        - critical: deviation >200%, confidence >0.9

        Returns:
            AnomalyScore with detailed breakdown
        """
        baseline_mean = baseline.get('mean', 0)
        baseline_std = baseline.get('std', 0)

        if baseline_mean == 0:
            deviation_pct = 0
            confidence = 0.0
        else:
            deviation_pct = abs((current - baseline_mean) / baseline_mean) * 100
            # Higher confidence with more data points and lower std
            confidence = min(0.9, baseline.get('count', 0) / 30.0)
            if baseline_std > 0:
                confidence *= min(1.0, baseline_mean / baseline_std)

        # Determine severity
        if deviation_pct > 200:
            severity = "critical"
        elif deviation_pct > 100:
            severity = "high"
        elif deviation_pct > 50:
            severity = "medium"
        elif deviation_pct > 20:
            severity = "low"
        else:
            severity = "none"

        return AnomalyScore(
            metric_name=metric,
            current_value=current,
            baseline_value=baseline_mean,
            deviation_percent=deviation_pct,
            severity=severity,
            confidence=confidence,
            timestamp=datetime.now()
        )

    def is_metric_anomalous(
        self,
        metric_name: str,
        value: float
    ) -> bool:
        """
        Check if a single metric value is anomalous.

        Args:
            metric_name: Name of the metric
            value: Metric value

        Returns:
            True if metric is anomalous
        """
        if metric_name == "cpu_percent":
            return value >= self.thresholds.cpu_high or value <= self.thresholds.cpu_low
        elif metric_name == "memory_percent":
            return value >= self.thresholds.memory_high
        elif metric_name == "disk_percent":
            return value >= self.thresholds.disk_high
        elif metric_name == "error_rate":
            return value >= self.thresholds.error_rate_high
        return False

    def get_threshold(self, metric_name: str) -> Optional[float]:
        """Get threshold for a specific metric."""
        if metric_name == "cpu_percent":
            return self.thresholds.cpu_high
        elif metric_name == "memory_percent":
            return self.thresholds.memory_high
        elif metric_name == "disk_percent":
            return self.thresholds.disk_high
        elif metric_name == "error_rate":
            return self.thresholds.error_rate_high
        return None


@dataclass
class AnomalyScore:
    """Detailed anomaly scoring with severity classification (NEW for Day 2)."""
    metric_name: str
    current_value: float
    baseline_value: float
    deviation_percent: float
    severity: str  # low, medium, high, critical
    confidence: float  # 0.0 to 1.0
    timestamp: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'metric': self.metric_name,
            'current': self.current_value,
            'baseline': self.baseline_value,
            'deviation_percent': self.deviation_percent,
            'severity': self.severity,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat()
        }
