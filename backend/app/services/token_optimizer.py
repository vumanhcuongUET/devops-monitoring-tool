"""
Token Optimizer Service - Core engine for AI input optimization.

This module implements intelligent context optimization to reduce token usage
while maintaining triage card accuracy.

Phase 6: AI Input Optimization & Cost Efficiency
"""

from datetime import timedelta
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

from app.models.triage_card import SeverityLevel


class OptimizationStrategy(str, Enum):
    """Available optimization strategies."""
    ANOMALY_DETECTION = "anomaly_detection"
    SMART_SAMPLING = "smart_sampling"
    TIME_SERIES_COMPRESSION = "time_series_compression"
    RELEVANCE_FILTERING = "relevance_filtering"
    COMPACT_FORMATTING = "compact_formatting"


@dataclass
class OptimizationConfig:
    """Configuration for token optimization."""
    enabled: bool = True
    default_budget: int = 2000
    fallback_on_error: bool = True

    # Anomaly detection thresholds
    anomaly_cpu_high: float = 80.0
    anomaly_cpu_low: float = 20.0
    anomaly_memory_high: float = 85.0
    anomaly_disk_high: float = 90.0
    anomaly_error_rate_high: float = 5.0

    # Network I/O thresholds (multipliers for baseline)
    anomaly_network_io_high_multiplier: float = 3.0
    anomaly_network_io_critical_multiplier: float = 5.0

    # Disk I/O thresholds (multipliers for baseline)
    anomaly_disk_io_high_multiplier: float = 3.0
    anomaly_disk_io_critical_multiplier: float = 5.0

    # Smart sampling quotas
    log_sampling_critical: int = 5
    log_sampling_error: int = 10
    log_sampling_warning: int = 10
    log_sampling_info: int = 5

    # Relevance scoring
    min_relevance_score: float = 0.3
    max_results_per_source: int = 20

    # Time series compression
    compress_time_series: bool = True
    include_percentiles: bool = True
    include_trend: bool = True


@dataclass
class OptimizationResult:
    """Result of optimization process."""
    optimized_context: dict[str, Any]
    original_tokens: int
    optimized_tokens: int
    token_savings: int
    token_savings_percent: float
    strategies_applied: list[OptimizationStrategy]
    processing_time_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "optimized_context": self.optimized_context,
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "token_savings": self.token_savings,
            "token_savings_percent": self.token_savings_percent,
            "strategies_applied": [s.value for s in self.strategies_applied],
            "processing_time_ms": self.processing_time_ms,
        }


class TokenOptimizer:
    """
    Core token optimization engine.

    Applies multiple strategies to minimize token usage while maintaining
    triage card accuracy.
    """

    def __init__(self, config: Optional[OptimizationConfig] = None):
        """Initialize token optimizer with configuration."""
        self.config = config or OptimizationConfig()
        self._strategies = []

        # Import strategy modules (lazy loading)
        self._anomaly_detector = None
        self._log_sampler = None
        self._ts_compressor = None
        self._relevance_scorer = None

    async def optimize(
        self,
        context_data: dict[str, Any],
        incident_type: str,
        severity: SeverityLevel,
        token_budget: Optional[int] = None,
    ) -> OptimizationResult:
        """
        Apply optimization strategies to minimize token usage.

        Args:
            context_data: Raw monitoring context data
            incident_type: Type of incident (high_latency, high_error_rate, etc.)
            severity: Severity level of incident
            token_budget: Optional token budget constraint

        Returns:
            OptimizationResult with optimized context and metrics
        """
        import time
        start_time = time.time()

        # Calculate initial token estimate
        original_tokens = self._estimate_tokens(context_data)

        # Determine token budget
        budget = token_budget or self._get_budget_for_severity(severity)

        # Apply optimization strategies sequentially
        optimized_context = context_data.copy()
        strategies_applied = []

        # Strategy 1: Anomaly Detection Filtering
        if self.config.anomaly_cpu_high > 0:
            optimized_context = await self._apply_anomaly_detection(optimized_context)
            strategies_applied.append(OptimizationStrategy.ANOMALY_DETECTION)

        # Strategy 2: Smart Sampling (for logs)
        if "logs" in optimized_context and optimized_context["logs"]:
            optimized_context = await self._apply_smart_sampling(optimized_context, incident_type)
            strategies_applied.append(OptimizationStrategy.SMART_SAMPLING)

        # Strategy 3: Time Series Compression
        if self.config.compress_time_series:
            optimized_context = await self._apply_time_series_compression(optimized_context)
            strategies_applied.append(OptimizationStrategy.TIME_SERIES_COMPRESSION)

        # Strategy 4: Relevance Filtering
        optimized_context = await self._apply_relevance_filtering(
            optimized_context, incident_type, severity
        )
        strategies_applied.append(OptimizationStrategy.RELEVANCE_FILTERING)

        # Strategy 5: Compact Formatting
        optimized_context = self._apply_compact_formatting(optimized_context)
        strategies_applied.append(OptimizationStrategy.COMPACT_FORMATTING)

        # Calculate final metrics
        optimized_tokens = self._estimate_tokens(optimized_context)
        token_savings = original_tokens - optimized_tokens
        token_savings_percent = (token_savings / original_tokens * 100) if original_tokens > 0 else 0

        processing_time_ms = (time.time() - start_time) * 1000

        return OptimizationResult(
            optimized_context=optimized_context,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            token_savings=token_savings,
            token_savings_percent=token_savings_percent,
            strategies_applied=strategies_applied,
            processing_time_ms=processing_time_ms,
        )

    async def _apply_anomaly_detection(self, context: dict[str, Any]) -> dict[str, Any]:
        """Apply anomaly detection filtering to metrics."""
        # Import here to avoid circular imports
        from app.services.anomaly_detector import AnomalyDetector

        if self._anomaly_detector is None:
            self._anomaly_detector = AnomalyDetector(self.config)

        if "metrics" in context and context["metrics"]:
            context["metrics"] = await self._anomaly_detector.detect_metrics_anomaly(
                context["metrics"]
            )

        return context

    async def _apply_smart_sampling(
        self, context: dict[str, Any], incident_type: str
    ) -> dict[str, Any]:
        """Apply smart sampling to logs."""
        from app.services.log_sampler import LogSampler

        if self._log_sampler is None:
            self._log_sampler = LogSampler(self.config)

        if "logs" in context and context["logs"]:
            context["logs"] = await self._log_sampler.sample_logs(
                context["logs"],
                incident_type,
                self.config.max_results_per_source
            )

        # Apply to APM errors too
        if "apm" in context and isinstance(context["apm"], dict):
            if "top_errors" in context["apm"]:
                context["apm"]["top_errors"] = await self._log_sampler.sample_apm_errors(
                    context["apm"]["top_errors"],
                    self.config.log_sampling_error
                )

        return context

    async def _apply_time_series_compression(self, context: dict[str, Any]) -> dict[str, Any]:
        """Apply time series compression."""
        from app.services.time_series_compressor import TimeSeriesCompressor

        if self._ts_compressor is None:
            self._ts_compressor = TimeSeriesCompressor(self.config)

        # Compress any time-series data in metrics
        if "metrics" in context and context["metrics"]:
            context["metrics"] = await self._ts_compressor.compress_metrics(
                context["metrics"]
            )

        return context

    async def _apply_relevance_filtering(
        self, context: dict[str, Any], incident_type: str, severity: SeverityLevel
    ) -> dict[str, Any]:
        """Apply relevance-based filtering."""
        # Select relevant data sources based on incident type
        relevant_sources = self._get_relevant_sources(incident_type)

        # Filter out irrelevant data sources
        filtered_context = {}
        for source in relevant_sources:
            if source in context:
                filtered_context[source] = context[source]

        # Always include critical fields
        if "alerts" in context:
            filtered_context["alerts"] = context["alerts"][:self.config.max_results_per_source]

        return filtered_context

    def _apply_compact_formatting(self, context: dict[str, Any]) -> dict[str, Any]:
        """Apply compact formatting to reduce token usage."""
        # Remove None values
        compact_context = {}
        for key, value in context.items():
            if value is not None and value != [] and value != {}:
                compact_context[key] = value

        return compact_context

    def _get_budget_for_severity(self, severity: SeverityLevel) -> int:
        """Get token budget based on severity level."""
        budgets = {
            SeverityLevel.CRITICAL: 3000,
            SeverityLevel.HIGH: 2500,
            SeverityLevel.MEDIUM: 2000,
            SeverityLevel.LOW: 1500,
            SeverityLevel.INFO: 1000,
        }
        return budgets.get(severity, self.config.default_budget)

    def _get_relevant_sources(self, incident_type: str) -> list[str]:
        """Get relevant data sources for incident type."""
        mapping = {
            "high_latency": ["apm", "metrics", "kubernetes"],
            "high_error_rate": ["logs", "apm", "alerts"],
            "pod_crashloop": ["kubernetes", "logs", "metrics"],
            "disk_full": ["metrics", "logs"],
            "database_slow": ["apm", "metrics"],
            "network_issue": ["metrics", "kubernetes", "logs"],
            "deployment_failure": ["kubernetes", "logs"],
        }
        return mapping.get(incident_type, ["logs", "metrics", "kubernetes", "alerts"])

    def _estimate_tokens(self, data: dict[str, Any]) -> int:
        """
        Rough token estimation.

        Approximate: 1 token ≈ 4 characters
        """
        import json
        text = json.dumps(data, ensure_ascii=False)
        return len(text) // 4


# Singleton instance
_token_optimizer: Optional[TokenOptimizer] = None


def get_token_optimizer(config: Optional[OptimizationConfig] = None) -> TokenOptimizer:
    """Get or create the singleton TokenOptimizer instance."""
    global _token_optimizer
    if _token_optimizer is None:
        _token_optimizer = TokenOptimizer(config)
    return _token_optimizer
