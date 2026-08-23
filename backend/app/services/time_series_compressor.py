"""
Time Series Compressor Service - Compress time-series data to key statistics.

This module converts raw time-series data into percentile-based summaries,
reducing token usage by ~90% while preserving trends and outliers.

Phase 6: AI Input Optimization & Cost Efficiency
Enhanced for Day 4: Advanced trend detection and compression
"""

from typing import Any, List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np


class Trend(str, Enum):
    """Trend states (NEW for Day 4)."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class CompressionResult:
    """Result of time-series compression."""
    original_points: int
    compressed_values: int
    compression_ratio: float
    statistics: dict


@dataclass
class PercentileStats:
    """Percentile-based statistics."""
    current: float
    p50: float  # Median
    p90: float
    p95: float
    p99: float
    min: float
    max: float
    mean: float
    std: float  # Volatility
    trend: str  # increasing, decreasing, stable


class TimeSeriesCompressor:
    """
    Compress time-series data to key statistics.

    Replaces hundreds of data points with ~8 key values:
    - Current value
    - Percentiles (p50, p90, p95, p99)
    - Min, Max
    - Mean, Std (volatility)
    - Trend indicator

    Token savings: ~90% for time-series data
    """

    def __init__(self, config):
        """Initialize compressor with configuration."""
        self.include_percentiles = config.include_percentiles
        self.include_trend = config.include_trend

    async def compress_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Compress all time-series data in metrics dict.

        Args:
            metrics: Raw metrics dictionary with potential time-series

        Returns:
            Metrics with compressed time-series
        """
        if not metrics:
            return metrics

        result = {}

        # Process each metric
        for key, value in metrics.items():
            if isinstance(value, list) and self._is_time_series(value):
                # Compress time-series data
                result[key] = self._compress_time_series(value)
            elif isinstance(value, dict):
                # Recursively process nested dicts
                result[key] = await self.compress_metrics(value)
            else:
                # Keep scalar values as-is
                result[key] = value

        return result

    async def compress_single_series(
        self,
        data_points: List[tuple],
        metric_name: str = "unknown"
    ) -> CompressionResult:
        """
        Compress a single time-series.

        Args:
            data_points: List of (timestamp, value) tuples
            metric_name: Name of the metric

        Returns:
            CompressionResult with statistics
        """
        if not data_points:
            return CompressionResult(
                original_points=0,
                compressed_values=0,
                compression_ratio=0.0,
                statistics={}
            )

        # Extract values
        values = [float(v[1]) for v in data_points if v[1] is not None]

        if not values:
            return CompressionResult(
                original_points=len(data_points),
                compressed_values=0,
                compression_ratio=0.0,
                statistics={}
            )

        # Calculate statistics
        stats = self._calculate_percentiles(values)

        return CompressionResult(
            original_points=len(data_points),
            compressed_values=len(stats.__dict__),
            compression_ratio=len(data_points) / len(stats.__dict__),
            statistics=stats.__dict__
        )

    def _is_time_series(self, value: list) -> bool:
        """Check if list is time-series data."""
        if not value or len(value) < 2:
            return False

        # Check if elements are tuples/lists with 2+ items
        first_element = value[0]
        if isinstance(first_element, (tuple, list)):
            return len(first_element) >= 2

        return False

    def _compress_time_series(self, data_points: List[tuple]) -> dict:
        """
        Compress time-series to percentile statistics.

        Args:
            data_points: List of (timestamp, value) tuples

        Returns:
            Dictionary with compressed statistics
        """
        # Extract values
        values = [float(v[1]) for v in data_points if v[1] is not None]

        if not values:
            return {"error": "No valid data points"}

        stats = self._calculate_percentiles(values)

        result = {
            "current": stats.current,
            "p50": stats.p50,
            "p90": stats.p90,
            "p95": stats.p95,
            "p99": stats.p99,
            "min": stats.min,
            "max": stats.max,
            "mean": stats.mean,
            "std": stats.std,
            "trend": stats.trend,
            "samples": len(values),
        }

        return result

    def _calculate_percentiles(self, values: List[float]) -> PercentileStats:
        """Calculate percentile statistics from values."""
        if not values:
            return PercentileStats(
                current=0.0, p50=0.0, p90=0.0, p95=0.0, p99=0.0,
                min=0.0, max=0.0, mean=0.0, std=0.0, trend="stable"
            )

        try:
            values_array = np.array(values)

            current = float(values[-1])
            p50 = float(np.percentile(values_array, 50))
            p90 = float(np.percentile(values_array, 90))
            p95 = float(np.percentile(values_array, 95))
            p99 = float(np.percentile(values_array, 99))
            min_val = float(np.min(values_array))
            max_val = float(np.max(values_array))
            mean_val = float(np.mean(values_array))
            std_val = float(np.std(values_array))

            # Determine trend
            if len(values) >= 2:
                first_val = values[0]
                if current > first_val * 1.1:  # 10% increase
                    trend = "increasing"
                elif current < first_val * 0.9:  # 10% decrease
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"

            return PercentileStats(
                current=current,
                p50=p50,
                p90=p90,
                p95=p95,
                p99=p99,
                min=min_val,
                max=max_val,
                mean=mean_val,
                std=std_val,
                trend=trend
            )
        except Exception:
            # Fallback if numpy fails
            return PercentileStats(
                current=values[-1],
                p50=values[-1],
                p90=values[-1],
                p95=values[-1],
                p99=values[-1],
                min=min(values),
                max=max(values),
                mean=sum(values) / len(values),
                std=0.0,
                trend="stable"
            )

    def get_compression_summary(self, original_size: int, compressed_size: int) -> dict:
        """Get summary of compression operation."""
        if original_size == 0:
            return {"error": "No data to compress"}

        ratio = original_size / compressed_size if compressed_size > 0 else 0
        reduction_percent = ((original_size - compressed_size) / original_size * 100)

        return {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": round(ratio, 1),
            "reduction_percent": round(reduction_percent, 1),
            "token_savings_estimated": round(reduction_percent * 0.9, 1),  # ~90% savings
        }

    def format_for_llm(self, stats: PercentileStats, metric_name: str) -> str:
        """
        Format statistics for LLM prompt.

        Returns compact string representation.
        """
        parts = [
            f"{metric_name}:",
            f"current={stats.current:.1f}",
            f"p50={stats.p50:.1f}",
            f"p95={stats.p95:.1f}",
        ]

        if self.include_trend:
            parts.append(f"trend={stats.trend}")

        parts.append(f"volatility={'high' if stats.std > stats.mean * 0.3 else 'low'}")

        return " ".join(parts)

    # ========== Day 4: Enhanced Trend Detection & Compression ==========

    def detect_trend(
        self,
        values: List[float],
        window_size: int = 5
    ) -> str:
        """
        Detect trend using moving average (NEW for Day 4).

        Algorithm:
        1. Calculate moving average
        2. Compare first vs last MA
        3. Check volatility (std/mean ratio)
        4. Classify trend

        Args:
            values: List of numeric values
            window_size: Moving average window

        Returns:
            Trend state: 'increasing', 'decreasing', 'stable', 'volatile', 'unknown'
        """
        if len(values) < window_size:
            return Trend.UNKNOWN.value

        try:
            # Convert to numpy array
            arr = np.array(values)

            # Calculate moving averages
            ma_values = []
            for i in range(len(arr) - window_size + 1):
                window = arr[i:i + window_size]
                ma_values.append(np.mean(window))

            if len(ma_values) < 2:
                return Trend.UNKNOWN.value

            # Calculate volatility
            std = np.std(ma_values)
            mean = np.mean(ma_values)

            if mean > 0:
                volatility_ratio = std / mean
            else:
                volatility_ratio = float('inf') if std > 0 else 0

            # High volatility → volatile trend
            if volatility_ratio > 0.3:
                return Trend.VOLATILE.value

            # Compare first and last moving averages
            first_ma = ma_values[0]
            last_ma = ma_values[-1]

            # Calculate percent change
            if first_ma > 0:
                change_pct = (last_ma - first_ma) / abs(first_ma)
            else:
                change_pct = 0

            # Classify trend
            if change_pct > 0.1:  # >10% increase
                return Trend.INCREASING.value
            elif change_pct < -0.1:  # >10% decrease
                return Trend.DECREASING.value
            else:
                return Trend.STABLE.value
        except Exception:
            return Trend.UNKNOWN.value

    def compress_values(self, values: List[float], metric_name: str = "metric") -> dict:
        """
        Compress values to key statistics (NEW for Day 4).

        Returns:
            {
                "metric": str,
                "current": float,
                "p50": float,
                "p90": float,
                "p95": float,
                "p99": float,
                "min": float,
                "max": float,
                "trend": str,
                "volatility": float,
                "sample_count": int
            }
        """
        if not values:
            return self._empty_result(metric_name)

        try:
            arr = np.array(values)

            return {
                "metric": metric_name,
                "current": float(arr[-1]) if len(arr) > 0 else 0.0,
                "p50": float(np.percentile(arr, 50)),
                "p90": float(np.percentile(arr, 90)),
                "p95": float(np.percentile(arr, 95)),
                "p99": float(np.percentile(arr, 99)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "trend": self.detect_trend(values),
                "volatility": float(np.std(arr)) if len(arr) > 1 else 0.0,
                "sample_count": len(arr)
            }
        except Exception:
            return self._empty_result(metric_name)

    def _empty_result(self, metric_name: str) -> dict:
        """Return empty result structure (NEW for Day 4)."""
        return {
            "metric": metric_name,
            "current": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "min": 0.0,
            "max": 0.0,
            "trend": Trend.UNKNOWN.value,
            "volatility": 0.0,
            "sample_count": 0
        }
