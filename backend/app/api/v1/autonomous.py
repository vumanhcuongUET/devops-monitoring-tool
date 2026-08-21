"""API endpoints for autonomous actions (Phase 4)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.actions.autonomous_executor import get_autonomous_executor
from app.feedback.analyzer import get_feedback_analyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autonomous", tags=["autonomous"])


@router.get("/status")
async def get_autonomous_status() -> dict[str, Any]:
    """Get status of autonomous executor.

    Returns:
        Dict with rate limit quotas and last executions
    """
    try:
        executor = get_autonomous_executor()
        return executor.get_action_status()
    except Exception as e:
        logger.error(f"Failed to get autonomous status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/summary")
async def get_learning_summary(window_days: int = 30) -> dict[str, Any]:
    """Get learning and feedback summary.

    Args:
        window_days: Number of days to analyze

    Returns:
        Dict with learning metrics
    """
    try:
        analyzer = get_feedback_analyzer(window_days=window_days)
        return analyzer.get_learning_summary()
    except Exception as e:
        logger.error(f"Failed to get learning summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/confidence-report")
async def get_confidence_report(window_days: int = 30) -> dict[str, Any]:
    """Get comprehensive confidence report.

    Args:
        window_days: Number of days to analyze

    Returns:
        Dict with detailed confidence patterns
    """
    try:
        analyzer = get_feedback_analyzer(window_days=window_days)
        metrics = analyzer.generate_confidence_report()

        return {
            "analysis_window_days": window_days,
            "total_actions_analyzed": metrics.total_actions_analyzed,
            "high_confidence_patterns": [
                {
                    "action_type": action_type,
                    "pattern": {
                        "total_actions": pattern.total_actions,
                        "approval_rate": pattern.approval_rate,
                        "success_rate": pattern.success_rate,
                    }
                }
                for action_type, pattern in metrics.action_patterns.items()
                if pattern.confidence_level == "high"
            ],
            "medium_confidence_patterns": [
                {
                    "action_type": action_type,
                    "pattern": {
                        "total_actions": pattern.total_actions,
                        "approval_rate": pattern.approval_rate,
                        "success_rate": pattern.success_rate,
                    }
                }
                for action_type, pattern in metrics.action_patterns.items()
                if pattern.confidence_level == "medium"
            ],
            "low_confidence_patterns": [
                {
                    "action_type": action_type,
                    "pattern": {
                        "total_actions": pattern.total_actions,
                        "approval_rate": pattern.approval_rate,
                        "success_rate": pattern.success_rate,
                    }
                }
                for action_type, pattern in metrics.action_patterns.items()
                if pattern.confidence_level == "low"
            ],
            "auto_approval_candidates": analyzer.get_auto_approval_candidates(),
            "patterns_needing_review": [
                {
                    "action_type": p.action_type,
                    "total_actions": p.total_actions,
                    "approval_rate": p.approval_rate,
                    "success_rate": p.success_rate,
                }
                for p in analyzer.get_patterns_needing_review()
            ],
            "last_updated": next(iter(metrics.action_patterns.values())).last_updated.isoformat() if metrics.action_patterns else None,
        }
    except Exception as e:
        logger.error(f"Failed to get confidence report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
