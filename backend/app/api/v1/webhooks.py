"""
Webhook API Endpoints for Cache Invalidation

Phase 7 - Sprint 1 - Day 7
Purpose: Handle deployment and config change webhooks for cache invalidation

Endpoints:
- POST /api/v1/webhooks/deployment - Handle deployment events
- POST /api/v1/webhooks/config-change - Handle config change events
- GET /api/v1/webhooks/stats - Get webhook statistics
"""

import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from app.cache.invalidation import (
    DeploymentEvent,
    ConfigChangeEvent,
    WebhookProcessor,
    CacheInvalidator
)

logger = logging.getLogger(__name__)

# Global webhook processor (initialized in main.py)
webhook_processor: Optional[WebhookProcessor] = None


def set_webhook_processor(processor: WebhookProcessor):
    """Set the global webhook processor instance."""
    global webhook_processor
    webhook_processor = processor


# Request Models
class DeploymentWebhookRequest(BaseModel):
    """Deployment webhook request model."""

    project: str = Field(..., description="Project name")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Deployment version")
    environment: str = Field(default="production", description="Deployment environment")
    timestamp: Optional[str] = Field(None, description="Event timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "project": "meinvoice",
                "service": "api-gateway",
                "version": "v1.2.3",
                "environment": "production",
                "timestamp": "2026-08-23T10:30:00Z"
            }
        }


class ConfigChangeWebhookRequest(BaseModel):
    """Config change webhook request model."""

    project: str = Field(..., description="Project name")
    config_type: str = Field(..., description="Type of config that changed")
    changed_keys: List[str] = Field(..., description="List of changed config keys")
    environment: str = Field(default="production", description="Environment")
    timestamp: Optional[str] = Field(None, description="Event timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "project": "meinvoice",
                "config_type": "alerting",
                "changed_keys": ["cpu_threshold", "memory_threshold"],
                "environment": "production"
            }
        }


class WebhookResponse(BaseModel):
    """Webhook response model."""

    status: str = Field(..., description="Processing status")
    message: Optional[str] = Field(None, description="Optional message")
    event_id: Optional[str] = Field(None, description="Event ID for tracking")
    invalidated_count: Optional[int] = Field(None, description="Number of cache entries invalidated")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Cache invalidation scheduled",
                "event_id": "deploy:meinvoice:api-gateway:2026-08-23T10:30:00Z",
                "invalidated_count": 15
            }
        }


# Router
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/deployment",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle deployment webhook",
    description="Process deployment events and invalidate relevant cache entries."
)
async def on_deployment(
    payload: DeploymentWebhookRequest,
    background_tasks: BackgroundTasks
) -> WebhookResponse:
    """
    Handle deployment webhook and invalidate relevant cache.

    This endpoint receives deployment events and invalidates cache entries
    tagged with the project and service from the deployment.
    """
    if not webhook_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processor not initialized"
        )

    try:
        # Create deployment event
        event = DeploymentEvent(
            project=payload.project,
            service=payload.service,
            version=payload.version,
            environment=payload.environment,
            timestamp=payload.timestamp
        )

        # Process in background
        async def process_deployment():
            return await webhook_processor.process_deployment_webhook(event)

        background_tasks.add_task(process_deployment)

        return WebhookResponse(
            status="scheduled",
            message="Deployment webhook received, cache invalidation scheduled",
            details={
                "project": payload.project,
                "service": payload.service,
                "version": payload.version
            }
        )

    except Exception as e:
        logger.error(f"Deployment webhook error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing deployment webhook: {str(e)}"
        )


@router.post(
    "/deployment-sync",
    response_model=WebhookResponse,
    summary="Handle deployment webhook (synchronous)",
    description="Process deployment events synchronously and wait for invalidation to complete."
)
async def on_deployment_sync(payload: DeploymentWebhookRequest) -> WebhookResponse:
    """
    Handle deployment webhook synchronously.

    This endpoint processes deployment events immediately and returns
    the invalidation result. Use this when you need confirmation
    that invalidation completed.
    """
    if not webhook_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processor not initialized"
        )

    try:
        # Create deployment event
        event = DeploymentEvent(
            project=payload.project,
            service=payload.service,
            version=payload.version,
            environment=payload.environment,
            timestamp=payload.timestamp
        )

        # Process synchronously
        result = await webhook_processor.process_deployment_webhook(event)

        return WebhookResponse(
            status=result.get("status", "unknown"),
            message=result.get("message"),
            event_id=result.get("event_id"),
            invalidated_count=result.get("invalidated_count"),
            details=result
        )

    except Exception as e:
        logger.error(f"Deployment webhook error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing deployment webhook: {str(e)}"
        )


@router.post(
    "/config-change",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle config change webhook",
    description="Process config change events and invalidate relevant cache entries."
)
async def on_config_change(
    payload: ConfigChangeWebhookRequest,
    background_tasks: BackgroundTasks
) -> WebhookResponse:
    """
    Handle config change webhook and invalidate relevant cache.

    This endpoint receives config change events and invalidates cache
    entries tagged with the project and config type.
    """
    if not webhook_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processor not initialized"
        )

    try:
        # Create config change event
        event = ConfigChangeEvent(
            project=payload.project,
            config_type=payload.config_type,
            changed_keys=payload.changed_keys,
            environment=payload.environment,
            timestamp=payload.timestamp
        )

        # Process in background
        async def process_config_change():
            return await webhook_processor.process_config_change_webhook(event)

        background_tasks.add_task(process_config_change)

        return WebhookResponse(
            status="scheduled",
            message="Config change webhook received, cache invalidation scheduled",
            details={
                "project": payload.project,
                "config_type": payload.config_type,
                "changed_keys_count": len(payload.changed_keys)
            }
        )

    except Exception as e:
        logger.error(f"Config change webhook error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing config change webhook: {str(e)}"
        )


@router.post(
    "/config-change-sync",
    response_model=WebhookResponse,
    summary="Handle config change webhook (synchronous)",
    description="Process config change events synchronously and wait for invalidation to complete."
)
async def on_config_change_sync(payload: ConfigChangeWebhookRequest) -> WebhookResponse:
    """
    Handle config change webhook synchronously.

    This endpoint processes config change events immediately and returns
    the invalidation result.
    """
    if not webhook_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processor not initialized"
        )

    try:
        # Create config change event
        event = ConfigChangeEvent(
            project=payload.project,
            config_type=payload.config_type,
            changed_keys=payload.changed_keys,
            environment=payload.environment,
            timestamp=payload.timestamp
        )

        # Process synchronously
        result = await webhook_processor.process_config_change_webhook(event)

        return WebhookResponse(
            status=result.get("status", "unknown"),
            message=result.get("message"),
            event_id=result.get("event_id"),
            invalidated_count=result.get("invalidated_count"),
            details=result
        )

    except Exception as e:
        logger.error(f"Config change webhook error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing config change webhook: {str(e)}"
        )


class WebhookStatsResponse(BaseModel):
    """Webhook statistics response model."""

    webhooks_processed: int = Field(..., description="Total webhooks processed")
    invalidations_by_tag: int = Field(..., description="Invalidations by tag")
    invalidations_by_key: int = Field(..., description="Invalidations by key")
    tags_created: int = Field(..., description="Total tags created")
    processed_events_count: int = Field(..., description="Events in processed cache")


@router.get(
    "/stats",
    response_model=WebhookStatsResponse,
    summary="Get webhook statistics",
    description="Get statistics about webhook processing and cache invalidation."
)
async def get_webhook_stats() -> WebhookStatsResponse:
    """
    Get webhook processing statistics.

    Returns metrics about webhook processing and cache invalidation
    operations.
    """
    if not webhook_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processor not initialized"
        )

    invalidator_stats = webhook_processor.invalidator.get_stats()

    return WebhookStatsResponse(
        webhooks_processed=invalidator_stats.get("webhooks_processed", 0),
        invalidations_by_tag=invalidator_stats.get("invalidations_by_tag", 0),
        invalidations_by_key=invalidator_stats.get("invalidations_by_key", 0),
        tags_created=invalidator_stats.get("tags_created", 0),
        processed_events_count=webhook_processor.get_processed_count()
    )


class InvalidateRequest(BaseModel):
    """Manual cache invalidation request model."""

    project: str = Field(..., description="Project to invalidate")
    tag: Optional[str] = Field(None, description="Specific tag to invalidate")
    service: Optional[str] = Field(None, description="Service to invalidate")
    config_type: Optional[str] = Field(None, description="Config type to invalidate")

    class Config:
        json_schema_extra = {
            "example": {
                "project": "meinvoice",
                "service": "api-gateway"
            }
        }


@router.post(
    "/invalidate",
    response_model=WebhookResponse,
    summary="Manual cache invalidation",
    description="Manually invalidate cache entries for a project/service/config."
)
async def manual_invalidate(payload: InvalidateRequest) -> WebhookResponse:
    """
    Manually invalidate cache entries.

    This endpoint allows manual triggering of cache invalidation
    for specific projects, services, or config types.
    """
    if not webhook_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processor not initialized"
        )

    try:
        invalidator = webhook_processor.invalidator
        count = 0

        if payload.service:
            # Invalidate by service tag
            tag = f"service:{payload.service}"
            count += await invalidator.invalidate_by_tag(tag)

        if payload.tag:
            # Invalidate by specific tag
            count += await invalidator.invalidate_by_tag(payload.tag)

        if payload.config_type:
            # Invalidate by config type
            count += await invalidator.invalidate_on_config_change(
                payload.project,
                payload.config_type
            )

        # If no specific target, invalidate by project
        if not (payload.service or payload.tag or payload.config_type):
            tag = f"project:{payload.project}"
            count = await invalidator.invalidate_by_tag(tag)

        return WebhookResponse(
            status="success",
            message=f"Invalidated {count} cache entries",
            invalidated_count=count,
            details={
                "project": payload.project,
                "service": payload.service,
                "tag": payload.tag,
                "config_type": payload.config_type
            }
        )

    except Exception as e:
        logger.error(f"Manual invalidation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing manual invalidation: {str(e)}"
        )
