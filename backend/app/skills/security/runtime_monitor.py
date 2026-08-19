"""Security Runtime Monitor - Runtime security monitoring with Falco integration.

This skill monitors runtime security events:
- Container escape attempts
- Shell spawned in containers
- Crypto mining indicators
- Network anomalies
- File system violations
- Privilege escalation attempts
"""

import logging
from datetime import datetime, timedelta
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


class SecurityRuntimeMonitorSkill(BaseSkill):
    """Monitor runtime security events using Falco integration.

    This skill integrates with Falco to detect:
    - Shell spawned in containers (detective container breakout)
    - Crypto mining processes
    - Unauthorized network connections
    - Sensitive file access
    - Privilege escalation attempts
    - Abnormal system calls

    Requires:
    - Falco daemon running in cluster
    - Falco syslog/gRPC output enabled
    - Access to Falco events API
    """

    skill_id = "security_runtime_monitor"
    name = "Security Runtime Monitor"
    description = "Monitor runtime security events and detect suspicious activities"
    category = SkillCategory.SECURITY
    priority = SkillPriority.CRITICAL
    version = "1.0.0"

    # Falco event severity levels
    SEVERITY_LEVELS = {
        "emergency": 8,
        "alert": 7,
        "critical": 6,
        "error": 5,
        "warning": 4,
        "notice": 3,
        "informational": 2,
        "debug": 1,
    }

    # Critical Falco rule outputs
    CRITICAL_RULES = [
        "Terminal shell in container",
        "Shell spawned by unexpected process",
        "Container shell in entrypoint",
        "Spawned process crypto miner",
        "Non K8s connection detected",
        "Container write access to root filesystem",
        "Privilege escalation",
        "Sensitive file accessed",
        "Reverse shell",
        "Network connection established outside K8s",
    ]

    # Warning Falco rule outputs
    WARNING_RULES = [
        "Container entered network namespace",
        "Container entered PID namespace",
        "Container received privileged command",
        "Unknown user spawned shell",
        "Container exited unexpectedly",
        "File descriptor leaked",
        "System loads critical",
        "CPU usage critical",
        "Memory usage critical",
    ]

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the Runtime Monitor skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        self.falco_api_url = None  # Set from context
        self.events_buffer = []
        self.buffer_size = 1000

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze runtime security events.

        Args:
            project: Project/service name
            parameters: Analysis parameters
                - time_range_minutes: Time range to analyze (default: 60)
                - severity_filter: Filter by severity (default: all)
                - namespace: Filter by namespace (default: all)
                - container: Filter by container (default: all)
            context: Registry context with Falco configuration

        Returns:
            AnalysisResult with security events and findings
        """
        try:
            # Extract parameters
            time_range_minutes = parameters.get("time_range_minutes", 60)
            severity_filter = parameters.get("severity_filter", "all")
            namespace = parameters.get("namespace", "all")
            container = parameters.get("container", "all")

            logger.info(f"Analyzing runtime security for {project}, time range: {time_range_minutes}m")

            # Get Falco configuration from context
            if context:
                self.falco_api_url = context.get("falco_api_url")

            # Fetch events from Falco
            events = await self._fetch_falco_events(
                time_range_minutes=time_range_minutes,
                namespace=namespace,
                container=container,
                context=context or {},
            )

            # Filter by severity
            if severity_filter != "all":
                events = self._filter_by_severity(events, severity_filter)

            # Categorize events
            critical_events = self._categorize_events(events, "critical")
            warning_events = self._categorize_events(events, "warning")
            informational_events = self._categorize_events(events, "informational")

            # Detect patterns
            patterns = self._detect_patterns(events)

            # Calculate risk score
            risk_score = self._calculate_risk_score(events, patterns)

            # Generate findings
            findings = self._generate_findings(
                critical_events,
                warning_events,
                patterns,
                risk_score,
            )

            # Build result
            data = {
                "project": project,
                "time_range_minutes": time_range_minutes,
                "total_events": len(events),
                "critical_events": len(critical_events),
                "warning_events": len(warning_events),
                "informational_events": len(informational_events),
                "events_by_severity": self._count_by_severity(events),
                "patterns_detected": patterns,
                "risk_score": risk_score,
                "findings": findings,
                "sample_events": events[:50],  # Limit sample events
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            confidence = self._calculate_confidence(events, time_range_minutes)

            # Generate warnings
            warnings = []
            if len(critical_events) > 0:
                warnings.append(f"{len(critical_events)} critical security events detected")
            if risk_score > 7:
                warnings.append("High risk score detected - immediate action recommended")

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                warnings=warnings,
            )

        except Exception as e:
            logger.error(f"Runtime security analysis failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                errors=[f"Runtime security analysis failed: {str(e)}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate security remediation recommendations.

        Args:
            analysis_id: ID of previous analysis
            project: Project name

        Returns:
            List of security recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        recommendations = []
        data = result.data

        # Critical events - immediate action
        if data.get("critical_events", 0) > 0:
            recommendations.append(Recommendation(
                title="Investigate critical runtime security events immediately",
                description=f"Detected {data['critical_events']} critical security events in the last "
                          f"{data['time_range_minutes']} minutes. These may indicate active attacks.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="critical",
                commands=[
                    "# Review Falco events",
                    "kubectl logs -n falco deployment/falco --tail=100",
                    "# Check affected containers",
                    "kubectl get pods -A | grep <affected_pod>",
                    "# Isolate compromised containers if needed",
                    "kubectl cordon <node>",
                ],
            ))

        # Shell in containers
        patterns = data.get("patterns_detected", {})
        if patterns.get("shell_in_container", 0) > 0:
            recommendations.append(Recommendation(
                title="Investigate shell activity in containers",
                description=f"Detected {patterns['shell_in_container']} shell spawns in containers. "
                          f"This may indicate container breakout attempts or unauthorized access.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1 hour",
                risk_level="high",
                commands=[
                    "# Review container logs",
                    "kubectl logs <pod_name> --previous",
                    "# Check running processes",
                    "kubectl exec -it <pod_name> -- ps aux",
                    "# Verify container images",
                    "trivy image <container_image>",
                ],
            ))

        # Crypto mining indicators
        if patterns.get("crypto_mining", 0) > 0:
            recommendations.append(Recommendation(
                title="Terminate crypto mining processes",
                description="Detected potential crypto mining activity. This is a security incident "
                          "requiring immediate investigation and remediation.",
                priority=SkillPriority.CRITICAL,
                action_type="automated",
                estimated_effort="30 minutes",
                risk_level="critical",
                commands=[
                    "# Identify affected pods",
                    "kubectl get pods -A -l app=miner",
                    "# Terminate malicious pods",
                    "kubectl delete pod <miner_pod> --grace-period=0",
                    "# Scan nodes for malware",
                    "# Review admission controller logs",
                ],
            ))

        # Network anomalies
        if patterns.get("network_anomalies", 0) > 0:
            recommendations.append(Recommendation(
                title="Investigate network anomalies",
                description=f"Detected {patterns['network_anomalies']} suspicious network activities. "
                          f"Review network policies and traffic patterns.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="2 hours",
                risk_level="medium",
                commands=[
                    "# Review network policies",
                    "kubectl get networkpolicies -A",
                    "# Check external connections",
                    "kubectl logs <pod> | grep -i connect",
                    "# Apply network segmentation if needed",
                ],
            ))

        # Privilege escalation
        if patterns.get("privilege_escalation", 0) > 0:
            recommendations.append(Recommendation(
                title="Review privilege escalation attempts",
                description="Detected privilege escalation attempts. Review user permissions "
                          "and container security contexts.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="high",
                commands=[
                    "# Review pod security contexts",
                    "kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\\t"}{.spec.securityContext}{"\\n"}{end}'",
                    "# Check RBAC bindings",
                    "kubectl get clusterrolebindings -o yaml",
                    "# Audit privileged containers",
                    "kubectl get pods -A --field-selector spec.privileged=true",
                ],
            ))

        # General monitoring recommendations
        if data.get("risk_score", 0) > 5:
            recommendations.append(Recommendation(
                title="Enhance runtime security monitoring",
                description="Runtime security risk score is elevated. Consider enhancing monitoring "
                          "and alerting for faster incident response.",
                priority=SkillPriority.MEDIUM,
                action_type="automated",
                estimated_effort="2-4 hours",
                risk_level="low",
                commands=[
                    "# Enable additional Falco rules",
                    "# Configure Slack/webhook alerts",
                    "# Set up security dashboard",
                    "# Establish incident response playbook",
                ],
            ))

        return recommendations

    async def _fetch_falco_events(
        self,
        time_range_minutes: int,
        namespace: str,
        container: str,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Fetch events from Falco.

        Args:
            time_range_minutes: Time range in minutes
            namespace: Namespace filter
            container: Container filter
            context: Registry context

        Returns:
            List of Falco events
        """
        # Mock implementation - in production, query Falco API
        # Real implementation would:
        # 1. Query Falco gRPC API
        # 2. Or parse Falco syslog output
        # 3. Or query Falco events from Elasticsearch

        return self._generate_mock_events(time_range_minutes)

    def _generate_mock_events(self, time_range_minutes: int) -> list[dict[str, Any]]:
        """Generate mock Falco events for testing.

        Args:
            time_range_minutes: Time range for events

        Returns:
            List of mock events
        """
        import random

        events = []
        num_events = min(50, time_range_minutes // 2)  # Scale with time range

        # Event templates
        event_templates = [
            {
                "rule": "Terminal shell in container",
                "severity": "critical",
                "output_fields": {
                    "ka.state.namespace": "production",
                    "ka.resp.name": "api-server-123",
                    "ka.container.name": "api",
                    "proc.exe": "/bin/bash",
                },
            },
            {
                "rule": "Shell spawned by unexpected process",
                "severity": "warning",
                "output_fields": {
                    "ka.state.namespace": "staging",
                    "ka.resp.name": "worker-456",
                    "ka.container.name": "worker",
                    "proc.exe": "/bin/sh",
                },
            },
            {
                "rule": "Non K8s connection detected",
                "severity": "critical",
                "output_fields": {
                    "ka.state.namespace": "production",
                    "ka.resp.name": "database-789",
                    "fd.sip": "192.168.1.100",
                },
            },
            {
                "rule": "Spawned process crypto miner",
                "severity": "critical",
                "output_fields": {
                    "ka.state.namespace": "production",
                    "ka.resp.name": "unknown-pod-999",
                    "proc.exe": "/tmp/miner",
                },
            },
            {
                "rule": "Container write access to root filesystem",
                "severity": "warning",
                "output_fields": {
                    "ka.state.namespace": "development",
                    "ka.resp.name": "test-111",
                    "ka.container.name": "app",
                },
            },
            {
                "rule": "Privilege escalation",
                "severity": "critical",
                "output_fields": {
                    "ka.state.namespace": "production",
                    "ka.resp.name": "api-server-123",
                    "proc.exe": "sudo",
                },
            },
        ]

        for i in range(num_events):
            template = random.choice(event_templates)
            event = {
                "timestamp": (datetime.now(timezone.utc) -
                           timedelta(seconds=random.randint(0, time_range_minutes * 60))).isoformat(),
                "rule": template["rule"],
                "severity": template["severity"],
                "output": template["output_fields"],
                "source": "falco",
                "priority": self.SEVERITY_LEVELS.get(template["severity"], 1),
            }
            events.append(event)

        return sorted(events, key=lambda x: x["timestamp"], reverse=True)

    def _filter_by_severity(
        self,
        events: list[dict[str, Any]],
        severity: str,
    ) -> list[dict[str, Any]]:
        """Filter events by severity level.

        Args:
            events: List of events
            severity: Severity filter

        Returns:
            Filtered events
        """
        severity_threshold = self.SEVERITY_LEVELS.get(severity, 0)
        return [
            e for e in events
            if self.SEVERITY_LEVELS.get(e.get("severity", "debug"), 0) >= severity_threshold
        ]

    def _categorize_events(
        self,
        events: list[dict[str, Any]],
        category: str,
    ) -> list[dict[str, Any]]:
        """Categorize events by type.

        Args:
            events: List of events
            category: Category (critical, warning, informational)

        Returns:
            Categorized events
        """
        category_map = {
            "critical": ["critical", "emergency", "alert"],
            "warning": ["warning", "error"],
            "informational": ["informational", "notice", "debug"],
        }

        target_severities = category_map.get(category, [])
        return [
            e for e in events
            if e.get("severity", "").lower() in target_severities
        ]

    def _count_by_severity(self, events: list[dict[str, Any]]) -> dict[str, int]:
        """Count events by severity.

        Args:
            events: List of events

        Returns:
            Count by severity
        """
        counts = {}
        for event in events:
            severity = event.get("severity", "unknown")
            counts[severity] = counts.get(severity, 0) + 1
        return counts

    def _detect_patterns(self, events: list[dict[str, Any]]) -> dict[str, int]:
        """Detect patterns in events.

        Args:
            events: List of events

        Returns:
            Pattern counts
        """
        patterns = {
            "shell_in_container": 0,
            "crypto_mining": 0,
            "network_anomalies": 0,
            "privilege_escalation": 0,
            "file_system_violations": 0,
            "suspicious_process": 0,
        }

        for event in events:
            rule = event.get("rule", "").lower()

            if "shell" in rule and "container" in rule:
                patterns["shell_in_container"] += 1
            if "crypto" in rule or "miner" in rule:
                patterns["crypto_mining"] += 1
            if "network" in rule or "connection" in rule:
                patterns["network_anomalies"] += 1
            if "privilege" in rule or "escalat" in rule or "sudo" in rule:
                patterns["privilege_escalation"] += 1
            if "file" in rule or "filesystem" in rule or "write" in rule:
                patterns["file_system_violations"] += 1
            if "process" in rule and "unexpected" in rule:
                patterns["suspicious_process"] += 1

        return patterns

    def _calculate_risk_score(
        self,
        events: list[dict[str, Any]],
        patterns: dict[str, int],
    ) -> float:
        """Calculate overall risk score.

        Args:
            events: List of events
            patterns: Detected patterns

        Returns:
            Risk score (0-10)
        """
        score = 0.0

        # Base score from event count
        critical_count = sum(1 for e in events if e.get("severity") == "critical")
        score += min(critical_count * 0.5, 3.0)

        warning_count = sum(1 for e in events if e.get("severity") == "warning")
        score += min(warning_count * 0.1, 1.0)

        # Add pattern weights
        if patterns.get("crypto_mining", 0) > 0:
            score += 3.0
        if patterns.get("shell_in_container", 0) > 5:
            score += 2.0
        if patterns.get("privilege_escalation", 0) > 0:
            score += 2.5
        if patterns.get("network_anomalies", 0) > 10:
            score += 1.0

        return min(score, 10.0)

    def _generate_findings(
        self,
        critical_events: list[dict[str, Any]],
        warning_events: list[dict[str, Any]],
        patterns: dict[str, int],
        risk_score: float,
    ) -> list[dict[str, Any]]:
        """Generate security findings.

        Args:
            critical_events: Critical events
            warning_events: Warning events
            patterns: Detected patterns
            risk_score: Risk score

        Returns:
            List of findings
        """
        findings = []

        # High-risk finding
        if risk_score >= 7:
            findings.append({
                "severity": "critical",
                "title": "High runtime security risk detected",
                "description": f"Multiple critical security events detected with risk score {risk_score:.1f}/10. "
                             f"Immediate investigation recommended.",
                "evidence": {
                    "risk_score": risk_score,
                    "critical_events": len(critical_events),
                    "patterns": {k: v for k, v in patterns.items() if v > 0},
                },
            })

        # Crypto mining finding
        if patterns.get("crypto_mining", 0) > 0:
            findings.append({
                "severity": "critical",
                "title": "Potential crypto mining activity detected",
                "description": f"Detected {patterns['crypto_mining']} events related to crypto mining. "
                             f"This indicates a compromised resource.",
                "evidence": {"crypto_mining_events": patterns["crypto_mining"]},
            })

        # Shell in containers finding
        if patterns.get("shell_in_container", 0) > 0:
            findings.append({
                "severity": "high",
                "title": "Shell activity detected in containers",
                "description": f"Detected {patterns['shell_in_container']} shell spawns in containers. "
                             f"This may indicate unauthorized access or container breakout attempts.",
                "evidence": {"shell_events": patterns["shell_in_container"]},
            })

        # Privilege escalation finding
        if patterns.get("privilege_escalation", 0) > 0:
            findings.append({
                "severity": "critical",
                "title": "Privilege escalation attempts detected",
                "description": f"Detected {patterns['privilege_escalation']} privilege escalation attempts. "
                             f"This may indicate an attacker attempting to gain higher privileges.",
                "evidence": {"escalation_events": patterns["privilege_escalation"]},
            })

        # Network anomalies finding
        if patterns.get("network_anomalies", 0) > 5:
            findings.append({
                "severity": "medium",
                "title": "Unusual network activity detected",
                "description": f"Detected {patterns['network_anomalies']} suspicious network events. "
                             f"Review network policies and traffic patterns.",
                "evidence": {"network_events": patterns["network_anomalies"]},
            })

        return findings

    def _calculate_confidence(
        self,
        events: list[dict[str, Any]],
        time_range_minutes: int,
    ) -> float:
        """Calculate confidence in the analysis.

        Args:
            events: List of events
            time_range_minutes: Time range analyzed

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.7  # Base confidence

        # More events = higher confidence
        if len(events) >= 50:
            confidence += 0.1
        elif len(events) >= 20:
            confidence += 0.05

        # Longer time range = higher confidence
        if time_range_minutes >= 60:
            confidence += 0.1
        elif time_range_minutes >= 30:
            confidence += 0.05

        return min(confidence, 1.0)

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Args:
            parameters: Parameters to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate time_range_minutes
        time_range = parameters.get("time_range_minutes", 60)
        if not isinstance(time_range, (int, float)) or time_range < 1 or time_range > 1440:
            errors.append("time_range_minutes must be between 1 and 1440 (24 hours)")

        # Validate severity_filter
        severity_filter = parameters.get("severity_filter", "all")
        if severity_filter != "all" and severity_filter not in self.SEVERITY_LEVELS:
            errors.append(f"severity_filter must be one of: all, {', '.join(self.SEVERITY_LEVELS.keys())}")

        return len(errors) == 0, errors


# Create alias for compatibility
SecurityRuntimeMonitorSkill = SecurityRuntimeMonitorSkill
