"""Skills API endpoints for Phase 3: Governance & Advanced Skills."""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.skills.registry import get_skill_registry

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/")
async def list_skills(
    category: str | None = None,
    enabled_only: bool = True,
    implemented_only: bool = False,
) -> dict[str, Any]:
    """List all available skills.

    Args:
        category: Optional category filter
        enabled_only: If True, only return enabled skills
        implemented_only: If True, drop skills whose data layer is mock/empty

    Returns:
        Dictionary with skills list
    """
    try:
        registry = get_skill_registry()
        skills = registry.list_skills(
            category=category,
            enabled_only=enabled_only,
            implemented_only=implemented_only,
        )

        return {
            "skills": skills,
            "total": len(skills),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{skill_id}/analyze")
async def execute_skill(
    skill_id: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Execute a skill analysis.

    Args:
        skill_id: ID of skill to execute
        request: Analysis request with project and parameters

    Returns:
        Dictionary with execution ID and result
    """
    try:
        project = request.get("project", "")
        parameters = request.get("parameters", {})
        context = request.get("context", {})

        if not project:
            raise HTTPException(status_code=400, detail="project is required")

        registry = get_skill_registry()
        execution_id, result = await registry.execute(
            skill_id=skill_id,
            project=project,
            parameters=parameters,
            context=context,
        )

        return {
            "execution_id": execution_id,
            "result": result.model_dump(),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{skill_id}/recommendations/{execution_id}")
async def get_skill_recommendations(
    skill_id: str,
    execution_id: str,
    project: str,
) -> dict[str, Any]:
    """Get recommendations from a skill analysis.

    Args:
        skill_id: ID of skill
        execution_id: ID of execution
        project: Project name

    Returns:
        Dictionary with recommendations
    """
    try:
        registry = get_skill_registry()
        recommendations = await registry.get_recommendations(
            skill_id=skill_id,
            analysis_id=execution_id,
            project=project,
        )

        return {
            "recommendations": [r.model_dump() for r in recommendations],
            "total": len(recommendations),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions")
async def list_executions(
    skill_id: str | None = None,
    project: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List recent skill executions.

    Args:
        skill_id: Optional skill filter
        project: Optional project filter
        limit: Maximum results to return

    Returns:
        Dictionary with executions list
    """
    try:
        registry = get_skill_registry()
        history = registry.get_history(
            skill_id=skill_id,
            project=project,
            limit=limit,
        )

        return {
            "executions": history,
            "total": len(history),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_skill_statistics() -> dict[str, Any]:
    """Get skill execution statistics.

    Returns:
        Dictionary with execution statistics
    """
    try:
        registry = get_skill_registry()
        stats = registry.get_statistics()

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
