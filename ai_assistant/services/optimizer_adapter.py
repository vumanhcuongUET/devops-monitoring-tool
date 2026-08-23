"""
Optimizer Adapter for AI Assistant.

Provides sync wrapper around TokenOptimizer from backend Phase 6.
Enables 70% token reduction for LLM calls.

Architecture Note:
This adapter uses sys.path manipulation to import backend clients.
See docs/adr/001-backend-integration-via-sys-path.md for rationale.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add backend to Python path
# NOTE: This is an intentional integration pattern for the monorepo.
# If backend/ moves, update this path. See ADR 001.
backend_path = Path(__file__).parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from app.services.token_optimizer import TokenOptimizer
    from app.services.anomaly_detector import AnomalyDetector
    from app.services.log_sampler import LogSampler
    from app.services.time_series_compressor import TimeSeriesCompressor
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False

# Import sync_bridge (handle both relative and absolute import)
try:
    from ..core.sync_bridge import sync_async_bridge
except ImportError:
    # Fallback when run as script or tests
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.sync_bridge import sync_async_bridge


class OptimizerAdapter:
    """
    Sync adapter for TokenOptimizer from Phase 6.

    Applies intelligent optimization strategies to reduce LLM token usage
    by 60-80% while maintaining accuracy.
    """

    def __init__(
        self,
        default_rate: float = 100.0,
        burst: int = 10,
        fallback_enabled: bool = True
    ):
        """
        Initialize optimizer.

        Args:
            default_rate: Default requests per second for rate limiting
            burst: Burst capacity for rate limiter
            fallback_enabled: If True, returns unoptimized context if backend unavailable
        """
        self._optimizer = None
        self._fallback_enabled = fallback_enabled

        if BACKEND_AVAILABLE:
            try:
                # Initialize with minimal required dependencies
                self._optimizer = TokenOptimizer(
                    es_client=None,  # Will be set if needed
                    prom_client=None,
                    k8s_client=None,
                    l2_cache=None
                )
            except Exception as e:
                if not fallback_enabled:
                    raise RuntimeError(f"Failed to initialize TokenOptimizer: {e}")
        else:
            # Backend unavailable
            if not fallback_enabled:
                raise RuntimeError("Backend unavailable and fallback disabled")

    @property
    def available(self) -> bool:
        """Check if optimizer is available."""
        return self._optimizer is not None

    @sync_async_bridge
    async def optimize(
        self,
        context: Dict[str, Any],
        incident_type: str,
        severity: str = "medium"
    ) -> Dict[str, Any]:
        """
        Optimize context for LLM consumption.

        Applies anomaly detection, smart sampling, time series compression,
        and relevance filtering.

        Args:
            context: Raw monitoring context (logs, metrics, APM, K8s data)
            incident_type: Type of incident (high_latency, high_error_rate, etc.)
            severity: Incident severity (low, medium, high, critical)

        Returns:
            Optimized context with metadata about savings
        """
        if not self.available:
            # Return unoptimized with flag
            return {
                "context": context,
                "optimized": False,
                "original_tokens": 0,
                "optimized_tokens": 0,
                "token_savings": 0,
                "fallback": True
            }

        # Call backend optimizer
        result = await self._optimizer.optimize(
            context=context,
            incident_type=incident_type,
            severity=severity
        )

        return result

    @sync_async_bridge
    async def optimize_with_fallback(
        self,
        context: Dict[str, Any],
        incident_type: str,
        severity: str = "medium"
    ) -> Dict[str, Any]:
        """
        Optimize with automatic fallback on error.

        If optimization fails, returns original context gracefully.

        Args:
            context: Raw monitoring context
            incident_type: Type of incident
            severity: Incident severity

        Returns:
            Optimized context (or original if optimization fails)
        """
        try:
            return await self.optimize(context, incident_type, severity)
        except Exception as e:
            # Fallback to original context
            return {
                "context": context,
                "optimized": False,
                "error": str(e),
                "fallback": True,
                "original_tokens": 0,
                "optimized_tokens": 0,
                "token_savings": 0
            }

    def estimate_tokens(self, data: Dict[str, Any]) -> int:
        """
        Estimate token count for data.

        Rough estimation based on character count (4 chars ≈ 1 token).

        Args:
            data: Data dictionary to estimate

        Returns:
            Estimated token count
        """
        import json

        json_str = json.dumps(data, ensure_ascii=False)
        # Rough approximation: 4 characters ≈ 1 token
        return len(json_str) // 4
