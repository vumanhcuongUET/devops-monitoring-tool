"""Security Header Validator Skill.

Validates security headers across all endpoints.
Checks for missing headers, misconfigurations, and compliance scoring.
"""

import logging
from typing import Any, Optional

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)


class HeaderValidatorSkill(BaseSkill):
    """Validate security headers across all endpoints.

    This skill analyzes HTTP response headers to check:
    - Content-Security-Policy
    - Strict-Transport-Security
    - X-Frame-Options / X-Content-Type-Options
    - Permissions-Policy
    - Referrer-Policy
    - Compliance scoring (A-F grade)

    Example usage:
        skill = SecurityHeaderValidatorSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "base_url": "https://api.example.com",
                "endpoints": ["/api/v1/users", "/api/v1/data"]
            }
        )
    """

    skill_id = "security_header_validator"
    name = "Security Header Validator"
    description = (
        "Validate security headers across endpoints, check for missing headers, "
        "detect misconfigurations, and provide compliance scoring."
    )
    category = SkillCategory.SECURITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    # Standard security headers with best practices
    SECURITY_HEADERS = {
        "Content-Security-Policy": {
            "required": True,
            "weight": 25,
            "best_practice": "default-src 'self'; script-src 'nonce-{random}'",
        },
        "Strict-Transport-Security": {
            "required": True,
            "weight": 20,
            "best_practice": "max-age=31536000; includeSubDomains; preload",
        },
        "X-Content-Type-Options": {
            "required": True,
            "weight": 10,
            "best_practice": "nosniff",
        },
        "X-Frame-Options": {
            "required": False,  # Replaced by frame-ancestors in CSP
            "weight": 5,
            "best_practice": "DENY or SAMEORIGIN",
        },
        "Permissions-Policy": {
            "required": True,
            "weight": 15,
            "best_practice": "geolocation=(), microphone=(), camera=()",
        },
        "Referrer-Policy": {
            "required": True,
            "weight": 10,
            "best_practice": "strict-origin-when-cross-origin",
        },
        "X-XSS-Protection": {
            "required": False,  # Deprecated but still useful
            "weight": 5,
            "best_practice": "1; mode=block",
        },
        "Cross-Origin-Opener-Policy": {
            "required": False,
            "weight": 5,
            "best_practice": "same-origin",
        },
        "Cross-Origin-Resource-Policy": {
            "required": False,
            "weight": 5,
            "best_practice": "same-origin",
        },
    }

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the security header validator skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Run security header validation.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - base_url: Base URL to check (required)
                - endpoints: List of endpoints to check (optional)
                - headers: Custom headers to validate (optional)
            context: Additional context from registry

        Returns:
            AnalysisResult with header validation data
        """
        try:
            # Extract parameters
            base_url = parameters.get("base_url")
            endpoints = parameters.get("endpoints", ["/"])
            custom_headers = parameters.get("headers", {})

            if not base_url:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Parameter 'base_url' is required"],
                    metadata={"project": project},
                )

            # Fetch headers from endpoints
            endpoint_results = []
            for endpoint in endpoints:
                url = f"{base_url}{endpoint}"
                headers = await self._fetch_headers(url, custom_headers)
                endpoint_results.append(
                    {"endpoint": endpoint, "url": url, "headers": headers}
                )

            # Analyze headers across all endpoints
            analysis = self._analyze_headers(endpoint_results)

            # Calculate compliance score
            compliance_score = self._calculate_compliance_score(analysis)

            # Calculate grade
            grade = self._calculate_grade(compliance_score)

            # Calculate confidence
            confidence = self._calculate_confidence(endpoint_results)

            # Generate warnings
            warnings = self._generate_warnings(analysis)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "base_url": base_url,
                    "endpoints_analyzed": len(endpoint_results),
                    "endpoint_results": endpoint_results,
                    "analysis": analysis,
                    "compliance_score": compliance_score,
                    "grade": grade,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "base_url": base_url,
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
        """Generate recommendations based on header validation.

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
        grade = data.get("grade", "F")

        # Critical: Missing CSP
        missing_headers = analysis.get("missing_headers", [])
        if "Content-Security-Policy" in missing_headers:
            recommendations.append(
                Recommendation(
                    title="Add Content-Security-Policy Header",
                    description="CSP header is missing. This is critical for XSS protection.",
                    priority=SkillPriority.HIGH,
                    action_type="add",
                    estimated_effort="4-8 hours",
                    risk_level="high",
                    commands=[
                        "Implement CSP header",
                        "Start with report-only mode",
                        "Use nonces for scripts",
                    ],
                    references=["https://web.dev/strict-csp/"],
                )
            )

        # Critical: Missing HSTS
        if "Strict-Transport-Security" in missing_headers:
            recommendations.append(
                Recommendation(
                    title="Add Strict-Transport-Security Header",
                    description="HSTS header enforces HTTPS connections and prevents downgrade attacks.",
                    priority=SkillPriority.HIGH,
                    action_type="add",
                    estimated_effort="5 minutes",
                    risk_level="high",
                    commands=[
                        "Add Strict-Transport-Security: max-age=31536000; includeSubDomains",
                    ],
                )
            )

        # High: Missing other required headers
        required_missing = [
            h
            for h in missing_headers
            if self.SECURITY_HEADERS.get(h, {}).get("required", False)
        ]
        if len(required_missing) > 2:
            recommendations.append(
                Recommendation(
                    title=f"Add {len(required_missing)} Missing Security Headers",
                    description=f"Missing required headers: {', '.join(required_missing)}",
                    priority=SkillPriority.HIGH,
                    action_type="add",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        f"Add {header} header"
                        for header in required_missing
                        if header not in ["Content-Security-Policy", "Strict-Transport-Security"]
                    ],
                )
            )

        # Medium: Misconfigured headers
        misconfigured = analysis.get("misconfigured_headers", [])
        if misconfigured:
            recommendations.append(
                Recommendation(
                    title="Fix Misconfigured Security Headers",
                    description=f"{len(misconfigured)} headers are misconfigured: "
                    f"{', '.join([h['header'] for h in misconfigured[:3]])}{'...' if len(misconfigured) > 3 else ''}",
                    priority=SkillPriority.MEDIUM,
                    action_type="fix",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Review header configurations",
                        "Update with best practices",
                        "Test changes in staging first",
                    ],
                )
            )

        # Overall grade recommendation
        if grade in ["D", "F"]:
            recommendations.append(
                Recommendation(
                    title="Improve Security Headers Compliance",
                    description=f"Current security grade is {grade}. Implement missing headers "
                    f"and fix misconfigurations to improve security posture.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="1-2 days",
                    risk_level="medium",
                    commands=[
                        "Review all security header recommendations",
                        "Implement changes incrementally",
                        "Test thoroughly before production",
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

        # Validate base_url
        if not parameters.get("base_url"):
            errors.append("Parameter 'base_url' is required")
        else:
            base_url = parameters.get("base_url", "")
            if not base_url.startswith(("http://", "https://")):
                errors.append("base_url must start with http:// or https://")

        # Validate endpoints
        endpoints = parameters.get("endpoints", [])
        if endpoints and not isinstance(endpoints, list):
            errors.append("endpoints must be a list of endpoint paths")

        return len(errors) == 0, errors

    async def _fetch_headers(
        self, url: str, custom_headers: dict[str, str]
    ) -> dict[str, str]:
        """Fetch HTTP response headers from URL.

        Args:
            url: URL to fetch headers from
            custom_headers: Custom headers to include in request

        Returns:
            Dictionary of response headers
        """
        # In real implementation, make HTTP request:
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(url, headers=custom_headers)
        #     return dict(response.headers)

        # Mock implementation with common headers
        return {
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'",
            "Strict-Transport-Security": "max-age=31536000",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            # Permissions-Policy missing in mock
            # Referrer-Policy missing in mock
        }

    def _analyze_headers(
        self, endpoint_results: list[dict]
    ) -> dict[str, Any]:
        """Analyze headers across all endpoints.

        Args:
            endpoint_results: List of endpoint results with headers

        Returns:
            Analysis results dictionary
        """
        analysis = {
            "missing_headers": [],
            "misconfigured_headers": [],
            "present_headers": [],
            "endpoint_coverage": {},
        }

        # Track headers across all endpoints
        all_headers = set()
        endpoint_coverage = {}

        for result in endpoint_results:
            endpoint = result["endpoint"]
            headers = result.get("headers", {})

            endpoint_coverage[endpoint] = {
                "total_headers": len(headers),
                "security_headers": 0,
                "missing_required": [],
            }

            for header_name, config in self.SECURITY_HEADERS.items():
                if header_name in headers:
                    all_headers.add(header_name)
                    endpoint_coverage[endpoint]["security_headers"] += 1

                    # Validate configuration
                    validation = self._validate_header_config(
                        header_name, headers[header_name], config
                    )
                    if not validation["valid"]:
                        analysis["misconfigured_headers"].append(
                            {
                                "header": header_name,
                                "endpoint": endpoint,
                                "value": headers[header_name],
                                "issues": validation["issues"],
                            }
                        )
                elif config.get("required", False):
                    if header_name not in analysis["missing_headers"]:
                        analysis["missing_headers"].append(header_name)
                    endpoint_coverage[endpoint]["missing_required"].append(
                        header_name
                    )

        analysis["present_headers"] = list(all_headers)
        analysis["endpoint_coverage"] = endpoint_coverage

        return analysis

    def _validate_header_config(
        self, header_name: str, value: str, config: dict
) -> dict[str, Any]:
        """Validate individual header configuration.

        Args:
            header_name: Name of the header
            value: Header value
            config: Header configuration from SECURITY_HEADERS

        Returns:
            Validation result with valid flag and issues list
        """
        validation = {"valid": True, "issues": []}

        # Header-specific validations
        if header_name == "Strict-Transport-Security":
            # Must have max-age
            if "max-age=" not in value:
                validation["valid"] = False
                validation["issues"].append("Missing max-age directive")

            # Check for includeSubDomains
            if "includeSubDomains" not in value:
                validation["issues"].append("Consider adding includeSubDomains")

            # Check for preload (required for preload list)
            if "preload" not in value:
                validation["issues"].append("Consider adding preload for HSTS preload list")

        elif header_name == "Content-Security-Policy":
            # Check for unsafe-inline
            if "unsafe-inline" in value:
                validation["valid"] = False
                validation["issues"].append("Contains unsafe-inline directive")

            # Check for default-src
            if "default-src" not in value:
                validation["issues"].append("Missing default-src directive")

        elif header_name == "X-Frame-Options":
            # Must be DENY or SAMEORIGIN
            if value not in ["DENY", "SAMEORIGIN"]:
                validation["valid"] = False
                validation["issues"].append(
                    "Should be DENY or SAMEORIGIN (or use frame-ancestors in CSP)"
                )

        elif header_name == "X-Content-Type-Options":
            # Should be nosniff
            if value != "nosniff":
                validation["valid"] = False
                validation["issues"].append("Should be set to nosniff")

        return validation

    def _calculate_compliance_score(self, analysis: dict) -> float:
        """Calculate security header compliance score.

        Args:
            analysis: Analysis results

        Returns:
            Compliance score between 0 and 100
        """
        score = 100.0

        # Deduct for missing required headers
        missing_required = [
            h
            for h in analysis.get("missing_headers", [])
            if self.SECURITY_HEADERS.get(h, {}).get("required", False)
        ]
        for header in missing_required:
            score -= self.SECURITY_HEADERS.get(header, {}).get("weight", 10)

        # Deduct for misconfigured headers
        misconfigured_count = len(analysis.get("misconfigured_headers", []))
        score -= misconfigured_count * 5

        return max(0, min(100, score))

    def _calculate_grade(self, score: float) -> str:
        """Calculate letter grade from compliance score.

        Args:
            score: Compliance score

        Returns:
            Letter grade
        """
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _calculate_confidence(self, endpoint_results: list) -> float:
        """Calculate confidence in the analysis.

        Args:
            endpoint_results: List of endpoint results

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with more endpoints
        if len(endpoint_results) > 5:
            confidence += 0.3
        elif len(endpoint_results) > 1:
            confidence += 0.2

        # Increase confidence if we got headers
        if any(r.get("headers") for r in endpoint_results):
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_warnings(self, analysis: dict) -> list[str]:
        """Generate warnings based on analysis.

        Args:
            analysis: Analysis results

        Returns:
            List of warning messages
        """
        warnings = []

        missing = analysis.get("missing_headers", [])
        critical_missing = [
            h for h in missing if self.SECURITY_HEADERS.get(h, {}).get("required", False)
        ]
        if critical_missing:
            warnings.append(f"Missing critical headers: {', '.join(critical_missing[:3])}")

        misconfigured = analysis.get("misconfigured_headers", [])
        if misconfigured:
            warnings.append(f"{len(misconfigured)} headers are misconfigured")

        return warnings
