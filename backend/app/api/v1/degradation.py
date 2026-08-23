"""
Degradation API Endpoints - Phase 7 Sprint 2

Purpose: API endpoints for graceful degradation and DR mode management

Endpoints:
- GET /api/v1/degradation/status - Get current degradation status
- POST /api/v1/degradation/transition - Manually trigger mode transition
- GET /api/v1/degradation/sources - Get source health status
- POST /api/v1/degradation/refresh - Refresh critical cache entries
- GET /api/v1/degradation/priority-config - Get priority configurations
- PUT /api/v1/degradation/priority-config - Update priority configuration
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field

from app.degradation.dr_handler import DRMode, DRHandler, ModeTransition
from app.degradation.priority_config import Priority, PriorityConfig, PriorityConfigManager
from app.degradation.critical_cache import CriticalDataCache

logger = logging.getLogger(__name__)

# Global instances (set in main.py)
dr_handler: Optional[DRHandler] = None
priority_manager: Optional[PriorityConfigManager] = None
critical_cache: Optional[CriticalDataCache] = None


def set_dr_handler(handler: DRHandler):
    """Set the global DR handler instance."""
    global dr_handler
    dr_handler = handler


def set_priority_manager(manager: PriorityConfigManager):
    """Set the global priority manager instance."""
    global priority_manager
    priority_manager = manager


def set_critical_cache(cache: CriticalDataCache):
    """Set the global critical cache instance."""
    global critical_cache
    critical_cache = cache


# Request/Response Models
class ManualTransitionRequest(BaseModel):
    """Request for manual mode transition."""
    mode: str = Field(..., description="Target mode (normal, degraded, emergency)")
    reason: str = Field(..., description="Reason for transition")

    class Config:
        json_schema_extra = {
            "example": {
                "mode": "degraded",
                "reason": "Elasticsearch cluster maintenance"
            }
        }


class ModeStatusResponse(BaseModel):
    """Response with current mode status."""
    current_mode: str
    health_percentage: float
    last_check: Optional[str]
    last_transition: Optional[Dict[str, Any]]
    source_health: Dict[str, Any]
    hysteresis: float
    running: bool


class SourceHealthResponse(BaseModel):
    """Response with source health status."""
    source_name: str
    available: bool
    response_time_ms: float
    last_check: str
    error: Optional[str]
    consecutive_failures: int


class RefreshCacheRequest(BaseModel):
    """Request to refresh cache entries."""
    project: str = Field(..., description="Project name")
    source_name: Optional[str] = Field(None, description="Specific source (None for all)")


class PriorityConfigUpdateRequest(BaseModel):
    """Request to update priority configuration."""
    source_name: str
    priority: str
    timeout_ms: int
    retry_count: int = 0
    fallback_to_cache: bool = True
    cache_ttl_seconds: int = 300
    project: Optional[str] = None


# Router
router = APIRouter(prefix="/degradation", tags=["degradation"])


@router.get(
    "/status",
    response_model=ModeStatusResponse,
    summary="Get degradation status",
    description="Get current DR mode and overall system health status."
)
async def get_degradation_status() -> ModeStatusResponse:
    """
    Get current degradation status.

    Returns:
        Current mode, health percentage, source health, and transition history.
    """
    if not dr_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DR handler not initialized"
        )

    try:
        status_data = dr_handler.get_mode_status()
        return ModeStatusResponse(**status_data)
    except Exception as e:
        logger.error(f"Error getting degradation status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/transition",
    response_model=Dict[str, Any],
    summary="Manual mode transition",
    description="Manually trigger a DR mode transition."
)
async def manual_transition(request: ManualTransitionRequest) -> Dict[str, Any]:
    """
    Manually trigger a DR mode transition.

    Use this for planned maintenance or emergencies.
    """
    if not dr_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DR handler not initialized"
        )

    try:
        # Validate mode
        try:
            target_mode = DRMode(request.mode.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mode: {request.mode}. Must be: normal, degraded, emergency"
            )

        # Execute transition
        transition = await dr_handler.manual_transition(
            target_mode,
            request.reason
        )

        return {
            "status": "success",
            "message": f"Transitioned to {request.mode} mode",
            "transition": transition.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during manual transition: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/reset",
    summary="Reset to normal mode",
    description="Reset the system back to NORMAL mode."
)
async def reset_to_normal() -> Dict[str, Any]:
    """
    Reset the system back to NORMAL mode.

    Use this after recovery from an incident.
    """
    if not dr_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DR handler not initialized"
        )

    try:
        transition = await dr_handler.reset_to_normal("Manual reset via API")

        return {
            "status": "success",
            "message": "Reset to normal mode",
            "transition": transition.to_dict()
        }

    except Exception as e:
        logger.error(f"Error resetting to normal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/sources",
    summary="Get source health status",
    description="Get health status of all data sources."
)
async def get_source_health() -> Dict[str, SourceHealthResponse]:
    """
    Get health status of all monitored data sources.

    Returns:
        Dictionary of source_name -> health status.
    """
    if not dr_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DR handler not initialized"
        )

    try:
        health_data = dr_handler.get_source_health()
        return {
            name: SourceHealthResponse(**data)
            for name, data in health_data.items()
        }
    except Exception as e:
        logger.error(f"Error getting source health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/transitions",
    summary="Get transition history",
    description="Get recent DR mode transitions."
)
async def get_transition_history(limit: int = 10) -> Dict[str, Any]:
    """
    Get recent DR mode transitions.

    Args:
        limit: Maximum number of transitions to return (default: 10)
    """
    if not dr_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DR handler not initialized"
        )

    try:
        transitions = dr_handler.get_transition_history(limit)
        return {
            "transitions": transitions,
            "total": len(transitions)
        }
    except Exception as e:
        logger.error(f"Error getting transition history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/refresh",
    summary="Refresh critical cache",
    description="Manually refresh critical cache entries."
)
async def refresh_critical_cache(
    request: RefreshCacheRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Manually trigger refresh of critical cache entries.

    Args:
        request: Refresh request with project and optional source name

    Returns:
        Refresh status and affected sources.
    """
    if not critical_cache:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Critical cache not initialized"
        )

    try:
        if request.source_name:
            # Refresh specific source
            await critical_cache.refresh_entry(
                request.project,
                request.source_name
            )
            return {
                "status": "success",
                "message": f"Refreshed cache for {request.project}/{request.source_name}",
                "affected_sources": [request.source_name]
            }
        else:
            # Refresh all sources for project
            sources = await critical_cache._get_project_sources(request.project)
            for source_name in sources:
                await critical_cache.refresh_entry(
                    request.project,
                    source_name
                )
            return {
                "status": "success",
                "message": f"Refreshed all cache for {request.project}",
                "affected_sources": sources
            }

    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/cache/health",
    summary="Get critical cache health",
    description="Get health status of the critical cache system."
)
async def get_cache_health() -> Dict[str, Any]:
    """
    Get health status of the critical cache.

    Returns:
        Cache health, statistics, and entry counts.
    """
    if not critical_cache:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Critical cache not initialized"
        )

    try:
        health = await critical_cache.get_health_status()
        return health
    except Exception as e:
        logger.error(f"Error getting cache health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/priority-config",
    summary="Get priority configurations",
    description="Get all priority configurations."
)
async def get_priority_configurations(project: Optional[str] = None) -> Dict[str, Any]:
    """
    Get priority configurations.

    Args:
        project: Optional project name for project-specific configs
    """
    if not priority_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Priority manager not initialized"
        )

    try:
        configs = priority_manager.get_all_configs(project)
        summary = priority_manager.get_priority_summary()

        return {
            "configurations": {
                name: config.model_dump(mode='json')
                for name, config in configs.items()
            },
            "summary": summary,
            "project": project or "global"
        }
    except Exception as e:
        logger.error(f"Error getting priority configs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put(
    "/priority-config",
    summary="Update priority configuration",
    description="Update priority configuration for a data source."
)
async def update_priority_configuration(request: PriorityConfigUpdateRequest) -> Dict[str, Any]:
    """
    Update priority configuration for a data source.

    Validates and applies the new configuration.
    """
    if not priority_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Priority manager not initialized"
        )

    try:
        # Validate priority
        try:
            priority_enum = Priority[request.priority.upper()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {request.priority}. Must be: P0, P1, P2, P3"
            )

        # Create config
        config = PriorityConfig(
            source_name=request.source_name,
            priority=priority_enum,
            timeout_ms=request.timeout_ms,
            retry_count=request.retry_count,
            fallback_to_cache=request.fallback_to_cache,
            cache_ttl_seconds=request.cache_ttl_seconds
        )

        # Validate config
        errors = priority_manager.validate_config(config)
        if errors:
            return {
                "status": "warning",
                "message": "Configuration saved with validation warnings",
                "warnings": errors,
                "config": config.model_dump(mode='json')
            }

        # Apply config
        priority_manager.update_config(
            request.source_name,
            config,
            request.project
        )

        return {
            "status": "success",
            "message": f"Updated priority config for {request.source_name}",
            "config": config.model_dump(mode='json')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating priority config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/health-check",
    summary="Trigger health check",
    description="Manually trigger a health check and mode evaluation."
)
async def trigger_health_check(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Manually trigger a health check of all data sources.

    This will evaluate source health and potentially trigger a mode transition.
    """
    if not dr_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DR handler not initialized"
        )

    try:
        # Trigger health check in background
        async def run_check():
            return await dr_handler.check_health_and_transition(manual_trigger=True)

        background_tasks.add_task(run_check)

        return {
            "status": "scheduled",
            "message": "Health check scheduled"
        }

    except Exception as e:
        logger.error(f"Error triggering health check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/stats",
    summary="Get degradation statistics",
    description="Get statistics about degradation and cache performance."
)
async def get_degradation_stats() -> Dict[str, Any]:
    """
    Get statistics about degradation and cache performance.

    Returns:
        Combined statistics from DR handler and critical cache.
    """
    stats = {}

    if dr_handler:
        status = dr_handler.get_mode_status()
        stats["dr_handler"] = {
            "current_mode": status["current_mode"],
            "health_percentage": status["health_percentage"],
            "total_transitions": len(dr_handler.transition_history),
            "running": status["running"]
        }

    if critical_cache:
        stats["critical_cache"] = await critical_cache.get_health_status()

    if priority_manager:
        stats["priority_config"] = priority_manager.get_priority_summary()

    return stats
