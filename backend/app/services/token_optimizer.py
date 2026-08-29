"""
Token Optimizer Service - Core engine for AI input optimization.

This module implements intelligent context optimization to reduce token usage
while maintaining triage card accuracy.

Phase 6: AI Input Optimization & Cost Efficiency
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

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
    anomalies: list = None
    logs_sampled: int = 0
    metrics_compressed: bool = False
    fallback: bool = False
    fallback_reason: str | None = None

    def __post_init__(self):
        """Initialize default values for list fields."""
        if self.anomalies is None:
            self.anomalies = []

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
            "anomalies": self.anomalies,
            "logs_sampled": self.logs_sampled,
            "metrics_compressed": self.metrics_compressed,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
        }


class TokenOptimizer:
    """
    Core token optimization engine.

    Applies multiple strategies to minimize token usage while maintaining
    triage card accuracy.
    """

    def __init__(self, config: OptimizationConfig | None = None):
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
        token_budget: int | None = None,
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
        anomalies = []
        logs_sampled = 0
        metrics_compressed = False

        # Strategy 1: Anomaly Detection Filtering
        if self.config.anomaly_cpu_high > 0:
            optimized_context, detected_anomalies = await self._apply_anomaly_detection(optimized_context)
            strategies_applied.append(OptimizationStrategy.ANOMALY_DETECTION)
            anomalies.extend(detected_anomalies)

        # Strategy 2: Smart Sampling (for logs)
        if optimized_context.get("logs"):
            optimized_context, sampled_count = await self._apply_smart_sampling(optimized_context, incident_type)
            strategies_applied.append(OptimizationStrategy.SMART_SAMPLING)
            logs_sampled = sampled_count

        # Strategy 3: Time Series Compression
        if self.config.compress_time_series:
            optimized_context, compressed = await self._apply_time_series_compression(optimized_context)
            strategies_applied.append(OptimizationStrategy.TIME_SERIES_COMPRESSION)
            metrics_compressed = compressed

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
            anomalies=anomalies,
            logs_sampled=logs_sampled,
            metrics_compressed=metrics_compressed,
            fallback=False,
            fallback_reason=None,
        )

    async def optimize_with_fallback(
        self,
        context_data: dict[str, Any],
        incident_type: str,
        severity: SeverityLevel,
        request_id: str | None = None,
    ) -> OptimizationResult:
        """
        Optimize with automatic fallback on error.

        If optimization fails, returns original context with fallback=True.
        This ensures production stability - optimization failures never crash the system.

        Args:
            context_data: Full incident context
            incident_type: Type of incident
            severity: Severity level
            request_id: Request identifier for tracking

        Returns:
            OptimizationResult (with fallback=True if failed)
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Attempt optimization
            result = await self.optimize(
                context_data=context_data,
                incident_type=incident_type,
                severity=severity
            )

            # Validate result
            if not self._validate_result(result):
                logger.warning(
                    f"Optimization validation failed for {request_id}, using fallback"
                )
                return self._create_fallback_result(
                    context_data, "Validation failed"
                )

            return result

        except Exception as e:
            # Log the error with full context
            logger.error(
                f"Optimization failed for {request_id}: {e!s}",
                exc_info=True,
                extra={
                    'incident_type': incident_type,
                    'severity': str(severity),
                    'context_keys': list(context_data.keys())
                }
            )

            # Return fallback result
            return self._create_fallback_result(
                context_data,
                f"{type(e).__name__}: {e!s}"
            )

    def _validate_result(self, result: OptimizationResult) -> bool:
        """Validate optimization result."""
        # Check essential fields exist
        if not result.optimized_context:
            return False

        # Check token reduction is reasonable
        if result.token_savings_percent < -100:
            return False

        # Check processing time is reasonable
        if result.processing_time_ms > 10000:
            return False

        # Check optimized context is not empty
        if not result.optimized_context:
            return False

        return True

    def _create_fallback_result(
        self,
        context_data: dict[str, Any],
        reason: str
    ) -> OptimizationResult:
        """Create fallback result with original context."""
        original_count = self._estimate_tokens(context_data)

        return OptimizationResult(
            optimized_context=context_data,
            original_tokens=original_count,
            optimized_tokens=original_count,
            token_savings=0,
            token_savings_percent=0.0,
            strategies_applied=[],
            processing_time_ms=0.0,
            anomalies=[],
            logs_sampled=0,
            metrics_compressed=False,
            fallback=True,
            fallback_reason=reason
        )

    async def _apply_anomaly_detection(self, context: dict[str, Any]) -> tuple[dict[str, Any], list]:
        """Apply anomaly detection filtering to metrics.

        Returns:
            Tuple of (updated_context, list_of_anomalies)
        """
        # Import here to avoid circular imports
        from app.services.anomaly_detector import AnomalyDetector

        anomalies = []
        if self._anomaly_detector is None:
            self._anomaly_detector = AnomalyDetector(self.config)

        if context.get("metrics"):
            context["metrics"], detected_anomalies = await self._anomaly_detector.detect_metrics_anomaly(
                context["metrics"]
            )
            anomalies.extend(detected_anomalies)

        return context, anomalies

    async def _apply_smart_sampling(
        self, context: dict[str, Any], incident_type: str
    ) -> tuple[dict[str, Any], int]:
        """Apply smart sampling to logs.

        Returns:
            Tuple of (updated_context, sampled_count)
        """
        from app.services.log_sampler import LogSampler

        sampled_count = 0
        if self._log_sampler is None:
            self._log_sampler = LogSampler(self.config)

        if context.get("logs"):
            # Handle both dict format (TestDataGenerator) and list format
            logs_data = context["logs"]
            if isinstance(logs_data, dict):
                # TestDataGenerator format: {"logs": [...], "total": N, ...}
                logs_list = logs_data.get("logs", [])
                original_count = len(logs_list)
            else:
                # Direct list format
                logs_list = logs_data
                original_count = len(logs_list)

            # Sample the logs
            sampled_logs = await self._log_sampler.sample_logs(
                logs_list,
                incident_type,
                self.config.max_results_per_source
            )
            sampled_count = len(sampled_logs)

            # Update context - preserve original structure if it was a dict
            if isinstance(logs_data, dict):
                context["logs"]["logs"] = sampled_logs
                context["logs"]["total"] = sampled_count
            else:
                context["logs"] = sampled_logs

        # Apply to APM errors too (check for apm_data)
        if "apm_data" in context and isinstance(context["apm_data"], dict):
            if "top_errors" in context["apm_data"]:
                context["apm_data"]["top_errors"] = await self._log_sampler.sample_apm_errors(
                    context["apm_data"]["top_errors"],
                    self.config.log_sampling_error
                )

        return context, sampled_count

    async def _apply_time_series_compression(self, context: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Apply time series compression.

        Returns:
            Tuple of (updated_context, was_compressed)
        """
        from app.services.time_series_compressor import TimeSeriesCompressor

        compressed = False
        if self._ts_compressor is None:
            self._ts_compressor = TimeSeriesCompressor(self.config)

        # Compress any time-series data in metrics
        if context.get("metrics"):
            context["metrics"], compressed = await self._ts_compressor.compress_metrics(
                context["metrics"]
            )

        return context, compressed

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
_token_optimizer: TokenOptimizer | None = None


def get_token_optimizer(config: OptimizationConfig | None = None) -> TokenOptimizer:
    """Get or create the singleton TokenOptimizer instance."""
    global _token_optimizer
    if _token_optimizer is None:
        _token_optimizer = TokenOptimizer(config)
    return _token_optimizer
