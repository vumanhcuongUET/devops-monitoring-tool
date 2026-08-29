"""Security Secret Exposure Scanner Skill.

Advanced secret detection beyond Phase 3.
Scans git history, container images, K8s YAML, and CI/CD variables.
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


class SecretExposureScannerSkill(BaseSkill):
    """Advanced secret detection for exposed secrets.

    This skill scans for:
    - Git history for leaked secrets
    - Container image layers
    - Kubernetes YAML deep scan
    - CI/CD variable scan

    Enhances Phase 3 secret_scanner with additional capabilities.

    Example usage:
        skill = SecretExposureScannerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "target": "repo",
                "scan_depth": 6,
                "scan_history": True
            }
        )
    """

    skill_id = "security_secret_exposure_scanner"
    name = "Security Secret Exposure Scanner"
    description = (
        "Advanced secret scanning including git history, container images, "
        "K8s manifests, and CI/CD variable detection."
    )
    category = SkillCategory.SECURITY
    priority = SkillPriority.HIGH
    version = "2.0.0"  # Enhanced from Phase 3

    # Secret patterns to detect
    SECRET_PATTERNS = {
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "aws_secret_key": r"[0-9a-zA-Z/+]{40}",
        "github_token": r"ghp_[a-zA-Z0-9]{36}",
        "github_oauth": r"(gho|ghu|ghs)_[a-zA-Z0-9]{36}",
        "slack_token": r"xox[baprs]-[0-9]{12}-[0-9]{12}-[0-9]{12}-[a-z0-9]{32}",
        "stripe_key": r"sk_live_[0-9a-zA-Z]{24,}",
        "dockerhub_auth": r"\$dockerhub(?:-pss)?(?:_[a-z0-9]{6}){4}",
        "api_key": r"(?i)(api[_-]?key|apikey)[\"']?\s*[:=]\s*[\"']?[0-9a-zA-Z]{20,}",
        "password": r"(?i)password[\"']?\s*[:=]\s*[\"']?[^\s]{8,}",
        "private_key": r"-----BEGIN[A-Z ]+PRIVATE KEY-----",
        "bearer_token": r"(?i)bearer[\"']?\s*[\"']?[a-zA-Z0-9\-._~+/]+=*",
    }

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the secret exposure scanner skill.

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
        """Run secret exposure scan.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - target: Target type (repo, image, cluster, all)
                - scan_depth: History scan depth in months (default: 6)
                - scan_history: Scan git history (default: True)
                - image_name: Container image name (for image scan)
            context: Additional context from registry

        Returns:
            AnalysisResult with secret scan data
        """
        try:
            # Extract parameters
            target = parameters.get("target", "repo")
            scan_depth = parameters.get("scan_depth", 6)
            scan_history = parameters.get("scan_history", True)
            image_name = parameters.get("image_name")

            # Perform scans based on target type
            secrets_found = []
            scan_summary = {"scans_performed": [], "total_secrets": 0}

            if target in ["repo", "all"]:
                # Scan repository
                repo_scan = await self._scan_repository(project, scan_depth, scan_history)
                secrets_found.extend(repo_scan.get("secrets", []))
                scan_summary["scans_performed"].append("repository_scan")

            if target in ["image", "all"] and image_name:
                # Scan container image
                image_scan = await self._scan_image(image_name)
                secrets_found.extend(image_scan.get("secrets", []))
                scan_summary["scans_performed"].append("image_scan")

            if target in ["cluster", "all"]:
                # Scan Kubernetes resources
                k8s_scan = await self._scan_kubernetes_resources(project)
                secrets_found.extend(k8s_scan.get("secrets", []))
                scan_summary["scans_performed"].append("kubernetes_scan")

            if target in ["cicd", "all"]:
                # Scan CI/CD variables
                cicd_scan = await self._scan_cicd_variables(project)
                secrets_found.extend(cicd_scan.get("secrets", []))
                scan_summary["scans_performed"].append("cicd_scan")

            # Remove duplicates
            unique_secrets = self._deduplicate_secrets(secrets_found)

            # Categorize by severity
            categorized_secrets = self._categorize_secrets(unique_secrets)

            # Calculate risk score
            risk_score = self._calculate_risk_score(categorized_secrets)

            # Calculate confidence
            confidence = self._calculate_confidence(unique_secrets, scan_summary)

            # Generate warnings
            warnings = self._generate_warnings(categorized_secrets)

            scan_summary["total_secrets"] = len(unique_secrets)
            scan_summary["critical_secrets"] = len(categorized_secrets.get("critical", []))
            scan_summary["high_secrets"] = len(categorized_secrets.get("high", []))

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "target": target,
                    "scan_depth": scan_depth,
                    "secrets_found": unique_secrets,
                    "categorized_secrets": categorized_secrets,
                    "risk_score": risk_score,
                    "scan_summary": scan_summary,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "target": target,
                    "scan_depth": scan_depth,
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
        """Generate recommendations based on secret scan.

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
        categorized = data.get("categorized_secrets", {})
        risk_score = data.get("risk_score", 0)

        # Critical: Active secrets detected
        critical_secrets = categorized.get("critical", [])
        if critical_secrets:
            active_count = sum(1 for s in critical_secrets if s.get("status") == "active")
            if active_count > 0:
                recommendations.append(
                    Recommendation(
                        title="Rotate Active Secrets Immediately",
                        description=f"{active_count} active secrets detected in code/artifacts. "
                        f"These must be rotated immediately as they are currently valid.",
                        priority=SkillPriority.CRITICAL,
                        action_type="urgent",
                        estimated_effort="2-4 hours",
                        risk_level="critical",
                        commands=[
                            "Rotate all exposed secrets",
                            "Remove secrets from git history (git filter-repo or BFG)",
                            "Update credentials in affected systems",
                            "Scan for any unauthorized access",
                        ],
                        references=[
                            "https://github.com/BadAui/bfg-repo-cleaner",
                            "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token",
                        ],
                    )
                )

        # High: Expired secrets in history
        high_secrets = categorized.get("high", [])
        if high_secrets:
            expired_count = sum(1 for s in high_secrets if s.get("status") == "expired")
            if expired_count > 0:
                recommendations.append(
                    Recommendation(
                        title="Clean Up Expired Secrets from History",
                        description=f"{expired_count} expired secrets found in git history. "
                        f"While rotated, they should be removed for hygiene.",
                        priority=SkillPriority.MEDIUM,
                        action_type="clean",
                        estimated_effort="1-2 hours",
                        risk_level="low",
                        commands=[
                            "Remove from git history using BFG Repo-Cleaner",
                            "Force push with cleaned history",
                            "Update all clone references",
                        ],
                    )
                )

        # Medium: Kubernetes secrets audit
        k8s_secrets = [s for s in data.get("secrets_found", []) if s.get("source") == "kubernetes"]
        if k8s_secrets:
            recommendations.append(
                Recommendation(
                    title="Audit Kubernetes Secrets Management",
                    description=f"{len(k8s_secrets)} secrets found in Kubernetes manifests. "
                    f"Consider using External Secrets Operator for rotation.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="4-8 hours",
                    risk_level="medium",
                    commands=[
                        "Implement External Secrets Operator",
                        "Set up automatic secret rotation",
                        "Use sealed secrets for sensitive data",
                        "Audit RBAC for secret access",
                    ],
                    references=["https://external-secrets.io/"],
                )
            )

        # Medium: CI/CD variables audit
        cicd_secrets = [s for s in data.get("secrets_found", []) if s.get("source") == "cicd"]
        if cicd_secrets:
            recommendations.append(
                Recommendation(
                    title="Secure CI/CD Variables",
                    description=f"{len(cicd_secrets)} secrets found in CI/CD configuration. "
                    f"Move to proper secret management.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="2-4 hours",
                    risk_level="medium",
                    commands=[
                        "Move secrets to vault/secret manager",
                        "Use CI/CD secret management features",
                        "Add secret scanning to PR checks",
                        "Implement secret rotation policies",
                    ],
                )
            )

        # Overall risk score recommendation
        if risk_score > 70:
            recommendations.append(
                Recommendation(
                    title="Address High Secret Exposure Risk",
                    description=f"Secret exposure risk score is {risk_score}/100. "
                    f"Implement secret scanning in CI/CD pipeline and fix all findings.",
                    priority=SkillPriority.HIGH,
                    action_type="fix",
                    estimated_effort="1-2 days",
                    risk_level="high",
                    commands=[
                        "Add pre-commit secret scanning",
                        "Add secret scanning to CI pipeline",
                        "Implement branch protection rules",
                        "Train team on secret management",
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

        # Validate target
        target = parameters.get("target", "repo")
        valid_targets = ["repo", "image", "cluster", "cicd", "all"]
        if target not in valid_targets:
            errors.append(f"target must be one of: {', '.join(valid_targets)}")

        # Validate scan_depth
        scan_depth = parameters.get("scan_depth", 6)
        if not isinstance(scan_depth, int) or scan_depth < 1:
            errors.append("scan_depth must be a positive integer")

        # Validate image_name if target is image
        if target == "image" and not parameters.get("image_name"):
            errors.append("image_name is required when target is 'image'")

        return len(errors) == 0, errors

    async def _scan_repository(
        self, project: str, scan_depth: int, scan_history: bool
    ) -> dict[str, Any]:
        """Scan repository for secrets.

        Args:
            project: Project name
            scan_depth: History scan depth in months
            scan_history: Whether to scan git history

        Returns:
            Repository scan results
        """
        secrets = []

        if scan_history:
            # Scan git history
            # In real implementation, use gitleaks or trufflehog:
            # result = await gitleaks.scan(repo_path, depth=scan_depth)

            # Mock implementation
            secrets.append(
                {
                    "type": "aws_access_key",
                    "value": "AKIAIOSFODNN7EXAMPLE",
                    "file": "config/database.py",
                    "line": 15,
                    "commit": "a1b2c3d",
                    "date": "2026-06-15",
                    "source": "git_history",
                    "status": "active",  # Still valid
                }
            )
            secrets.append(
                {
                    "type": "github_token",
                    "value": "ghp_1234567890abcdefghijklmnopqrstuv",
                    "file": ".env.backup",
                    "line": 3,
                    "commit": "e5f6g7h",
                    "date": "2026-05-20",
                    "source": "git_history",
                    "status": "expired",  # Already rotated
                }
            )

        return {"secrets": secrets}

    async def _scan_image(self, image_name: str) -> dict[str, Any]:
        """Scan container image for secrets.

        Args:
            image_name: Container image name

        Returns:
            Image scan results
        """
        secrets = []

        # In real implementation, use trufflehog or similar:
        # layers = docker_client.get_image_layers(image_name)
        # for layer in layers:
        #     secrets.extend(scan_layer(layer))

        # Mock implementation
        secrets.append(
            {
                "type": "database_password",
                "value": "SuperSecret123!",
                "layer": "app-layer",
                "file": "/app/config.json",
                "source": "container_image",
                "status": "active",
            }
        )

        return {"secrets": secrets, "image": image_name}

    async def _scan_kubernetes_resources(self, project: str) -> dict[str, Any]:
        """Scan Kubernetes YAML for secrets.

        Args:
            project: Project name

        Returns:
            Kubernetes scan results
        """
        secrets = []

        # In real implementation, scan k8s/ directory:
        # for yaml_file in glob("k8s/**/*.yaml"):
        #     secrets.extend(scan_k8s_yaml(yaml_file))

        # Mock implementation
        secrets.append(
            {
                "type": "api_key",
                "value": "secret-api-key-12345",
                "file": "k8s/secrets.yaml",
                "line": 10,
                "source": "kubernetes",
                "status": "active",
                "note": "K8s secret - acceptable if encrypted at rest",
            }
        )

        return {"secrets": secrets}

    async def _scan_cicd_variables(self, project: str) -> dict[str, Any]:
        """Scan CI/CD configuration for secrets.

        Args:
            project: Project name

        Returns:
            CI/CD scan results
        """
        secrets = []

        # In real implementation, scan .github/workflows/, .gitlab-ci.yml:
        # for workflow_file in glob(".github/**/*.{yml,yaml}"):
        #     secrets.extend(scan_workflow(workflow_file))

        # Mock implementation
        secrets.append(
            {
                "type": "slack_webhook",
                "value": "https://hooks.slack.com/services/T00/B00/XXXX",
                "file": ".github/workflows/notify.yml",
                "line": 25,
                "source": "cicd",
                "status": "active",
            }
        )

        return {"secrets": secrets}

    def _deduplicate_secrets(self, secrets: list) -> list:
        """Remove duplicate secrets from list.

        Args:
            secrets: List of secrets

        Returns:
            Deduplicated list
        """
        seen = set()
        unique = []

        for secret in secrets:
            # Create unique key based on type and value
            key = (secret.get("type"), secret.get("value", "")[:20])
            if key not in seen:
                seen.add(key)
                unique.append(secret)

        return unique

    def _categorize_secrets(self, secrets: list) -> dict[str, list]:
        """Categorize secrets by severity.

        Args:
            secrets: List of secrets

        Returns:
            Dictionary with severity categories
        """
        categorized = {"critical": [], "high": [], "medium": [], "low": []}

        for secret in secrets:
            severity = self._assess_severity(secret)
            categorized[severity].append(secret)

        return categorized

    def _assess_severity(self, secret: dict) -> str:
        """Assess severity of a secret exposure.

        Args:
            secret: Secret dictionary

        Returns:
            Severity level
        """
        secret_type = secret.get("type", "")
        status = secret.get("status", "unknown")
        source = secret.get("source", "")

        # Critical: Active secrets with high-value types
        if status == "active" and secret_type in ["aws_access_key", "github_token", "stripe_key"]:
            return "critical"

        # Critical: Private keys
        if secret_type == "private_key":
            return "critical"

        # High: Active API keys or passwords
        if status == "active" and secret_type in ["api_key", "password", "slack_token"]:
            return "high"

        # High: Expired but recent secrets
        if status == "expired" and secret_type in ["aws_access_key", "github_token"]:
            return "high"

        # Medium: Expired other secrets
        if status == "expired":
            return "medium"

        # Medium: K8s secrets (should be in secret management)
        if source == "kubernetes":
            return "medium"

        # Low: Low-severity tokens
        return "low"

    def _calculate_risk_score(self, categorized: dict) -> float:
        """Calculate overall risk score.

        Args:
            categorized: Categorized secrets dictionary

        Returns:
            Risk score between 0 and 100
        """
        score = 0.0

        # Weighted score based on severity
        score += len(categorized.get("critical", [])) * 25
        score += len(categorized.get("high", [])) * 15
        score += len(categorized.get("medium", [])) * 8
        score += len(categorized.get("low", [])) * 3

        return min(100.0, score)

    def _calculate_confidence(self, secrets: list, scan_summary: dict) -> float:
        """Calculate confidence in the scan results.

        Args:
            secrets: List of secrets found
            scan_summary: Scan summary

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with more scan types
        scans_performed = len(scan_summary.get("scans_performed", []))
        if scans_performed > 2:
            confidence += 0.3
        elif scans_performed > 1:
            confidence += 0.2

        # Increase confidence with secrets found
        if len(secrets) > 0:
            confidence += 0.2

        return min(confidence, 1.0)

    def _generate_warnings(self, categorized: dict) -> list[str]:
        """Generate warnings based on scan results.

        Args:
            categorized: Categorized secrets

        Returns:
            List of warning messages
        """
        warnings = []

        critical_count = len(categorized.get("critical", []))
        if critical_count > 0:
            active_critical = sum(
                1 for s in categorized["critical"] if s.get("status") == "active"
            )
            warnings.append(f"{active_critical} active critical secrets detected")

        total_secrets = sum(len(v) for v in categorized.values())
        if total_secrets > 10:
            warnings.append(f"High volume of secrets detected: {total_secrets} total")

        return warnings
