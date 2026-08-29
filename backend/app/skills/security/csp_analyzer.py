"""Security CSP Analyzer Skill.

Analyzes and recommends Content Security Policy improvements.
Detects unsafe directives and generates production-ready CSP policies.
"""

import logging
from typing import Any

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)


class CSPAnalyzerSkill(BaseSkill):
    """Analyze and recommend Content Security Policy improvements.

    This skill analyzes CSP headers to:
    - Parse and validate current CSP configuration
    - Detect unsafe directives ('unsafe-inline', 'unsafe-eval')
    - Identify report-only violations
    - Generate production-ready CSP policies
    - Provide migration path from permissive to strict CSP

    Example usage:
        skill = CSPAnalyzerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "url": "https://api.example.com",
                "environment": "production"
            }
        )
    """

    skill_id = "security_csp_analyzer"
    name = "Security CSP Analyzer"
    description = (
        "Analyze Content Security Policy, detect unsafe directives, "
        "and generate production-ready CSP policies."
    )
    category = SkillCategory.SECURITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Unsafe CSP directives that should be avoided
    UNSAFE_DIRECTIVES = ["unsafe-inline", "unsafe-eval", "unsafe-hashes"]

    # Standard CSP directives
    STANDARD_DIRECTIVES = [
        "default-src",
        "script-src",
        "style-src",
        "img-src",
        "connect-src",
        "font-src",
        "object-src",
        "media-src",
        "frame-src",
        "base-uri",
        "form-action",
        "frame-ancestors",
        "report-uri",
        "report-to",
    ]

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the CSP analyzer skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run CSP analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - url: URL to check for CSP header (optional)
                - csp_header: Raw CSP header value (optional)
                - environment: Environment context (default: production)
            context: Additional context from registry

        Returns:
            AnalysisResult with CSP analysis data
        """
        try:
            # Extract parameters
            url = parameters.get("url")
            csp_header = parameters.get("csp_header")
            environment = parameters.get("environment", "production")

            # Get CSP header (from URL or direct input)
            if not csp_header and url:
                csp_header = await self._fetch_csp_header(url)

            if not csp_header:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["No CSP header provided or found"],
                    metadata={"project": project, "url": url},
                )

            # Parse and analyze CSP
            parsed_csp = self._parse_csp(csp_header)
            analysis = self._analyze_csp(parsed_csp, environment)

            # Generate recommendations
            recommendations_data = self._generate_recommendations_data(
                parsed_csp, analysis, environment
            )

            # Calculate security score
            security_score = self._calculate_security_score(parsed_csp, analysis)

            # Calculate confidence
            confidence = self._calculate_confidence(parsed_csp)

            # Generate warnings
            warnings = self._generate_warnings(analysis)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "url": url,
                    "environment": environment,
                    "csp_header": csp_header,
                    "parsed_csp": parsed_csp,
                    "analysis": analysis,
                    "security_score": security_score,
                    "recommendations": recommendations_data,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "environment": environment,
                },
            )

        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[str(e)],
                metadata={"project": project},
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate recommendations based on CSP analysis.

        Args:
            analysis_id: ID of previous analysis result
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
        analysis = data.get("analysis", {})
        security_score = data.get("security_score", 0)

        # Critical: unsafe-inline detected
        if analysis.get("has_unsafe_inline"):
            recommendations.append(
                Recommendation(
                    title="Remove 'unsafe-inline' from CSP",
                    description="The 'unsafe-inline' directive allows inline scripts/styles, "
                    "which exposes the application to XSS attacks.",
                    priority=SkillPriority.HIGH,
                    action_type="fix",
                    estimated_effort="4-8 hours",
                    risk_level="high",
                    commands=[
                        "Implement nonce-based CSP",
                        "Move scripts to external files",
                        "Use template helpers for nonce generation",
                    ],
                    references=[
                        "https://web.dev/strict-csp/",
                        "https://owasp.org/www-project/secure-headers/",
                    ],
                )
            )

        # High: unsafe-eval detected
        if analysis.get("has_unsafe_eval"):
            recommendations.append(
                Recommendation(
                    title="Remove 'unsafe-eval' from CSP",
                    description="The 'unsafe-eval' directive allows eval() and similar functions, "
                    "which can lead to code injection vulnerabilities.",
                    priority=SkillPriority.HIGH,
                    action_type="fix",
                    estimated_effort="2-4 hours",
                    risk_level="high",
                    commands=[
                        "Remove eval() usage",
                        "Use alternative code patterns",
                        "Implement safe dynamic code loading",
                    ],
                )
            )

        # Medium: Wildcard sources detected
        if analysis.get("has_wildcard_sources"):
            recommendations.append(
                Recommendation(
                    title="Restrict Wildcard Sources in CSP",
                    description="Wildcard sources (*) allow loading from any origin, "
                    "which bypasses CSP protections.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Replace * with specific domains",
                        "Use source lists instead of wildcards",
                        "Consider using CSP hashes for specific resources",
                    ],
                )
            )

        # Medium: Missing important directives
        missing = analysis.get("missing_directives", [])
        critical_missing = ["object-src", "base-uri", "form-action"]
        if any(m in critical_missing for m in missing):
            recommendations.append(
                Recommendation(
                    title="Add Missing Critical CSP Directives",
                    description=f"Missing critical directives: "
                    f"{', '.join([m for m in missing if m in critical_missing])}",
                    priority=SkillPriority.MEDIUM,
                    action_type="add",
                    estimated_effort="30 minutes",
                    risk_level="medium",
                    commands=[
                        "Add object-src 'none'",
                        "Add base-uri 'self'",
                        "Add form-action 'self'",
                    ],
                    references=["https://web.dev/strict-csp/"],
                )
            )

        # Low: No reporting configured
        if not analysis.get("has_reporting"):
            recommendations.append(
                Recommendation(
                    title="Add CSP Reporting",
                    description="CSP violation reporting helps detect issues before enforcing "
                    "strict policies.",
                    priority=SkillPriority.LOW,
                    action_type="add",
                    estimated_effort="1-2 hours",
                    risk_level="low",
                    commands=[
                        "Set up CSP report endpoint",
                        "Add report-uri or report-to directive",
                        "Monitor CSP violation reports",
                    ],
                )
            )

        # Overall score recommendation
        if security_score < 70:
            recommendations.append(
                Recommendation(
                    title="Improve CSP Security Score",
                    description=f"Current CSP security score is {security_score}/100. "
                    f"Implement recommended changes to improve security.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="1-2 days",
                    risk_level="medium",
                    commands=[
                        "Review all CSP recommendations",
                        "Implement changes incrementally",
                        "Test with report-only mode first",
                    ],
                )
            )

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate analysis parameters.

        Args:
            parameters: Parameters to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # At least one of url or csp_header must be provided
        if not parameters.get("url") and not parameters.get("csp_header"):
            errors.append("Either 'url' or 'csp_header' parameter is required")

        # Validate environment
        environment = parameters.get("environment", "production")
        if environment not in ["production", "staging", "development"]:
            errors.append("environment must be one of: production, staging, development")

        return len(errors) == 0, errors

    async def _fetch_csp_header(self, url: str) -> str | None:
        """Fetch CSP header from URL.

        Args:
            url: URL to check

        Returns:
            CSP header value or None
        """
        # In real implementation, would make HTTP request:
        # response = await http_client.get(url)
        # return response.headers.get("Content-Security-Policy")

        # Mock implementation
        return (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.example.com; "
            "style-src 'self' 'unsafe-inline'; img-src * data:; object-src 'none';"
        )

    def _parse_csp(self, csp_header: str) -> dict[str, Any]:
        """Parse CSP header into structured format.

        Args:
            csp_header: Raw CSP header string

        Returns:
            Parsed CSP dictionary
        """
        directives = {}

        # Split by semicolon
        parts = [p.strip() for p in csp_header.split(";") if p.strip()]

        for part in parts:
            # Split directive from sources
            if " " in part:
                directive, sources = part.split(" ", 1)
                directives[directive] = [s.strip() for s in sources.split()]
            else:
                directives[part] = []

        return directives

    def _analyze_csp(
        self, parsed_csp: dict[str, Any], environment: str
    ) -> dict[str, Any]:
        """Analyze parsed CSP for security issues.

        Args:
            parsed_csp: Parsed CSP dictionary
            environment: Environment context

        Returns:
            Analysis results
        """
        analysis = {
            "has_unsafe_inline": False,
            "has_unsafe_eval": False,
            "has_wildcard_sources": False,
            "has_reporting": False,
            "missing_directives": [],
            "issues": [],
        }

        for directive, sources in parsed_csp.items():
            # Check for unsafe directives
            for source in sources:
                if source == "'unsafe-inline'":
                    analysis["has_unsafe_inline"] = True
                    analysis["issues"].append(
                        {"severity": "high", "message": f"'unsafe-inline' in {directive}"}
                    )
                elif source == "'unsafe-eval'":
                    analysis["has_unsafe_eval"] = True
                    analysis["issues"].append(
                        {"severity": "high", "message": f"'unsafe-eval' in {directive}"}
                    )
                elif source == "*":
                    analysis["has_wildcard_sources"] = True
                    analysis["issues"].append(
                        {"severity": "medium", "message": f"Wildcard (*) in {directive}"}
                    )

            # Check for reporting directives
            if directive in ["report-uri", "report-to"]:
                analysis["has_reporting"] = True

        # Check for missing critical directives
        critical_directives = ["object-src", "base-uri"]
        for directive in critical_directives:
            if directive not in parsed_csp:
                analysis["missing_directives"].append(directive)

        return analysis

    def _generate_recommendations_data(
        self, parsed_csp: dict, analysis: dict, environment: str
    ) -> dict[str, Any]:
        """Generate CSP recommendation data.

        Args:
            parsed_csp: Parsed CSP
            analysis: Analysis results
            environment: Environment context

        Returns:
            Recommendation data dictionary
        """
        recommended_csp = self._generate_recommended_csp(parsed_csp, environment)

        return {
            "current_csp": parsed_csp,
            "recommended_csp": recommended_csp,
            "migration_path": self._generate_migration_path(analysis),
            "estimated_effort": self._estimate_effort(analysis),
        }

    def _generate_recommended_csp(
        self, current_csp: dict, environment: str
    ) -> dict[str, Any]:
        """Generate recommended CSP configuration.

        Args:
            current_csp: Current parsed CSP
            environment: Environment context

        Returns:
            Recommended CSP dictionary
        """
        # Start with secure defaults
        recommended = {
            "default-src": ["'self'"],
            "script-src": ["'self'", "'nonce-{random}'"],  # Nonces instead of unsafe-inline
            "style-src": ["'self'", "'nonce-{random}'"],
            "img-src": ["'self'", "data:", "https:"],
            "connect-src": ["'self'"],
            "font-src": ["'self'", "https:"],
            "object-src": ["'none'"],
            "base-uri": ["'self'"],
            "form-action": ["'self'"],
            "frame-ancestors": ["'none'"],
        }

        # Add environment-specific recommendations
        if environment == "development":
            # More permissive for development
            recommended["connect-src"].append("http://localhost:*")
            recommended["script-src"].append("'unsafe-eval'")

        # Preserve safe custom sources from current CSP
        for directive, sources in current_csp.items():
            for source in sources:
                if source not in self.UNSAFE_DIRECTIVES and source != "*":
                    if directive not in recommended:
                        recommended[directive] = []
                    if source not in recommended[directive]:
                        recommended[directive].append(source)

        # Add reporting for production
        if environment == "production":
            recommended["report-uri"] = ["/api/v1/csp-report"]

        return recommended

    def _generate_migration_path(self, analysis: dict) -> list[dict[str, Any]]:
        """Generate migration path to strict CSP.

        Args:
            analysis: CSP analysis results

        Returns:
            List of migration steps
        """
        steps = []

        # Step 1: Report-only mode
        steps.append(
            {
                "phase": "1",
                "name": "Report-Only Mode",
                "duration": "2 weeks",
                "actions": [
                    "Add Content-Security-Policy-Report-Only header",
                    "Monitor violation reports",
                    "Identify and fix violations",
                ],
            }
        )

        # Step 2: Remove unsafe-inline (if present)
        if analysis.get("has_unsafe_inline"):
            steps.append(
                {
                    "phase": "2",
                    "name": "Remove unsafe-inline",
                    "duration": "1 week",
                    "actions": [
                        "Implement nonce generation",
                        "Update templates with nonces",
                        "Test with report-only first",
                    ],
                }
            )

        # Step 3: Enforce strict CSP
        steps.append(
            {
                "phase": "3",
                "name": "Enforce Strict CSP",
                "duration": "1 week",
                "actions": [
                    "Switch to Content-Security-Policy header",
                    "Monitor for violations",
                    "Be ready to rollback if needed",
                ],
            }
        )

        return steps

    def _estimate_effort(self, analysis: dict) -> str:
        """Estimate implementation effort.

        Args:
            analysis: CSP analysis results

        Returns:
            Effort estimate string
        """
        effort_hours = 0

        if analysis.get("has_unsafe_inline"):
            effort_hours += 8  # Nonces implementation

        if analysis.get("has_unsafe_eval"):
            effort_hours += 4  # Code refactoring

        if analysis.get("has_wildcard_sources"):
            effort_hours += 2  # Source specification

        if not analysis.get("has_reporting"):
            effort_hours += 2  # Reporting setup

        if effort_hours <= 4:
            return "1-4 hours"
        elif effort_hours <= 8:
            return "4-8 hours"
        elif effort_hours <= 16:
            return "1-2 days"
        else:
            return "2-3 days"

    def _calculate_security_score(self, parsed_csp: dict, analysis: dict) -> float:
        """Calculate CSP security score.

        Args:
            parsed_csp: Parsed CSP
            analysis: Analysis results

        Returns:
            Security score between 0 and 100
        """
        score = 100.0

        # Deduct for unsafe directives
        if analysis.get("has_unsafe_inline"):
            score -= 30
        if analysis.get("has_unsafe_eval"):
            score -= 20

        # Deduct for wildcard sources
        if analysis.get("has_wildcard_sources"):
            score -= 15

        # Deduct for missing critical directives
        missing_count = len(analysis.get("missing_directives", []))
        score -= missing_count * 5

        # Deduct if no reporting
        if not analysis.get("has_reporting"):
            score -= 10

        # Add bonus for object-src none
        if parsed_csp.get("object-src") == ["'none'"]:
            score += 5

        return max(0, min(100, score))

    def _calculate_confidence(self, parsed_csp: dict) -> float:
        """Calculate confidence in the analysis.

        Args:
            parsed_csp: Parsed CSP

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with more directives
        if len(parsed_csp) > 5:
            confidence += 0.2

        # Increase confidence with standard directives
        standard_count = sum(1 for d in parsed_csp if d in self.STANDARD_DIRECTIVES)
        confidence += standard_count * 0.05

        return min(confidence, 1.0)

    def _generate_warnings(self, analysis: dict) -> list[str]:
        """Generate warnings based on analysis.

        Args:
            analysis: Analysis results

        Returns:
            List of warning messages
        """
        warnings = []

        if analysis.get("has_unsafe_inline"):
            warnings.append("CSP contains 'unsafe-inline' directive (HIGH risk)")

        if analysis.get("has_unsafe_eval"):
            warnings.append("CSP contains 'unsafe-eval' directive (HIGH risk)")

        if analysis.get("has_wildcard_sources"):
            warnings.append("CSP contains wildcard sources (MEDIUM risk)")

        if not analysis.get("has_reporting"):
            warnings.append("CSP does not have violation reporting configured")

        return warnings
