"""Skill Registry for managing and executing skills."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.skills.base import (
    BaseSkill,
    SkillConfig,
    SkillCategory,
    SkillExecutionError,
    SkillTimeoutError,
    AnalysisResult,
    Recommendation,
    SkillStatus,
)

logger = logging.getLogger(__name__)

# Singleton instance
_skill_registry: Optional["SkillRegistry"] = None


class SkillRegistry:
    """Registry for managing and executing skills.

    This registry:
    - Discovers and loads available skills
    - Manages skill configurations
    - Executes skill analyses
    - Tracks execution history
    """

    MAX_HISTORY_SIZE = 5000  # Maximum skill execution history entries to keep

    def __init__(self):
        """Initialize the skill registry."""
        self._skills: dict[str, type[BaseSkill]] = {}
        self._instances: dict[str, BaseSkill] = {}
        self._configs: dict[str, SkillConfig] = {}
        self._results: dict[str, AnalysisResult] = {}
        self._status: dict[str, SkillStatus] = {}
        self._history: list[dict[str, Any]] = []

    def register(
        self,
        skill_class: type[BaseSkill],
        config: Optional[SkillConfig] = None,
    ) -> None:
        """Register a skill class.

        Args:
            skill_class: Skill class to register
            config: Optional skill configuration

        Raises:
            ValueError: If skill_id is already registered
        """
        # Create temporary instance to get metadata
        temp_instance = skill_class(config)
        skill_id = temp_instance.skill_id

        if skill_id in self._skills:
            raise ValueError(f"Skill {skill_id} already registered")

        self._skills[skill_id] = skill_class
        self._configs[skill_id] = config or SkillConfig()
        self._instances[skill_id] = temp_instance

        logger.info(f"Registered skill: {skill_id} ({temp_instance.name})")

    def unregister(self, skill_id: str) -> None:
        """Unregister a skill.

        Args:
            skill_id: ID of skill to unregister
        """
        if skill_id in self._skills:
            del self._skills[skill_id]
            del self._configs[skill_id]
            del self._instances[skill_id]
            logger.info(f"Unregistered skill: {skill_id}")

    def get_skill(self, skill_id: str) -> Optional[BaseSkill]:
        """Get a skill instance by ID.

        Args:
            skill_id: ID of skill to get

        Returns:
            Skill instance or None if not found
        """
        return self._instances.get(skill_id)

    def list_skills(
        self,
        category: Optional[SkillCategory] = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List all registered skills.

        Args:
            category: Optional category filter
            enabled_only: If True, only return enabled skills

        Returns:
            List of skill metadata dictionaries
        """
        skills = []
        for skill_id, instance in self._instances.items():
            if enabled_only and not self._configs[skill_id].enabled:
                continue
            if category and instance.category != category:
                continue

            skills.append({
                **instance.get_metadata(),
                "config": self._configs[skill_id].model_dump(),
            })

        return skills

    def get_skill_config(self, skill_id: str) -> Optional[SkillConfig]:
        """Get skill configuration.

        Args:
            skill_id: ID of skill

        Returns:
            Skill configuration or None
        """
        return self._configs.get(skill_id)

    def update_skill_config(
        self,
        skill_id: str,
        config: SkillConfig,
    ) -> None:
        """Update skill configuration.

        Args:
            skill_id: ID of skill
            config: New configuration

        Raises:
            ValueError: If skill not found
        """
        if skill_id not in self._instances:
            raise ValueError(f"Skill {skill_id} not found")

        self._configs[skill_id] = config

        # Recreate instance with new config
        skill_class = self._skills[skill_id]
        self._instances[skill_id] = skill_class(config)

        logger.info(f"Updated config for skill: {skill_id}")

    async def execute(
        self,
        skill_id: str,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[str, AnalysisResult]:
        """Execute a skill analysis.

        Args:
            skill_id: ID of skill to execute
            project: Project/service name
            parameters: Skill-specific parameters
            context: Additional context

        Returns:
            AnalysisResult containing findings

        Raises:
            ValueError: If skill not found or disabled
            SkillExecutionError: If execution fails
        """
        skill = self._instances.get(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        config = self._configs.get(skill_id)
        if not config or not config.enabled:
            raise ValueError(f"Skill {skill_id} is disabled")

        # Validate parameters
        is_valid, errors = skill.validate_parameters(parameters)
        if not is_valid:
            raise ValueError(f"Invalid parameters: {', '.join(errors)}")

        # Update status
        execution_id = str(uuid.uuid4())
        self._status[skill_id] = SkillStatus.RUNNING

        start_time = datetime.now(timezone.utc)

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                skill.analyze(project, parameters, context),
                timeout=config.timeout_seconds,
            )

            # Store result
            result.skill_id = skill_id
            self._results[execution_id] = result
            self._status[skill_id] = SkillStatus.COMPLETED

            # Log to history
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self._history.append({
                "id": execution_id,
                "skill_id": skill_id,
                "project": project,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "success": result.success,
            })

            # Trim history to prevent unbounded growth
            if len(self._history) > self.MAX_HISTORY_SIZE:
                # Remove oldest entries (FIFO)
                excess = len(self._history) - self.MAX_HISTORY_SIZE
                self._history = self._history[excess:]

            logger.info(f"Skill {skill_id} completed in {duration:.2f}s")
            return execution_id, result

        except asyncio.TimeoutError:
            self._status[skill_id] = SkillStatus.FAILED
            error = SkillTimeoutError(skill_id, f"Execution timed out after {config.timeout_seconds}s")
            logger.error(str(error))
            raise error

        except Exception as e:
            self._status[skill_id] = SkillStatus.FAILED
            logger.error(f"Skill {skill_id} failed: {e}")
            raise SkillExecutionError(skill_id, str(e))

    async def get_recommendations(
        self,
        skill_id: str,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Get recommendations from a skill analysis.

        Args:
            skill_id: ID of skill
            analysis_id: ID of analysis result
            project: Project name

        Returns:
            List of recommendations
        """
        skill = self._instances.get(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        return await skill.get_recommendations(analysis_id, project)

    def get_result(self, execution_id: str) -> Optional[AnalysisResult]:
        """Get analysis result by execution ID.

        Args:
            execution_id: ID of execution

        Returns:
            AnalysisResult or None
        """
        return self._results.get(execution_id)

    def get_status(self, skill_id: str) -> Optional[SkillStatus]:
        """Get current status of a skill.

        Args:
            skill_id: ID of skill

        Returns:
            SkillStatus or None
        """
        return self._status.get(skill_id)

    def get_history(
        self,
        skill_id: Optional[str] = None,
        project: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get execution history.

        Args:
            skill_id: Optional skill filter
            project: Optional project filter
            limit: Maximum results to return

        Returns:
            List of history entries
        """
        history = self._history

        if skill_id:
            history = [h for h in history if h["skill_id"] == skill_id]
        if project:
            history = [h for h in history if h["project"] == project]

        return history[-limit:]

    def get_statistics(self) -> dict[str, Any]:
        """Get execution statistics.

        Returns:
            Dictionary with statistics
        """
        total = len(self._history)
        if total == 0:
            return {
                "total_executions": 0,
                "successful": 0,
                "failed": 0,
                "average_duration": 0,
                "by_skill": {},
                "by_project": {},
            }

        successful = sum(1 for h in self._history if h["success"])
        failed = total - successful

        duration_sum = sum(h.get("duration_seconds", 0) for h in self._history)
        avg_duration = duration_sum / total

        by_skill: dict[str, int] = {}
        by_project: dict[str, int] = {}

        for h in self._history:
            skill_id = h["skill_id"]
            project = h["project"]
            by_skill[skill_id] = by_skill.get(skill_id, 0) + 1
            by_project[project] = by_project.get(project, 0) + 1

        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "average_duration": avg_duration,
            "by_skill": by_skill,
            "by_project": by_project,
        }


def get_skill_registry() -> SkillRegistry:
    """Get or create the singleton SkillRegistry instance.

    Returns:
        SkillRegistry instance
    """
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry


def register_skill(
    skill_class: type[BaseSkill],
    config: Optional[SkillConfig] = None,
) -> None:
    """Register a skill with the global registry.

    Args:
        skill_class: Skill class to register
        config: Optional configuration
    """
    registry = get_skill_registry()
    registry.register(skill_class, config)


def discover_skills() -> None:
    """Discover and register all skills in the skills package.

    This function imports all skill modules and registers their skills.
    """
    import importlib
    import pkgutil

    from app.skills import finops, security, capacity, devops, code
    from app.skills import observability, reliability, performance

    # Map category to module
    category_modules = {
        SkillCategory.FINOPS: finops,
        SkillCategory.SECURITY: security,
        SkillCategory.CAPACITY: capacity,
        SkillCategory.DEVOPS: devops,
        SkillCategory.CODE: code,
        SkillCategory.OBSERVABILITY: observability,
        SkillCategory.RELIABILITY: reliability,
        SkillCategory.PERFORMANCE: performance,
    }

    for category, module in category_modules.items():
        # Find all modules in the category package
        for importer, modname, ispkg in pkgutil.iter_modules(module.__path__):
            if modname.startswith("_"):
                continue

            try:
                full_module = f"{module.__name__}.{modname}"
                importlib.import_module(full_module)
                logger.debug(f"Discovered skill module: {full_module}")
            except ImportError as e:
                logger.warning(f"Failed to import {modname}: {e}")


# Initialize registry with built-in skills on import
def _initialize_registry():
    """Initialize the skill registry with built-in skills."""
    try:
        registry = get_skill_registry()

        # Register FinOps skills
        from app.skills.finops import (
            CostAnalyzerSkill,
            IdleResourcesSkill,
            RightSizingSkill,
        )
        registry.register(CostAnalyzerSkill)
        registry.register(IdleResourcesSkill)
        registry.register(RightSizingSkill)

        # Register Security skills
        from app.skills.security import (
            VulnerabilityScannerSkill,
            SecretScannerSkill,
            KubeBenchSkill,
            MisconfigurationDetectorSkill,
            DependencyConfusionSkill,
            SecurityRuntimeMonitorSkill,
        )
        registry.register(VulnerabilityScannerSkill)
        registry.register(SecretScannerSkill)
        registry.register(KubeBenchSkill)
        registry.register(MisconfigurationDetectorSkill)
        registry.register(DependencyConfusionSkill)
        registry.register(SecurityRuntimeMonitorSkill)

        # Register DevOps skills
        from app.skills.devops import (
            DeploymentHealthCheckSkill,
            ResourceOptimizerSkill,
            ConfigDriftDetectorSkill,
            CicdPipelineAnalyzerSkill,
            DockerfileBestPracticesSkill,
            KubernetesManifestValidatorSkill,
        )
        registry.register(DeploymentHealthCheckSkill)
        registry.register(ResourceOptimizerSkill)
        registry.register(ConfigDriftDetectorSkill)
        registry.register(CicdPipelineAnalyzerSkill)
        registry.register(DockerfileBestPracticesSkill)
        registry.register(KubernetesManifestValidatorSkill)

        # Register Code skills
        from app.skills.code import (
            DependencyAuditSkill,
            SastScannerSkill,
            ComplexityAnalyzerSkill,
            TestCoverageAnalyzerSkill,
            DuplicationDetectorSkill,
            CodeSmellDetectorSkill,
        )
        registry.register(DependencyAuditSkill)
        registry.register(SastScannerSkill)
        registry.register(ComplexityAnalyzerSkill)
        registry.register(TestCoverageAnalyzerSkill)
        registry.register(DuplicationDetectorSkill)
        registry.register(CodeSmellDetectorSkill)

        # Register Capacity skills
        from app.skills.capacity import (
            CapacityPlannerSkill,
            BottleneckDetectorSkill,
            GrowthPredictorSkill,
        )
        registry.register(CapacityPlannerSkill)
        registry.register(BottleneckDetectorSkill)
        registry.register(GrowthPredictorSkill)

        # Register Monitoring skills
        from app.skills.monitoring import (
            AlertOptimizerSkill,
            SLICalculatorSkill,
            DashboardAuditorSkill,
        )
        registry.register(AlertOptimizerSkill)
        registry.register(SLICalculatorSkill)
        registry.register(DashboardAuditorSkill)

        # Register Reliability skills
        from app.skills.reliability import (
            SLOTrackerSkill,
            SLAComplianceSkill,
            DependencyHealthSkill,
        )
        registry.register(SLOTrackerSkill)
        registry.register(SLAComplianceSkill)
        registry.register(DependencyHealthSkill)

        # Register Compliance skills
        from app.skills.compliance import (
            GDPRAuditorSkill,
            SOC2AuditorSkill,
        )
        registry.register(GDPRAuditorSkill)
        registry.register(SOC2AuditorSkill)

        # Register Phase 5: Observability skills
        from app.skills.observability import (
            MetricsAnalyzerSkill,
            TracingAnalyzerSkill,
            DashboardAuditorSkill,
            AnomalyDetectorSkill,
            SLOTrackerSkill as ObservabilitySLOTrackerSkill,
        )
        registry.register(MetricsAnalyzerSkill)
        registry.register(TracingAnalyzerSkill)
        registry.register(DashboardAuditorSkill)
        registry.register(AnomalyDetectorSkill)
        registry.register(ObservabilitySLOTrackerSkill)

        # Register Phase 5: Security skills
        from app.skills.security import (
            CSPAnalyzerSkill,
            HeaderValidatorSkill,
            SecretExposureScannerSkill,
        )
        registry.register(CSPAnalyzerSkill)
        registry.register(HeaderValidatorSkill)
        registry.register(SecretExposureScannerSkill)

        # Register Phase 5: Reliability skills
        from app.skills.reliability import (
            ScalingAnalyzerSkill,
            DLQMonitorSkill,
        )
        registry.register(ScalingAnalyzerSkill)
        registry.register(DLQMonitorSkill)

        # Register Phase 5: Performance skills
        from app.skills.performance import (
            LoadTestAnalyzerSkill,
            CircuitBreakerHealthSkill,
        )
        registry.register(LoadTestAnalyzerSkill)
        registry.register(CircuitBreakerHealthSkill)

        logger.info("Skill registry initialized with all built-in skills (44 total)")

    except ImportError as e:
        logger.warning(f"Failed to initialize some skills: {e}")


# Auto-initialize on module import (can be disabled via settings)
_initialize_registry()
