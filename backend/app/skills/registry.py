"""Skill Registry for managing and executing skills."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillExecutionError,
    SkillStatus,
    SkillTimeoutError,
)

logger = logging.getLogger(__name__)

# Singleton instance
_skill_registry: Optional["SkillRegistry"] = None

# Skills that have no real data-source integration yet: their fetch/scan layer
# returns empty lists or generated sample data, so results are not actionable.
# Kept registered as a public catalog but flagged and refused on execution.
STUB_SKILLS: frozenset[str] = frozenset({
    # finops — mock billing/cloud-provider clients
    "finops_cost_analyzer",
    "finops_idle_resources",
    "finops_rightsizing",
    # security — mock scanners / fabricated findings
    "security_vulnerability_scanner",
    "security_secret_scanner",
    "security_kube_bench",
    "security_misconfiguration_detector",
    "security_dependency_confusion",
    "security_runtime_monitor",
    "security_csp_analyzer",
    "security_header_validator",
    "security_secret_exposure_scanner",
    # devops — no repo/cluster I/O
    "devops_deployment_health_check",
    "devops_resource_optimizer",
    "devops_config_drift_detector",
    "cicd_pipeline_analyzer",
    "dockerfile_best_practices",
    "kubernetes_manifest_validator",
    # code — no repo I/O
    "code_dependency_audit",
    "code_sast_scanner",
    "code_complexity_analyzer",
    "code_test_coverage_analyzer",
    "code_duplication_detector",
    "code_smell_detector",
    # capacity — synthetic usage data
    "capacity_planner",
    "capacity_bottleneck_detector",
    "capacity_growth_predictor",
    # monitoring — synthetic metrics
    "monitoring_alert_optimizer",
    "monitoring_sli_calculator",
    "monitoring_dashboard_auditor",
    # observability — synthetic time series
    "observability_metrics_analyzer",
    "observability_tracing_analyzer",
    "observability_dashboard_auditor",
    "observability_anomaly_detector",
    "observability_slo_tracker",
    # reliability — synthetic metrics
    "reliability_slo_tracker",
    "reliability_sla_compliance",
    "reliability_dependency_health",
    "reliability_dlq_monitor",
    "reliability_scaling_analyzer",
    # compliance — synthetic audit evidence
    "compliance_gdpr_auditor",
    "compliance_soc2_auditor",
    # performance — synthetic load-test/circuit data
    "performance_load_test_analyzer",
    "performance_circuit_breaker_health",
})


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
        config: SkillConfig | None = None,
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

        # Flag stubs (no real data source) so list/execute can be honest
        temp_instance.implemented = skill_id not in STUB_SKILLS

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

    def get_skill(self, skill_id: str) -> BaseSkill | None:
        """Get a skill instance by ID.

        Args:
            skill_id: ID of skill to get

        Returns:
            Skill instance or None if not found
        """
        return self._instances.get(skill_id)

    def list_skills(
        self,
        category: SkillCategory | None = None,
        enabled_only: bool = True,
        implemented_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List registered skills with the implemented flag in metadata.

        Args:
            category: Optional category filter
            enabled_only: If True, only return enabled skills
            implemented_only: If True, drop skills whose data layer is mock/empty

        Returns:
            List of skill metadata dictionaries
        """
        skills = []
        for skill_id, instance in self._instances.items():
            if enabled_only and not self._configs[skill_id].enabled:
                continue
            if implemented_only and not instance.implemented:
                continue
            if category and instance.category != category:
                continue

            skills.append({
                **instance.get_metadata(),
                "config": self._configs[skill_id].model_dump(),
            })

        return skills

    def get_skill_config(self, skill_id: str) -> SkillConfig | None:
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

        # Recreate instance with new config (re-apply stub flag)
        skill_class = self._skills[skill_id]
        instance = skill_class(config)
        instance.implemented = skill_id not in STUB_SKILLS
        self._instances[skill_id] = instance

        logger.info(f"Updated config for skill: {skill_id}")

    async def execute(
        self,
        skill_id: str,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
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

        # Refuse stub skills — their output is mock data, not actionable analysis
        if not skill.implemented:
            raise ValueError(
                f"Skill {skill_id} is not implemented yet: its data layer returns "
                "mock/empty data. See SkillRegistry.STUB_SKILLS."
            )

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
            raise error from None

        except Exception as e:
            self._status[skill_id] = SkillStatus.FAILED
            logger.error(f"Skill {skill_id} failed: {e}")
            raise SkillExecutionError(skill_id, str(e)) from e

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

    def get_result(self, execution_id: str) -> AnalysisResult | None:
        """Get analysis result by execution ID.

        Args:
            execution_id: ID of execution

        Returns:
            AnalysisResult or None
        """
        return self._results.get(execution_id)

    def get_status(self, skill_id: str) -> SkillStatus | None:
        """Get current status of a skill.

        Args:
            skill_id: ID of skill

        Returns:
            SkillStatus or None
        """
        return self._status.get(skill_id)

    def get_history(
        self,
        skill_id: str | None = None,
        project: str | None = None,
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
    config: SkillConfig | None = None,
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

    from app.skills import (
        capacity,
        code,
        devops,
        finops,
        observability,
        performance,
        reliability,
        security,
    )

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

    for _category, module in category_modules.items():
        # Find all modules in the category package
        for _importer, modname, _ispkg in pkgutil.iter_modules(module.__path__):
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
            DependencyConfusionSkill,
            KubeBenchSkill,
            MisconfigurationDetectorSkill,
            SecretScannerSkill,
            SecurityRuntimeMonitorSkill,
            VulnerabilityScannerSkill,
        )
        registry.register(VulnerabilityScannerSkill)
        registry.register(SecretScannerSkill)
        registry.register(KubeBenchSkill)
        registry.register(MisconfigurationDetectorSkill)
        registry.register(DependencyConfusionSkill)
        registry.register(SecurityRuntimeMonitorSkill)

        # Register DevOps skills
        from app.skills.devops import (
            CicdPipelineAnalyzerSkill,
            ConfigDriftDetectorSkill,
            DeploymentHealthCheckSkill,
            DockerfileBestPracticesSkill,
            KubernetesManifestValidatorSkill,
            ResourceOptimizerSkill,
        )
        registry.register(DeploymentHealthCheckSkill)
        registry.register(ResourceOptimizerSkill)
        registry.register(ConfigDriftDetectorSkill)
        registry.register(CicdPipelineAnalyzerSkill)
        registry.register(DockerfileBestPracticesSkill)
        registry.register(KubernetesManifestValidatorSkill)

        # Register Code skills
        from app.skills.code import (
            CodeSmellDetectorSkill,
            ComplexityAnalyzerSkill,
            DependencyAuditSkill,
            DuplicationDetectorSkill,
            SastScannerSkill,
            TestCoverageAnalyzerSkill,
        )
        registry.register(DependencyAuditSkill)
        registry.register(SastScannerSkill)
        registry.register(ComplexityAnalyzerSkill)
        registry.register(TestCoverageAnalyzerSkill)
        registry.register(DuplicationDetectorSkill)
        registry.register(CodeSmellDetectorSkill)

        # Register Capacity skills
        from app.skills.capacity import (
            BottleneckDetectorSkill,
            CapacityPlannerSkill,
            GrowthPredictorSkill,
        )
        registry.register(CapacityPlannerSkill)
        registry.register(BottleneckDetectorSkill)
        registry.register(GrowthPredictorSkill)

        # Register Monitoring skills
        from app.skills.monitoring import (
            AlertOptimizerSkill,
            DashboardAuditorSkill,
            SLICalculatorSkill,
        )
        registry.register(AlertOptimizerSkill)
        registry.register(SLICalculatorSkill)
        registry.register(DashboardAuditorSkill)

        # Register Reliability skills
        from app.skills.reliability import (
            DependencyHealthSkill,
            SLAComplianceSkill,
            SLOTrackerSkill,
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
            AnomalyDetectorSkill,
            DashboardAuditorSkill,
            MetricsAnalyzerSkill,
            TracingAnalyzerSkill,
        )
        from app.skills.observability import (
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
            DLQMonitorSkill,
            ScalingAnalyzerSkill,
        )
        registry.register(ScalingAnalyzerSkill)
        registry.register(DLQMonitorSkill)

        # Register Phase 5: Performance skills
        from app.skills.performance import (
            CircuitBreakerHealthSkill,
            LoadTestAnalyzerSkill,
        )
        registry.register(LoadTestAnalyzerSkill)
        registry.register(CircuitBreakerHealthSkill)

        logger.info("Skill registry initialized with all built-in skills (44 total)")

    except Exception as e:
        # One bad group must not abort registration of the rest, whatever the
        # exception type (e.g. httpx missing-h2 ImportError surfaced here).
        logger.warning(f"Failed to initialize some skills: {e}")


# Auto-initialize on module import (can be disabled via settings)
_initialize_registry()
