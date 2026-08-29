"""
Token Tracker - Monitor and track optimization metrics.

This module tracks all optimization requests, providing analytics
for monitoring and continuous improvement.

Phase 6: AI Input Optimization & Cost Efficiency
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class TokenTracker:
    """
    Enhanced tracking with querying capabilities (NEW for Day 5).

    Tracks optimization metrics to JSONL storage for analytics.
    """

    def __init__(
        self,
        storage_path: str = "data/optimization_metrics.jsonl"
    ):
        """
        Initialize token tracker.

        Args:
            storage_path: Path to JSONL storage file
        """
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def track_optimization(
        self,
        request_id: str,
        original_token_count: int,
        optimized_token_count: int,
        token_reduction_pct: float,
        processing_time_ms: float,
        strategies_applied: list[str],
        incident_type: str | None = None,
        severity: str | None = None,
        anomalies_detected: int = 0,
        logs_sampled: int = 0,
        metrics_compressed: bool = False,
        fallback: bool = False,
        fallback_reason: str | None = None
    ):
        """
        Track optimization metrics.

        Args:
            request_id: Unique request identifier
            original_token_count: Original token count
            optimized_token_count: Optimized token count
            token_reduction_pct: Percentage reduction achieved
            processing_time_ms: Processing time in milliseconds
            strategies_applied: List of strategies applied
            incident_type: Type of incident
            severity: Severity level
            anomalies_detected: Number of anomalies found
            logs_sampled: Number of logs sampled
            metrics_compressed: Whether metrics were compressed
            fallback: Whether fallback was used
            fallback_reason: Reason for fallback if used
        """
        metric = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'request_id': request_id,
            'incident_type': incident_type,
            'severity': severity,
            'original_token_count': original_token_count,
            'optimized_token_count': optimized_token_count,
            'token_reduction_pct': token_reduction_pct,
            'processing_time_ms': processing_time_ms,
            'strategies_applied': strategies_applied,
            'anomalies_detected': anomalies_detected,
            'logs_sampled': logs_sampled,
            'metrics_compressed': metrics_compressed,
            'fallback': fallback,
            'fallback_reason': fallback_reason
        }

        # Append to JSONL
        try:
            with open(self.storage_path, 'a') as f:
                f.write(json.dumps(metric) + '\n')
        except Exception as e:
            logger.error(f"Failed to write metrics: {e}")

    def get_stats(
        self,
        limit: int = 100,
        since: datetime | None = None
    ) -> dict:
        """
        Get statistics from tracked metrics.

        Args:
            limit: Maximum number of recent samples to return
            since: Only include metrics since this datetime

        Returns:
            {
                'total_optimizations': int,
                'avg_reduction_pct': float,
                'total_tokens_saved': int,
                'avg_processing_time_ms': float,
                'fallback_rate': float,
                'by_incident_type': dict,
                'by_severity': dict,
                'recent_sample': list
            }
        """
        metrics = self._load_metrics(since)

        if not metrics:
            return self._empty_stats()

        total = len(metrics)

        # Calculate averages
        reductions = [m['token_reduction_pct'] for m in metrics]
        avg_reduction = sum(reductions) / len(reductions)

        times = [m['processing_time_ms'] for m in metrics]
        avg_time = sum(times) / len(times)

        # Total savings
        total_saved = sum(
            m['original_token_count'] - m['optimized_token_count']
            for m in metrics
        )

        # Fallback rate
        fallback_count = sum(1 for m in metrics if m.get('fallback', False))
        fallback_rate = fallback_count / total if total > 0 else 0

        # Group by incident type
        by_type = self._group_by_field(metrics, 'incident_type')
        by_severity = self._group_by_field(metrics, 'severity')

        return {
            'total_optimizations': total,
            'avg_reduction_pct': round(avg_reduction, 2),
            'total_tokens_saved': total_saved,
            'avg_processing_time_ms': round(avg_time, 2),
            'fallback_rate': round(fallback_rate, 3),
            'by_incident_type': by_type,
            'by_severity': by_severity,
            'recent_sample': metrics[:limit]
        }

    def get_metrics(
        self,
        limit: int = 100,
        since: datetime | None = None
    ) -> list[dict]:
        """
        Get raw metrics from storage.

        Args:
            limit: Maximum number of metrics to return
            since: Only include metrics since this datetime

        Returns:
            List of metric dictionaries
        """
        return self._load_metrics(since)[:limit]

    def _load_metrics(self, since: datetime | None = None) -> list[dict]:
        """
        Load metrics from storage.

        Args:
            since: Only include metrics since this datetime

        Returns:
            List of metric dictionaries
        """
        if not self.storage_path.exists():
            return []

        metrics = []
        cutoff = since or datetime.now(timezone.utc) - timedelta(days=1)

        try:
            with open(self.storage_path, 'r') as f:
                for line in f:
                    try:
                        metric = json.loads(line.strip())

                        # Filter by time if specified
                        metric_time = datetime.fromisoformat(
                            metric['timestamp']
                        ).replace(tzinfo=timezone.utc)

                        if metric_time >= cutoff:
                            metrics.append(metric)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")

        return metrics

    def _group_by_field(self, metrics: list[dict], field: str) -> dict:
        """
        Group metrics by field.

        Args:
            metrics: List of metric dictionaries
            field: Field to group by

        Returns:
            Grouped statistics
        """
        grouped = {}

        for m in metrics:
            key = m.get(field, 'unknown')
            if key not in grouped:
                grouped[key] = {
                    'count': 0,
                    'avg_reduction': 0.0,
                    'total_savings': 0
                }

            grouped[key]['count'] += 1
            grouped[key]['avg_reduction'] += m['token_reduction_pct']
            grouped[key]['total_savings'] += (
                m['original_token_count'] - m['optimized_token_count']
            )

        # Calculate averages
        for key in grouped:
            if grouped[key]['count'] > 0:
                grouped[key]['avg_reduction'] = round(
                    grouped[key]['avg_reduction'] / grouped[key]['count'],
                    2
                )

        return grouped

    def _empty_stats(self) -> dict:
        """Return empty stats structure."""
        return {
            'total_optimizations': 0,
            'avg_reduction_pct': 0.0,
            'total_tokens_saved': 0,
            'avg_processing_time_ms': 0.0,
            'fallback_rate': 0.0,
            'by_incident_type': {},
            'by_severity': {},
            'recent_sample': []
        }

    def clear_old_metrics(self, retention_days: int = 30):
        """
        Clear metrics older than retention period.

        Args:
            retention_days: Number of days to retain
        """
        if not self.storage_path.exists():
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        try:
            # Read all metrics
            metrics = []
            with open(self.storage_path, 'r') as f:
                for line in f:
                    try:
                        metric = json.loads(line.strip())
                        metric_time = datetime.fromisoformat(
                            metric['timestamp']
                        ).replace(tzinfo=timezone.utc)

                        if metric_time >= cutoff:
                            metrics.append(metric)
                    except (json.JSONDecodeError, ValueError):
                        continue

            # Write back only recent metrics
            with open(self.storage_path, 'w') as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + '\n')

            logger.info(f"Cleared old metrics, kept {len(metrics)} records")
        except Exception as e:
            logger.error(f"Failed to clear old metrics: {e}")


# Singleton instance
_token_tracker: TokenTracker | None = None


def get_token_tracker(storage_path: str = "data/optimization_metrics.jsonl") -> TokenTracker:
    """Get or create the singleton TokenTracker instance."""
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenTracker(storage_path)
    return _token_tracker
