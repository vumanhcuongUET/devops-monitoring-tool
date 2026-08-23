"""
API v1 Router - Main router for all v1 endpoints.

Includes all API modules for the monitoring platform.
"""

from fastapi import APIRouter

from app.api.v1 import (
    overview,
    analyze,
    alerts,
    actions,
    skills,
    optimization
)

# Create main v1 router
api_router = APIRouter()

# Include all routers
api_router.include_router(overview.router, prefix="/overview", tags=["overview"])
api_router.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(actions.router, prefix="/actions", tags=["actions"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(optimization.router, tags=["optimization"])

__all__ = ["api_router"]
