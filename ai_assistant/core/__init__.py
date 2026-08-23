"""
Core utilities for AI Assistant.

Exports config loading, feature flags, template rendering, caching,
single-flight deduplication, logging/metrics, and security.
"""

from .config_loader import (
    load_config,
    load_query_def,
    load_feature_flags,
    get_feature_flags,
    reload_feature_flags,
    is_feature_enabled,
    render_template,
)

from .sync_bridge import sync_async_bridge, run_async

from .cache import (
    SimpleCache,
    get_global_cache,
    cache_key_from_args,
    cached,
    clear_cache,
    get_cache_stats,
)

from .single_flight import (
    SingleFlight,
    get_global_single_flight,
    single_flight,
    get_single_flight_stats,
)

from .logging_config import (
    LogContext,
    get_log_context,
    set_log_context,
    log_context,
    CredentialSanitizer,
    JSONFormatter,
    MetricsCollector,
    get_metrics,
    setup_logging,
    track_time,
    track_counter,
    get_logger,
    log_with_context,
    log_debug,
    log_info,
    log_warning,
    log_error,
)

from .security import (
    RateLimitResult,
    TokenBucketRateLimiter,
    InputValidator,
    SecurityHeaders,
    rate_limit,
    validate_input,
    get_rate_limiter,
    check_rate_limit,
)

__all__ = [
    # Config loading
    "load_config",
    "load_query_def",
    "load_feature_flags",
    "get_feature_flags",
    "reload_feature_flags",
    "is_feature_enabled",
    # Template rendering
    "render_template",
    # Sync/async bridge
    "sync_async_bridge",
    "run_async",
    # Caching
    "SimpleCache",
    "get_global_cache",
    "cache_key_from_args",
    "cached",
    "clear_cache",
    "get_cache_stats",
    # Single-flight deduplication
    "SingleFlight",
    "get_global_single_flight",
    "single_flight",
    "get_single_flight_stats",
    # Logging & metrics
    "LogContext",
    "get_log_context",
    "set_log_context",
    "log_context",
    "CredentialSanitizer",
    "JSONFormatter",
    "MetricsCollector",
    "get_metrics",
    "setup_logging",
    "track_time",
    "track_counter",
    "get_logger",
    "log_with_context",
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    # Security
    "RateLimitResult",
    "TokenBucketRateLimiter",
    "InputValidator",
    "SecurityHeaders",
    "rate_limit",
    "validate_input",
    "get_rate_limiter",
    "check_rate_limit",
]
