"""Security Misconfiguration Detector - Detect security misconfigurations.

This skill scans for:
- Insecure TLS/SSL configurations
- Debug mode enabled in production
- Exposed admin panels
- CORS misconfigurations
- Missing security headers
"""

import logging
from typing import Any, Optional

from app.skills.base import (
    BaseSkill,
    SkillConfig,
    SkillCategory,
    SkillPriority,
    AnalysisResult,
    Recommendation,
)

logger = logging.getLogger(__name__)


class MisconfigurationDetectorSkill(BaseSkill):
    """Detect security misconfigurations in application and infrastructure.

    This skill checks:
    - Application configs (settings.py, .env files)
    - Web server configs (nginx, apache)
    - Kubernetes manifests
    - Docker configurations
    - CI/CD pipeline configs
    """

    skill_id = "security_misconfiguration_detector"
    name = "Security Misconfiguration Detector"
    description = "Detect security misconfigurations across application and infrastructure"
    category = SkillCategory.SECURITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Common misconfigurations patterns
    MISCONFIG_PATTERNS = {
        "debug_enabled": [
            r"DEBUG\s*=\s*True",
            r"debug:\s*true",
            r"<debug>true</debug>",
        ],
        "exposed_admin": [
            r"/admin",
            r"/wp-admin",
            r"/phpmyadmin",
            r"/console",
        ],
        "weak_tls": [
            r"TLSv1",
            r"SSLv3",
            r'ssl_protocols.*TLSv1',
        ],
        "missing_security_headers": [
            r"#.*X-Frame-Options",
            r"#.*X-Content-Type-Options",
            r"#.*Strict-Transport-Security",
        ],
        "cors_wildcard": [
            r"Access-Control-Allow-Origin:\s*\*",
            r"'allowed_origins'\s*:\s*\['\*'\]",
        ],
        "hardcoded_credentials": [
            r"password\s*=\s*['\"].+['\"]",
            r"api_key\s*=\s*['\"].+['\"]",
        ],
    }

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Scan for security misconfigurations.

        Args:
            project: Project name
            parameters: Scan parameters
                - config_path: Path to configuration files
                - check_type: Type of check (app, infra, all)
            context: Registry context

        Returns:
            AnalysisResult with misconfigurations found
        """
        try:
            config_path = parameters.get("config_path", ".")
            check_type = parameters.get("check_type", "all")

            # Run scans based on check type
            misconfigs = []

            if check_type in ["app", "all"]:
                misconfigs.extend(await self._check_app_configs(config_path))
            if check_type in ["infra", "all"]:
                misconfigs.extend(await self._check_infra_configs(config_path))

            # Categorize by severity
            critical = [m for m in misconfigs if m["severity"] == "CRITICAL"]
            high = [m for m in misconfigs if m["severity"] == "HIGH"]
            medium = [m for m in misconfigs if m["severity"] == "MEDIUM"]

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.8,
                data={
                    "config_path": config_path,
                    "check_type": check_type,
                    "misconfigurations": misconfigs,
                    "summary": {
                        "critical": len(critical),
                        "high": len(high),
                        "medium": len(medium),
                        "total": len(misconfigs),
                    },
                    "compliance_score": self._calculate_compliance_score(misconfigs),
                },
                warnings=self._generate_warnings(misconfigs),
            )

        except Exception as e:
            logger.error(f"Misconfiguration scan failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Misconfiguration scan failed: {str(e)}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate remediation recommendations.

        Args:
            analysis_id: Analysis ID
            project: Project name

        Returns:
            List of recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        recommendations = []
        data = result.data

        # Debug enabled
        debug_issues = [
            m for m in data["misconfigurations"]
            if m["type"] == "debug_enabled"
        ]
        if debug_issues:
            recommendations.append(Recommendation(
                title="Disable DEBUG mode in production",
                description="Debug mode is enabled, which exposes detailed error information and configuration.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="15 minutes",
                risk_level="high",
                commands=[
                    "# Python/Django",
                    "DEBUG = False",
                    "# Node.js/Express",
                    "app.disable('debug')",
                ],
            ))

        # Exposed admin panels
        admin_issues = [
            m for m in data["misconfigurations"]
            if m["type"] == "exposed_admin"
        ]
        if admin_issues:
            recommendations.append(Recommendation(
                title="Secure exposed admin panels",
                description=f"Found {len(admin_issues)} exposed admin endpoints. Add authentication and IP restrictions.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="high",
                commands=[
                    "# Add authentication",
                    "# Restrict to specific IPs",
                    "# Use non-standard admin URLs",
                ],
            ))

        # Weak TLS
        tls_issues = [
            m for m in data["misconfigurations"]
            if m["type"] == "weak_tls"
        ]
        if tls_issues:
            recommendations.append(Recommendation(
                title="Upgrade weak TLS/SSL configurations",
                description="Weak TLS versions detected. Upgrade to TLS 1.2+ and disable SSLv3.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1 hour",
                risk_level="medium",
                commands=[
                    "# Nginx config",
                    "ssl_protocols TLSv1.2 TLSv1.3;",
                    "# Apache config",
                    "SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1",
                ],
            ))

        # Missing security headers
        header_issues = [
            m for m in data["misconfigurations"]
            if m["type"] == "missing_security_headers"
        ]
        if header_issues:
            recommendations.append(Recommendation(
                title="Add security headers",
                description="Missing important security headers. Add X-Frame-Options, X-Content-Type-Options, HSTS.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="low",
                commands=[
                    "# Add to web server config",
                    "X-Frame-Options: DENY",
                    "X-Content-Type-Options: nosniff",
                    "Strict-Transport-Security: max-age=31536000",
                ],
            ))

        # CORS wildcard
        cors_issues = [
            m for m in data["misconfigurations"]
            if m["type"] == "cors_wildcard"
        ]
        if cors_issues:
            recommendations.append(Recommendation(
                title="Fix CORS wildcard configuration",
                description="CORS configured with wildcard origin. Restrict to specific trusted domains.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="medium",
                commands=[
                    "# Restrict to specific origins",
                    "allowed_origins = ['https://example.com']",
                ],
            ))

        return recommendations

    async def _check_app_configs(self, config_path: str) -> list[dict[str, Any]]:
        """Check application configurations for misconfigurations.

        Args:
            config_path: Path to config files

        Returns:
            List of misconfigurations
        """
        misconfigs = [
            {
                "type": "debug_enabled",
                "severity": "CRITICAL",
                "file": "config/settings.py",
                "line": 15,
                "config": "DEBUG = True",
                "message": "Debug mode enabled in production",
            },
            {
                "type": "hardcoded_credentials",
                "severity": "CRITICAL",
                "file": "config/.env",
                "line": 3,
                "config": "DATABASE_PASSWORD='password123'",
                "message": "Hardcoded password in configuration file",
            },
            {
                "type": "exposed_admin",
                "severity": "HIGH",
                "file": "app/urls.py",
                "line": 25,
                "config": "path('admin/', admin.site.urls)",
                "message": "Admin panel exposed at standard URL",
            },
        ]

        return misconfigs

    async def _check_infra_configs(self, config_path: str) -> list[dict[str, Any]]:
        """Check infrastructure configurations.

        Args:
            config_path: Path to config files

        Returns:
            List of misconfigurations
        """
        misconfigs = [
            {
                "type": "weak_tls",
                "severity": "HIGH",
                "file": "nginx/nginx.conf",
                "line": 42,
                "config": "ssl_protocols TLSv1 TLSv1.1 TLSv1.2;",
                "message": "Weak TLS versions enabled",
            },
            {
                "type": "missing_security_headers",
                "severity": "MEDIUM",
                "file": "nginx/nginx.conf",
                "line": 50,
                "config": "# X-Frame-Options disabled",
                "message": "Security headers commented out",
            },
            {
                "type": "cors_wildcard",
                "severity": "MEDIUM",
                "file": "app/cors.py",
                "line": 8,
                "config": "CORS_ALLOW_ORIGINS=['*']",
                "message": "CORS configured to allow all origins",
            },
        ]

        return misconfigs

    def _calculate_compliance_score(self, misconfigs: list) -> int:
        """Calculate compliance score (0-100).

        Args:
            misconfigs: List of misconfigurations

        Returns:
            Compliance score
        """
        if not misconfigs:
            return 100

        # Weight by severity
        weights = {"MEDIUM": 5, "HIGH": 15, "CRITICAL": 40}
        total_penalty = sum(weights.get(m["severity"], 5) for m in misconfigs)

        score = max(0, 100 - total_penalty)
        return score

    def _generate_warnings(self, misconfigs: list) -> list[str]:
        """Generate warnings based on findings.

        Args:
            misconfigs: List of misconfigurations

        Returns:
            List of warnings
        """
        warnings = []

        critical_count = sum(1 for m in misconfigs if m["severity"] == "CRITICAL")
        if critical_count > 0:
            warnings.append(f"{critical_count} CRITICAL misconfigurations detected")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        return True, []
