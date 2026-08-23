"""
Optimization API - Endpoints for optimization metrics and control.

Provides REST API for tracking optimization performance and tuning parameters.

Phase 6: AI Input Optimization - Sprint 4
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from app.analytics.token_tracker import TokenTracker
from app.quality.ab_tester import ABTester, get_ab_tester
from app.quality.accuracy_validator import get_accuracy_validator


router = APIRouter(prefix="/api/v1/optimization", tags=["optimization"])


# Request/Response Models
class OptimizationStatsResponse(BaseModel):
    """Response model for optimization statistics."""
    total_optimizations: int
    avg_reduction_pct: float
    total_tokens_saved: int
    avg_processing_time_ms: float
    fallback_rate: float
    by_incident_type: Dict[str, Any]
    by_severity: Dict[str, Any]
    recent_sample: list


class AccuracyMetricsResponse(BaseModel):
    """Response model for accuracy metrics."""
    avg_recall: float
    avg_precision: float
    avg_severity_accuracy: float
    total_validations: int


class ABTestStatsResponse(BaseModel):
    """Response model for A/B test statistics."""
    total_tests: int
    baseline_wins: int
    optimized_wins: int
    win_rate_optimized: float
    avg_token_reduction_pct: float
    avg_processing_time_diff_ms: float
    avg_finding_recall: float
    avg_finding_precision: float


class TuningRequest(BaseModel):
    """Request model for parameter tuning."""
    anomaly_cpu_high: Optional[float] = None
    anomaly_memory_high: Optional[float] = None
    log_sampling_critical: Optional[int] = None
    log_sampling_error: Optional[int] = None
    min_relevance_score: Optional[float] = None
    max_results_per_source: Optional[int] = None


class TuningResponse(BaseModel):
    """Response model for parameter tuning."""
    success: bool
    message: str
    updated_params: Dict[str, Any]


# Initialize components
token_tracker = TokenTracker()
ab_tester: Optional[ABTester] = None


@router.get("/stats", response_model=OptimizationStatsResponse)
async def get_optimization_stats(
    limit: int = 100,
    hours: int = 24
) -> OptimizationStatsResponse:
    """
    Get optimization statistics.

    Args:
        limit: Maximum number of recent samples to return
        hours: Time window in hours (default: 24)

    Returns:
        Optimization statistics including token savings, processing time, etc.
    """
    since = datetime.now() - timedelta(hours=hours)
    stats = token_tracker.get_stats(limit=limit, since=since)

    return OptimizationStatsResponse(**stats)


@router.get("/accuracy", response_model=AccuracyMetricsResponse)
async def get_accuracy_metrics() -> AccuracyMetricsResponse:
    """
    Get accuracy metrics from validation history.

    Returns:
        Average recall, precision, and severity accuracy
    """
    validator = get_accuracy_validator()
    metrics = validator.get_aggregate_metrics()

    return AccuracyMetricsResponse(**metrics)


@router.get("/ab-testing", response_model=ABTestStatsResponse)
async def get_ab_test_stats() -> ABTestStatsResponse:
    """
    Get A/B testing statistics.

    Returns:
        A/B test results including win rates and performance metrics
    """
    global ab_tester
    if ab_tester is None:
        ab_tester = get_ab_tester()

    stats = ab_tester.get_statistics()

    return ABTestStatsResponse(**stats)


@router.get("/strategies")
async def get_active_strategies() -> Dict[str, Any]:
    """
    Get active optimization strategies.

    Returns:
        List of enabled strategies and their configuration
    """
    from app.config import settings

    return {
        "strategies": {
            "anomaly_detection": {
                "enabled": True,
                "priority": 1,
                "description": "Filter metrics based on anomaly detection"
            },
            "smart_sampling": {
                "enabled": True,
                "priority": 2,
                "description": "Intelligently sample logs based on relevance"
            },
            "time_series_compression": {
                "enabled": True,
                "priority": 3,
                "description": "Compress time-series data with percentiles"
            },
            "relevance_filtering": {
                "enabled": True,
                "priority": 4,
                "description": "Filter data sources by incident relevance"
            }
        },
        "feature_flags": {
            "ab_testing_enabled": settings.OPTIMIZATION_AB_TESTING if hasattr(settings, 'OPTIMIZATION_AB_TESTING') else False,
            "relevance_scoring_enabled": settings.OPTIMIZATION_RELEVANCE_SCORING if hasattr(settings, 'OPTIMIZATION_RELEVANCE_SCORING') else False,
            "dynamic_budgeting_enabled": settings.OPTIMIZATION_DYNAMIC_BUDGETING if hasattr(settings, 'OPTIMIZATION_DYNAMIC_BUDGETING') else False
        }
    }


@router.post("/tune", response_model=TuningResponse)
async def tune_parameters(request: TuningRequest) -> TuningResponse:
    """
    Tune optimization parameters dynamically.

    Args:
        request: Parameter tuning request

    Returns:
        Success status and updated parameters
    """
    try:
        import yaml
        from pathlib import Path

        config_path = Path("config/optimization.yaml")

        # Read current config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Update parameters
        updated = {}
        if request.anomaly_cpu_high is not None:
            config['strategies']['anomaly_detection']['thresholds']['cpu']['high'] = request.anomaly_cpu_high
            updated['anomaly_cpu_high'] = request.anomaly_cpu_high

        if request.anomaly_memory_high is not None:
            config['strategies']['anomaly_detection']['thresholds']['memory']['high'] = request.anomaly_memory_high
            updated['anomaly_memory_high'] = request.anomaly_memory_high

        if request.log_sampling_critical is not None:
            config['strategies']['smart_sampling']['quotas']['critical'] = request.log_sampling_critical
            updated['log_sampling_critical'] = request.log_sampling_critical

        if request.log_sampling_error is not None:
            config['strategies']['smart_sampling']['quotas']['error'] = request.log_sampling_error
            updated['log_sampling_error'] = request.log_sampling_error

        if request.min_relevance_score is not None:
            config['strategies']['relevance_filtering']['min_relevance_score'] = request.min_relevance_score
            updated['min_relevance_score'] = request.min_relevance_score

        if request.max_results_per_source is not None:
            config['strategies']['smart_sampling']['max_results_per_source'] = request.max_results_per_source
            updated['max_results_per_source'] = request.max_results_per_source

        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        return TuningResponse(
            success=True,
            message=f"Updated {len(updated)} parameters",
            updated_params=updated
        )

    except Exception as e:
        logger.error(f"Failed to tune parameters: {e}")
        return TuningResponse(
            success=False,
            message=str(e),
            updated_params={}
        )


@router.get("/quality-gates")
async def get_quality_gates() -> Dict[str, Any]:
    """
    Get current quality gate thresholds.

    Returns:
        Quality gate configuration and status
    """
    from app.config import settings

    return {
        "quality_gates": {
            "finding_recall_min": 0.90,
            "finding_precision_min": 0.85,
            "severity_accuracy_min": 0.95,
            "token_reduction_min": 0.50,
            "processing_time_max_ms": 3000
        },
        "enforcement": {
            "enforce_thresholds": settings.OPTIMIZATION_ENFORCE_GATES if hasattr(settings, 'OPTIMIZATION_ENFORCE_GATES') else False
        }
    }


@router.get("/health")
async def optimization_health() -> Dict[str, Any]:
    """
    Health check for optimization system.

    Returns:
        System health status
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }

    # Check token tracker
    try:
        stats = token_tracker.get_stats(limit=1)
        health["components"]["token_tracker"] = "healthy"
    except Exception as e:
        health["components"]["token_tracker"] = f"unhealthy: {e}"
        health["status"] = "degraded"

    return health
