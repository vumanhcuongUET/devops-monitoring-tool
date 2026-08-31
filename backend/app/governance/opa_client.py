"""OPA Client - Integration with Open Policy Agent for policy validation.

This module provides:
- OPA client for policy evaluation
- Policy decision result models
- Integration with Action Engine for policy validation
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    """Policy decision outcomes."""

    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


class PolicySeverity(str, Enum):
    """Severity levels for policy violations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PolicyViolation:
    """A policy violation found during evaluation."""

    def __init__(
        self,
        policy_id: str,
        description: str,
        severity: PolicySeverity,
        details: dict[str, Any] | None = None,
    ):
        """Initialize a policy violation.

        Args:
            policy_id: ID of the violated policy
            description: Human-readable description
            severity: Severity of the violation
            details: Additional details
        """
        self.policy_id = policy_id
        self.description = description
        self.severity = severity
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)


class PolicyEvaluationResult:
    """Result of a policy evaluation."""

    def __init__(
        self,
        decision: PolicyDecision,
        violations: list[PolicyViolation] | None = None,
        warnings: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize the result.

        Args:
            decision: Overall policy decision
            violations: List of policy violations
            warnings: Warning messages
            metadata: Additional metadata
        """
        self.decision = decision
        self.violations = violations or []
        self.warnings = warnings or []
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "decision": self.decision.value,
            "violations": [
                {
                    "policy_id": v.policy_id,
                    "description": v.description,
                    "severity": v.severity.value,
                    "details": v.details,
                    "timestamp": v.timestamp.isoformat(),
                }
                for v in self.violations
            ],
            "warnings": self.warnings,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class OPAClient:
    """Client for Open Policy Agent policy evaluation.

    This client:
    - Evaluates actions against OPA policies
    - Returns policy decisions with violations
    - Supports dry-run mode for testing
    """

    # Cache entries are swept once the dict grows past this; without it the
    # dict grew forever (distinct action inputs never share keys).
    MAX_CACHE_KEYS = 1000

    def __init__(
        self,
        opa_url: str | None = None,
        timeout: float = 5.0,
        enable_cache: bool = True,
    ):
        """Initialize the OPA client.

        Args:
            opa_url: OPA server URL (default from settings)
            timeout: Request timeout in seconds
            enable_cache: Whether to cache policy decisions
        """
        self.opa_url = opa_url or getattr(settings, "OPA_URL", "http://localhost:8181")
        self.timeout = timeout
        self.enable_cache = enable_cache
        self._cache: dict[str, tuple[datetime, PolicyEvaluationResult]] = {}
        self._cache_ttl = 60  # Cache for 60 seconds

    async def evaluate_action(
        self,
        action: dict[str, Any],
        project: str,
        environment: str = "production",
        user: str | None = None,
    ) -> PolicyEvaluationResult:
        """Evaluate an action against OPA policies.

        Args:
            action: Action definition with command, parameters, etc.
            project: Project name
            environment: Environment name
            user: Optional user requesting the action

        Returns:
            PolicyEvaluationResult with decision and violations
        """
        # Check cache (entries carry a timestamp; the TTL is actually honored —
        # Phase 15: previously decisions, DENYs included, cached forever)
        cache_key = self._generate_cache_key(action, project, environment, user)
        if self.enable_cache and cache_key in self._cache:
            cached_at, cached = self._cache[cache_key]
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < self._cache_ttl:
                logger.debug(f"OPA cache hit for {cache_key}")
                return cached
            del self._cache[cache_key]

        # Build input for OPA
        input_data = {
            "action": action,
            "project": project,
            "environment": environment,
            "user": user,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.opa_url}/v1/data/devops/actions/allow",
                    json={"input": input_data},
                )

                if response.status_code == 200:
                    result = response.json()

                    # Parse response. A missing "result" (OPA returns {} for an
                    # undefined policy) is NOT an allow — Phase 15: treat it as
                    # UNKNOWN so fail-closed callers (OPA_ENFORCE) block.
                    raw_allowed = result.get("result")
                    if raw_allowed is None:
                        return PolicyEvaluationResult(
                            decision=PolicyDecision.UNKNOWN,
                            warnings=["OPA returned no result for the policy path"],
                        )
                    allowed = bool(raw_allowed)
                    decision = PolicyDecision.ALLOW if allowed else PolicyDecision.DENY

                    # Extract violations if denied
                    violations = []
                    if not allowed:
                        # Get detailed reasons from OPA
                        violations_response = await client.post(
                            f"{self.opa_url}/v1/data/devops/actions/violations",
                            json={"input": input_data},
                        )
                        if violations_response.status_code == 200:
                            violations_data = violations_response.json().get("result", [])
                            for v in violations_data:
                                violations.append(
                                    PolicyViolation(
                                        policy_id=v.get("policy_id", "unknown"),
                                        description=v.get("description", "Policy violation"),
                                        severity=PolicySeverity(
                                            v.get("severity", "medium")
                                        ),
                                        details=v,
                                    )
                                )

                    evaluation_result = PolicyEvaluationResult(
                        decision=decision,
                        violations=violations,
                        metadata={"opa_version": "v1"},
                    )

                    # Cache the result, sweeping expired entries when the
                    # dict grows unbounded (one key per distinct input).
                    if self.enable_cache:
                        now = datetime.now(timezone.utc)
                        if len(self._cache) >= self.MAX_CACHE_KEYS:
                            self._cache = {
                                k: v for k, v in self._cache.items()
                                if (now - v[0]).total_seconds() < self._cache_ttl
                            }
                        self._cache[cache_key] = (now, evaluation_result)

                    return evaluation_result
                else:
                    logger.error(f"OPA evaluation failed: {response.status_code}")
                    # Fail closed - deny if OPA is unavailable
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.DENY,
                        violations=[
                            PolicyViolation(
                                policy_id="opa_unavailable",
                                description="Policy evaluation service unavailable",
                                severity=PolicySeverity.HIGH,
                            )
                        ],
                    )

        except httpx.TimeoutError:
            logger.error("OPA request timed out")
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                violations=[
                    PolicyViolation(
                        policy_id="opa_timeout",
                        description="Policy evaluation timed out",
                        severity=PolicySeverity.HIGH,
                    )
                ],
            )
        except Exception as e:
            # Log hygiene: the raw exception (internal URL, query error) stays
            # in server logs; the result the caller may surface keeps a
            # generic message.
            logger.error("OPA evaluation error: %s", e, exc_info=True)
            return PolicyEvaluationResult(
                decision=PolicyDecision.UNKNOWN,
                warnings=["Policy evaluation failed — see server logs for details"],
            )

    async def evaluate_batch(
        self,
        actions: list[dict[str, Any]],
        project: str,
        environment: str = "production",
        user: str | None = None,
    ) -> list[PolicyEvaluationResult]:
        """Evaluate multiple actions in batch.

        Args:
            actions: List of action definitions
            project: Project name
            environment: Environment name
            user: Optional user

        Returns:
            List of PolicyEvaluationResult
        """
        results = []
        for action in actions:
            result = await self.evaluate_action(action, project, environment, user)
            results.append(result)

        return results

    async def check_compliance(
        self,
        project: str,
        environment: str = "production",
    ) -> dict[str, Any]:
        """Check overall compliance status.

        Args:
            project: Project name
            environment: Environment name

        Returns:
            Compliance status with scores and violations
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.opa_url}/v1/data/devops/compliance/status",
                    json={
                        "input": {
                            "project": project,
                            "environment": environment,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )

                if response.status_code == 200:
                    return response.json().get("result", {})
                else:
                    return {
                        "status": "unknown",
                        "error": f"OPA returned {response.status_code}",
                    }

        except Exception as e:
            return {
                "status": "unknown",
                "error": str(e),
            }

    def _generate_cache_key(
        self,
        action: dict[str, Any],
        project: str,
        environment: str,
        user: str | None,
    ) -> str:
        """Generate cache key for policy evaluation.

        Args:
            action: Action definition
            project: Project name
            environment: Environment name
            user: Optional user

        Returns:
            Cache key string
        """
        import hashlib
        import json

        key_data = {
            "action": action,
            "project": project,
            "environment": environment,
            "user": user,
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def clear_cache(self) -> None:
        """Clear the policy decision cache."""
        self._cache.clear()
        logger.info("OPA policy cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "enabled": self.enable_cache,
            "size": len(self._cache),
            "ttl_seconds": self._cache_ttl,
        }


# Singleton instance
_opa_client: OPAClient | None = None


def get_opa_client(
    opa_url: str | None = None,
    timeout: float = 5.0,
) -> OPAClient:
    """Get or create the singleton OPA client instance.

    Args:
        opa_url: Optional OPA server URL
        timeout: Request timeout

    Returns:
        OPAClient instance
    """
    global _opa_client
    if _opa_client is None:
        _opa_client = OPAClient(opa_url=opa_url, timeout=timeout)
    return _opa_client
