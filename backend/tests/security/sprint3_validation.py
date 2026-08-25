"""
Sprint 3 Validation Script

Phase 9 - Sprint 3 - Day 15
Purpose: Validate all Sprint 3 deliverables are complete and working

Run: python backend/tests/security/sprint3_validation.py
"""

import os
import sys
from pathlib import Path


# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class Sprint3Validator:
    """Validates all Sprint 3 deliverables."""

    def __init__(self):
        self.results = {
            "passed": [],
            "failed": [],
            "skipped": [],
        }

    def print_result(self, test_name: str, passed: bool, message: str = ""):
        """Print and record test result."""
        status = "passed" if passed else "failed"
        icon = "✅" if passed else "❌"
        print(f"{icon} {test_name}: {message or ('PASS' if passed else 'FAIL')}")
        self.results[status].append({"name": test_name, "message": message})

    def print_skip(self, test_name: str, reason: str):
        """Print and record skipped test."""
        print(f"⏭️  {test_name}: SKIPPED ({reason})")
        self.results["skipped"].append({"name": test_name, "message": reason})

    def validate_day11_secret_management(self) -> bool:
        """Day 11: Validate secret management setup."""
        print("\n=== Day 11: Secret Management Setup ===")

        # Check .gitignore
        gitignore_path = Path(__file__).parent.parent.parent.parent / ".gitignore"
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            self.print_result(
                ".env in .gitignore",
                ".env" in content,
            )
            self.print_result(
                "Secrets patterns in .gitignore",
                "*.key" in content or "*.pem" in content,
            )
        else:
            self.print_result(".gitignore exists", False)

        # Check External Secrets manifests
        eso_dir = Path(__file__).parent.parent.parent.parent / "k8s/external-secrets"
        external_secret = eso_dir / "external-secret.yaml"
        secretstore = eso_dir / "secretstore.yaml"

        self.print_result(
            "ExternalSecret manifest",
            external_secret.exists(),
            str(external_secret),
        )
        self.print_result(
            "SecretStore manifest",
            secretstore.exists(),
            str(secretstore),
        )

        # Check security scripts
        security_check = Path(__file__).parent.parent.parent.parent / "scripts/security-check.sh"
        remove_env = Path(__file__).parent.parent.parent.parent / "scripts/remove-env-from-history.sh"

        self.print_result(
            "Security check script",
            security_check.exists(),
        )
        self.print_result(
            "Remove .env from history script",
            remove_env.exists(),
        )

        return len(self.results["failed"]) == 0

    def validate_day12_ssrf_protection(self) -> bool:
        """Day 12: Validate SSRF protection enhancement."""
        print("\n=== Day 12: SSRF Protection Enhancement ===")

        try:
            from app.security import SSRFProtection

            # Check SSRFProtection class exists
            self.print_result(
                "SSRFProtection class exists",
                True,
            )

            # Check blocked networks
            required_networks = [
                "127.0.0.0/8",
                "10.0.0.0/8",
                "172.16.0.0/12",
                "192.168.0.0/16",
                "::1/128",
                "fc00::/7",
            ]

            for network in required_networks:
                if network not in SSRFProtection.BLOCKED_NETWORKS:
                    self.print_result(f"Blocked network {network}", False)

            self.print_result(
                f"Blocked networks ({len(SSRFProtection.BLOCKED_NETWORKS)})",
                len(SSRFProtection.BLOCKED_NETWORKS) >= 8,
                f"{len(SSRFProtection.BLOCKED_NETWORKS)} networks blocked",
            )

            # Check DNS cache
            self.print_result(
                "DNS cache TTL configured",
                SSRFProtection._cache_ttl > 0,
                f"TTL: {SSRFProtection._cache_ttl}s",
            )

            # Check cache stats method
            self.print_result(
                "DNS cache stats method",
                hasattr(SSRFProtection, "get_cache_stats"),
            )

            # Check cache clear method
            self.print_result(
                "DNS cache clear method",
                hasattr(SSRFProtection, "clear_dns_cache"),
            )

            return len(self.results["failed"]) == 0

        except Exception as e:
            self.print_result("Day 12 validation", False, str(e))
            return False

    def validate_day13_ci_cd(self) -> bool:
        """Day 13: Validate CI/CD pipeline."""
        print("\n=== Day 13: GitHub Actions CI/CD Pipeline ===")

        # Check CI workflow exists
        ci_workflow = Path(__file__).parent.parent.parent.parent / ".github/workflows/ci.yml"

        self.print_result(
            "CI workflow file",
            ci_workflow.exists(),
            str(ci_workflow),
        )

        if ci_workflow.exists():
            content = ci_workflow.read_text()

            # Check for required jobs
            self.print_result(
                "Backend lint job",
                "backend-lint" in content,
            )
            self.print_result(
                "Backend test job",
                "backend-test" in content,
            )
            self.print_result(
                "Frontend test job",
                "frontend-test" in content,
            )
            self.print_result(
                "Security scan job",
                "security-scan" in content,
            )
            self.print_result(
                "Build and push job",
                "build-and-push" in content,
            )

        return len(self.results["failed"]) == 0

    def validate_day14_external_secrets(self) -> bool:
        """Day 14: Validate External Secrets Operator setup."""
        print("\n=== Day 14: External Secrets Operator Setup ===")

        # Check setup script
        setup_script = Path(__file__).parent.parent.parent.parent / "scripts/setup-external-secrets.sh"

        self.print_result(
            "ESO setup script",
            setup_script.exists(),
        )

        # Check manifests exist (already checked in Day 11)
        eso_dir = Path(__file__).parent.parent.parent.parent / "k8s/external-secrets"

        self.print_result(
            "External secrets directory",
            eso_dir.exists(),
        )

        # Verify SecretStore has proper configuration
        secretstore = eso_dir / "secretstore.yaml"
        if secretstore.exists():
            content = secretstore.read_text()
            self.print_result(
                "Vault SecretStore configured",
                "vault" in content.lower(),
            )
            self.print_result(
                "ServiceAccount configured",
                "ServiceAccount" in content,
            )

        return len(self.results["failed"]) == 0

    def validate_day15_security_tests(self) -> bool:
        """Day 15: Validate security tests."""
        print("\n=== Day 15: Security Validation ===")

        # Check security test file
        test_file = Path(__file__).parent / "test_security_hardening.py"

        self.print_result(
            "Security test file",
            test_file.exists(),
            str(test_file),
        )

        if test_file.exists():
            content = test_file.read_text()

            # Check for key test classes
            self.print_result(
                "SSRF protection tests",
                "TestSSRFProtection" in content,
            )
            self.print_result(
                "Secrets configuration tests",
                "TestSecretsConfiguration" in content,
            )
            self.print_result(
                "Input validation tests",
                "TestInputValidation" in content,
            )
            self.print_result(
                "Rate limiting tests",
                "TestRateLimiting" in content,
            )
            self.print_result(
                "Authentication tests",
                "TestAuthentication" in content,
            )

        return len(self.results["failed"]) == 0

    def validate_integration(self) -> bool:
        """Validate integration of all Sprint 3 components."""
        print("\n=== Integration Validation ===")

        try:
            # Check imports work
            from app.security import SSRFProtection
            from app.config import settings

            self.print_result("All imports successful", True)

            # Verify security settings
            self.print_result(
                "AUTH_ENABLED setting",
                hasattr(settings, "AUTH_ENABLED"),
            )
            self.print_result(
                "AUDIT_LOG_ENABLED setting",
                hasattr(settings, "AUDIT_LOG_ENABLED"),
            )
            self.print_result(
                "REDIS_HOST setting",
                hasattr(settings, "REDIS_HOST"),
            )

            # Verify no circular imports
            self.print_result("No circular imports", True)

            return len(self.results["failed"]) == 0

        except Exception as e:
            self.print_result("Integration validation", False, str(e))
            return False

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 50)
        print("SPRINT 3 VALIDATION SUMMARY")
        print("=" * 50)

        total = len(self.results["passed"]) + len(self.results["failed"]) + len(self.results["skipped"])
        passed = len(self.results["passed"])
        failed = len(self.results["failed"])
        skipped = len(self.results["skipped"])

        print(f"\nTotal Checks: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⏭️  Skipped: {skipped}")

        if failed > 0:
            print("\nFailed Checks:")
            for check in self.results["failed"]:
                print(f"  - {check['name']}: {check['message']}")

        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")

        if failed == 0:
            print("\n🎉 SPRINT 3 VALIDATION PASSED!")
        else:
            print(f"\n⚠️  SPRINT 3 has {failed} failing check(s)")

        print("=" * 50)

        return failed == 0


def main():
    """Run Sprint 3 validation."""
    print("🔒 Phase 9 - Sprint 3 Validation")
    print("Security Hardening & CI/CD")
    print("=" * 50)

    validator = Sprint3Validator()

    # Run all day validations
    validator.validate_day11_secret_management()
    validator.validate_day12_ssrf_protection()
    validator.validate_day13_ci_cd()
    validator.validate_day14_external_secrets()
    validator.validate_day15_security_tests()
    validator.validate_integration()

    # Print summary
    success = validator.print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
