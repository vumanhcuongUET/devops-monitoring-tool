"""Catalog stub skills (Phase 14 ponytail cut).

The 22 unimplemented skills each used to ship a 300-800 line module whose
fabricated-data generators could never run — the registry refuses stubs
before `analyze()` is called. All that is real about them is the catalog
metadata (id, name, description, category, priority), which this single
class now serves. When a skill gets a real data source, it moves to its
own module, gets registered by a group in registry.py, and its entry is
removed from STUB_SKILLS and STUB_CATALOG here.
"""

from __future__ import annotations

from typing import Any

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

# id -> (name, description, category, priority)
STUB_CATALOG: dict[str, tuple[str, str, SkillCategory, SkillPriority]] = {
    # finops — needs a real billing/cloud-provider client
    "finops_cost_analyzer": (
        "Cost Analyzer",
        "Analyze cloud costs, detect anomalies, and identify optimization opportunities",
        SkillCategory.FINOPS, SkillPriority.HIGH,
    ),
    "finops_idle_resources": (
        "Idle Resources Detector",
        "Find idle or underutilized cloud resources for cost savings",
        SkillCategory.FINOPS, SkillPriority.HIGH,
    ),
    "finops_rightsizing": (
        "Resource Right-Sizing",
        "Optimize resource sizes based on actual utilization patterns",
        SkillCategory.FINOPS, SkillPriority.MEDIUM,
    ),
    # security — needs external scanners / cluster I/O
    "security_vulnerability_scanner": (
        "Vulnerability Scanner",
        "Scan container images and dependencies for security vulnerabilities",
        SkillCategory.SECURITY, SkillPriority.CRITICAL,
    ),
    "security_secret_scanner": (
        "Secret Scanner",
        "Scan code repositories for hardcoded secrets and credentials",
        SkillCategory.SECURITY, SkillPriority.CRITICAL,
    ),
    "security_kube_bench": (
        "Kubernetes CIS Benchmark",
        "Run CIS Kubernetes benchmark security checks using kube-bench",
        SkillCategory.SECURITY, SkillPriority.HIGH,
    ),
    "security_misconfiguration_detector": (
        "Security Misconfiguration Detector",
        "Detect security misconfigurations across application and infrastructure",
        SkillCategory.SECURITY, SkillPriority.HIGH,
    ),
    "security_dependency_confusion": (
        "Dependency Confusion Detector",
        "Detect dependency confusion attacks and supply chain vulnerabilities",
        SkillCategory.SECURITY, SkillPriority.HIGH,
    ),
    "security_runtime_monitor": (
        "Security Runtime Monitor",
        "Monitor runtime security events and detect suspicious activities",
        SkillCategory.SECURITY, SkillPriority.CRITICAL,
    ),
    "security_csp_analyzer": (
        "Security CSP Analyzer",
        "Analyze Content Security Policy, detect unsafe directives, "
        "and generate production-ready CSP policies.",
        SkillCategory.SECURITY, SkillPriority.HIGH,
    ),
    "security_header_validator": (
        "Security Header Validator",
        "Validate security headers across endpoints, check for missing headers, "
        "detect misconfigurations, and provide compliance scoring.",
        SkillCategory.SECURITY, SkillPriority.MEDIUM,
    ),
    "security_secret_exposure_scanner": (
        "Security Secret Exposure Scanner",
        "Advanced secret scanning including git history, container images, "
        "K8s manifests, and CI/CD variable detection.",
        SkillCategory.SECURITY, SkillPriority.HIGH,
    ),
    # code — needs repo I/O / external tools
    "code_dependency_audit": (
        "Dependency Auditor",
        "Audit code dependencies for vulnerabilities, updates, and license compliance",
        SkillCategory.CODE, SkillPriority.HIGH,
    ),
    "code_sast_scanner": (
        "SAST Scanner",
        "Static Application Security Testing for source code vulnerabilities",
        SkillCategory.CODE, SkillPriority.CRITICAL,
    ),
    "code_test_coverage_analyzer": (
        "Test Coverage Analyzer",
        "Analyze test coverage to identify gaps in testing",
        SkillCategory.CODE, SkillPriority.CRITICAL,
    ),
    # devops — no repo/CI I/O
    "devops_config_drift_detector": (
        "Config Drift Detector",
        "Detect configuration drift between Kubernetes environments",
        SkillCategory.DEVOPS, SkillPriority.MEDIUM,
    ),
    "cicd_pipeline_analyzer": (
        "CI/CD Pipeline Analyzer",
        "Analyze CI/CD pipeline for performance, security, and best practices",
        SkillCategory.DEVOPS, SkillPriority.HIGH,
    ),
    # monitoring / observability — needs a dashboard (Grafana) API
    "monitoring_dashboard_auditor": (
        "Dashboard Auditor",
        "Audit monitoring dashboard coverage and identify gaps",
        SkillCategory.MONITORING, SkillPriority.MEDIUM,
    ),
    "observability_dashboard_auditor": (
        "Observability Dashboard Auditor",
        "Audit Grafana dashboards for coverage, quality, and compliance. "
        "Identifies missing dashboards, duplicates, and health issues.",
        SkillCategory.OBSERVABILITY, SkillPriority.MEDIUM,
    ),
    # compliance — needs audit evidence sources
    "compliance_gdpr_auditor": (
        "GDPR Auditor",
        "Audit GDPR compliance for data handling and privacy",
        SkillCategory.COMPLIANCE, SkillPriority.HIGH,
    ),
    "compliance_soc2_auditor": (
        "SOC2 Auditor",
        "Audit SOC2 compliance for security controls",
        SkillCategory.COMPLIANCE, SkillPriority.HIGH,
    ),
    # performance — needs circuit telemetry
    # (performance_load_test_analyzer became real: it parses uploaded
    # k6/locust artifacts — see app/skills/performance/load_test_analyzer.py)
    "performance_circuit_breaker_health": (
        "Performance Circuit Breaker Health",
        "Monitor circuit breaker states, trip patterns, "
        "recovery times, and configuration recommendations.",
        SkillCategory.PERFORMANCE, SkillPriority.HIGH,
    ),
}


class CatalogStubSkill(BaseSkill):
    """Metadata-only placeholder for an unimplemented skill.

    The registry refuses execution (STUB_SKILLS) — analyze() exists only to
    satisfy the ABC and fails loudly if ever reached directly.
    """

    def __init__(self, skill_id: str, config: SkillConfig | None = None):
        name, description, category, priority = STUB_CATALOG[skill_id]
        self.skill_id = skill_id
        self.name = name
        self.description = description
        self.category = category
        self.priority = priority
        self.version = "0.1.0"
        self.implemented = False
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        return AnalysisResult(
            success=False,
            skill_id=self.skill_id,
            errors=[
                f"{self.skill_id} is a catalog stub with no data source — "
                "execution is refused by the registry"
            ],
        )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        return []

    def get_metadata(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "version": self.version,
            "enabled": self.config.enabled,
            "implemented": False,
        }
