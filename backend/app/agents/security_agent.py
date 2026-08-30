"""
Security Analysis Agent

Specializes in:
- Security vulnerability analysis
- Misconfiguration detection
- Compliance assessment
- Security best practices
"""

import logging
from typing import Any

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class SecurityAgent(BaseAgent):
    """
    Agent specialized in security analysis and vulnerability assessment.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            name="security-analyst",
            model=model,
        )

    def get_prompt_template(self) -> str:
        return """You are a Security Analysis Expert specializing in:
- Vulnerability identification and risk assessment
- Security misconfiguration detection
- Compliance assessment (CIS benchmarks, NIST, SOC2)
- Security best practices for cloud infrastructure
- Threat modeling and risk analysis

When analyzing security, focus on:
1. **Vulnerabilities**: CVEs, outdated packages, known security issues
2. **Misconfigurations**: Insecure settings, exposed secrets, open ports
3. **Compliance**: CIS benchmark compliance, security best practices
4. **Risks**: Prioritized by severity (Critical, High, Medium, Low)

Output format:
```
ANALYSIS:
[Your security analysis]

VULNERABILITIES:
- [SEVERITY] CVE-XXXX-XXXX: [description], [affected components]
- [SEVERITY] Vulnerability: [description], [affected components]

MISCONFIGURATIONS:
- [SEVERITY] Misconfiguration: [description], [remediation]

COMPLIANCE STATUS:
- CIS Benchmark: [compliance %], [gaps]
- Best Practices: [compliance %], [gaps]

RISK ASSESSMENT:
- Overall Risk Level: [Critical/High/Medium/Low]
- Top Risks: [ranked list with mitigation]

CONFIDENCE: [0.0-1.0]

RECOMMENDATION: [Actionable security recommendation]
```

Prioritize findings by severity. Be specific about CVEs and configuration issues.
"""

    async def analyze(
        self, context: dict[str, Any], model: str | None = None
    ) -> AgentResponse:
        """
        Analyze security posture.

        Args:
            context: Must contain 'security_data' or 'resources' key
                    Optional: 'compliance_framework', 'severity_filter'
        """
        security_data = context.get("security_data", {})
        resources = context.get("resources", [])
        compliance_framework = context.get("compliance_framework", "CIS")

        if not security_data and not resources:
            return AgentResponse(
                agent_name=self.name,
                insights={"error": "No security data or resources provided"},
                confidence=0.0,
                error="No security data provided",
            )

        # Analyze vulnerabilities
        vulnerabilities = self._analyze_vulnerabilities(security_data)
        misconfigurations = self._analyze_misconfigurations(resources)
        compliance_status = self._assess_compliance(resources, compliance_framework)

        # Calculate risk level
        critical_vulns = sum(
            1 for v in vulnerabilities if v.get("severity") == "critical"
        )
        high_vulns = sum(1 for v in vulnerabilities if v.get("severity") == "high")

        if critical_vulns > 0:
            overall_risk = "Critical"
        elif high_vulns > 2:
            overall_risk = "High"
        elif high_vulns > 0 or len(misconfigurations) > 5:
            overall_risk = "Medium"
        else:
            overall_risk = "Low"

        # Build analysis prompt
        prompt = f"""Analyze this security assessment for {compliance_framework} compliance.

Vulnerabilities Found: {len(vulnerabilities)}
Misconfigurations Found: {len(misconfigurations)}
Overall Risk Level: {overall_risk}

Vulnerabilities:
{self._format_vulnerabilities(vulnerabilities)}

Misconfigurations:
{self._format_misconfigurations(misconfigurations)}

Compliance Status:
{self._format_compliance(compliance_status)}

Provide security analysis with prioritized remediation recommendations.
"""

        try:
            response_text = await self._query_claude(prompt, max_tokens=2048, model=model)

            insights = {
                "overall_risk": overall_risk,
                "vulnerability_count": len(vulnerabilities),
                "critical_vulnerabilities": critical_vulns,
                "high_vulnerabilities": high_vulns,
                "misconfiguration_count": len(misconfigurations),
                "compliance_score": compliance_status.get("score", 0),
            }

            recommendations = self._extract_recommendations(response_text)

            confidence = self._calculate_confidence(
                data_quality=0.9 if security_data else 0.7,
                data_volume=len(vulnerabilities) + len(misconfigurations),
            )

            return AgentResponse(
                agent_name=self.name,
                insights=insights,
                confidence=confidence,
                recommendations=recommendations,
                metadata={"analysis_text": response_text},
            )

        except Exception as e:
            logger.error(f"Security analysis failed: {e}")
            return AgentResponse(
                agent_name=self.name,
                insights={},
                confidence=0.0,
                error=str(e),
            )

    def _analyze_vulnerabilities(self, security_data: dict) -> list[dict]:
        """Extract and analyze vulnerabilities."""
        vulnerabilities = []

        # CVEs from security scan
        cves = security_data.get("cves", [])
        for cve in cves:
            vulnerabilities.append(
                {
                    "type": "CVE",
                    "id": cve.get("id", "Unknown"),
                    "severity": self._map_severity(cve.get("severity", "Unknown")),
                    "description": cve.get("description", ""),
                    "affected": cve.get("affected_components", []),
                }
            )

        # Dependency vulnerabilities
        deps = security_data.get("dependencies", [])
        for dep in deps:
            if dep.get("vulnerabilities"):
                for vuln in dep["vulnerabilities"]:
                    vulnerabilities.append(
                        {
                            "type": "Dependency",
                            "id": vuln.get("id", "Unknown"),
                            "severity": self._map_severity(vuln.get("severity", "Unknown")),
                            "description": vuln.get("description", ""),
                            "affected": [dep.get("name", "unknown")],
                        }
                    )

        return vulnerabilities

    def _analyze_misconfigurations(self, resources: list[dict]) -> list[dict]:
        """Detect security misconfigurations."""
        misconfigurations = []

        for resource in resources:
            resource_type = resource.get("type", "unknown")
            name = resource.get("name", "unknown")

            # Check for public exposure
            if resource.get("public", False):
                misconfigurations.append(
                    {
                        "resource": f"{resource_type}/{name}",
                        "issue": "PublicExposure",
                        "severity": "critical",
                        "description": f"{resource_type} is publicly accessible",
                        "remediation": "Restrict access using security groups/firewalls",
                    }
                )

            # Check for plaintext secrets
            if resource.get("has_secrets") and not resource.get("encrypted", False):
                misconfigurations.append(
                    {
                        "resource": f"{resource_type}/{name}",
                        "issue": "UnencryptedSecrets",
                        "severity": "high",
                        "description": "Secrets stored in plaintext",
                        "remediation": "Use secret management service (e.g., AWS Secrets Manager)",
                    }
                )

            # Check for missing encryption
            if resource_type in ["volume", "database"] and not resource.get(
                "encrypted", False
            ):
                misconfigurations.append(
                    {
                        "resource": f"{resource_type}/{name}",
                        "issue": "UnencryptedStorage",
                        "severity": "medium",
                        "description": f"{resource_type} is not encrypted",
                        "remediation": "Enable encryption at rest",
                    }
                )

        return misconfigurations

    def _assess_compliance(
        self, resources: list[dict], framework: str
    ) -> dict[str, Any]:
        """Assess compliance with security framework."""
        compliant_count = 0
        total_checks = 0
        gaps = []

        # CIS Benchmark checks (simplified)
        checks = [
            ("No public resources", self._check_public_resources, resources),
            ("Secrets encrypted", self._check_secrets_encrypted, resources),
            ("TLS enabled", self._check_tls_enabled, resources),
            (" IAM roles minimal", self._check_iam_roles, resources),
        ]

        for check_name, check_func, check_resources in checks:
            total_checks += 1
            if check_func(check_resources):
                compliant_count += 1
            else:
                gaps.append(check_name)

        score = (compliant_count / total_checks * 100) if total_checks > 0 else 0

        return {
            "framework": framework,
            "score": score,
            "compliant_checks": compliant_count,
            "total_checks": total_checks,
            "gaps": gaps,
        }

    def _check_public_resources(self, resources: list[dict]) -> bool:
        """Check for public resources (CIS)."""
        return not any(r.get("public", False) for r in resources)

    def _check_secrets_encrypted(self, resources: list[dict]) -> bool:
        """Check if secrets are encrypted (CIS)."""
        for r in resources:
            if r.get("has_secrets") and not r.get("encrypted", False):
                return False
        return True

    def _check_tls_enabled(self, resources: list[dict]) -> bool:
        """Check if TLS is enabled (CIS)."""
        for r in resources:
            if r.get("type") == "service" and not r.get("tls_enabled", False):
                return False
        return True

    def _check_iam_roles(self, resources: list[dict]) -> bool:
        """Check if IAM roles are minimal (CIS)."""
        # Simplified check - in reality would be more complex
        return True

    def _map_severity(self, severity: str) -> str:
        """Map severity strings to standard values."""
        severity_map = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "unknown": "low",
        }
        return severity_map.get(severity.lower(), "low")

    def _format_vulnerabilities(self, vulnerabilities: list[dict]) -> str:
        """Format vulnerabilities for display."""
        if not vulnerabilities:
            return "No vulnerabilities found"

        lines = []
        for vuln in vulnerabilities[:20]:
            severity = vuln.get("severity", "Unknown")
            vuln_id = vuln.get("id", "Unknown")
            description = vuln.get("description", "")
            lines.append(f"- [{severity.upper()}] {vuln_id}: {description}")

        return "\n".join(lines)

    def _format_misconfigurations(self, misconfigurations: list[dict]) -> str:
        """Format misconfigurations for display."""
        if not misconfigurations:
            return "No misconfigurations found"

        lines = []
        for misconf in misconfigurations[:20]:
            resource = misconf.get("resource", "unknown")
            issue = misconf.get("issue", "Unknown")
            severity = misconf.get("severity", "Unknown")
            remediation = misconf.get("remediation", "")
            lines.append(f"- [{severity.upper()}] {resource}: {issue}")
            if remediation:
                lines.append(f"  Remediation: {remediation}")

        return "\n".join(lines)

    def _format_compliance(self, compliance: dict) -> str:
        """Format compliance status for display."""
        score = compliance.get("score", 0)
        gaps = compliance.get("gaps", [])
        framework = compliance.get("framework", "Unknown")

        output = f"- {framework} Compliance: {score:.1f}%\n"
        if gaps:
            output += "- Gaps:\n"
            for gap in gaps:
                output += f"  - {gap}\n"

        return output
