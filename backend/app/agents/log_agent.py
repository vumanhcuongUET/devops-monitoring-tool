"""
Log Analysis Agent

Specializes in:
- Error pattern recognition
- Log anomaly detection
- Root cause identification from logs
- Common application issue patterns
"""

import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any

from app.services.llm_input import truncate_text
from app.security import wrap_untrusted_data

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class LogAnalysisAgent(BaseAgent):
    """
    Agent specialized in analyzing log data to identify patterns,
    anomalies, and root causes of issues.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            name="log-analyst",
            model=model,
        )

    def get_prompt_template(self) -> str:
        return """You are a Log Analysis Expert specializing in:
- Error pattern recognition and categorization
- Log anomaly detection and unusual behavior identification
- Root cause analysis from log sequences
- Common application issue patterns (memory leaks, race conditions, etc.)

When analyzing logs, focus on:
1. **Error Patterns**: Identify recurring error types, stack traces, and failure modes
2. **Anomalies**: Detect unusual log frequency, timing patterns, or unexpected messages
3. **Root Causes**: Trace the sequence of events leading to failures
4. **Context**: Correlate errors across services/components

Output format:
```
ANALYSIS:
[Your analysis of the log patterns]

ERROR PATTERNS:
- Pattern 1: [description] (frequency: N)
- Pattern 2: [description] (frequency: N)

ANOMALIES:
- Anomaly 1: [description]
- Anomaly 2: [description]

ROOT CAUSE HYPOTHESIS:
[Hypothesis about what's causing the issues]

CONFIDENCE: [0.0-1.0]

RECOMMENDATION: [Actionable recommendation]
```

Be specific, evidence-based, and actionable. If data is insufficient, state what additional information would help.
"""

    async def analyze(
        self, context: dict[str, Any], model: str | None = None
    ) -> AgentResponse:
        """
        Analyze log data for patterns and issues.

        Args:
            context: Must contain 'logs' key with list of log entries
                    Optional: 'time_range', 'service', 'severity_filter'
        """
        logs = context.get("logs", [])
        service = context.get("service", "unknown")
        time_range = context.get("time_range", "unknown")

        if not logs:
            return AgentResponse(
                agent_name=self.name,
                insights={"error": "No logs provided for analysis"},
                confidence=0.0,
                error="No logs provided",
            )

        # Pre-process logs: extract error patterns
        error_logs = self._extract_errors(logs)
        error_patterns = self._find_error_patterns(error_logs)
        anomalies = self._detect_anomalies(logs)

        # Build analysis prompt
        log_sample = self._prepare_log_sample(logs, max_lines=100)

        prompt = f"""Analyze these logs from service '{service}' over {time_range}.

Context:
- Total log entries: {len(logs)}
- Error entries: {len(error_logs)}
- Identified patterns: {len(error_patterns)}

{wrap_untrusted_data(f"Sample logs:\n{log_sample}\n\nDetected error patterns:\n{self._format_error_patterns(error_patterns)}\n\nDetected anomalies:\n{self._format_anomalies(anomalies)}")}

Provide analysis focusing on root causes and actionable recommendations.
"""

        try:
            response_text = await self._query_claude(prompt, max_tokens=2048, model=model)

            # Extract insights from response
            insights = {
                "total_logs": len(logs),
                "error_count": len(error_logs),
                "error_rate": len(error_logs) / len(logs) if logs else 0,
                "patterns_found": len(error_patterns),
                "anomalies_found": len(anomalies),
            }

            recommendations = self._extract_recommendations(response_text)

            # Estimate confidence based on data quality
            confidence = self._calculate_confidence(
                data_quality=0.9 if len(logs) > 50 else 0.7,
                data_volume=len(logs),
            )

            return AgentResponse(
                agent_name=self.name,
                insights=insights,
                confidence=confidence,
                recommendations=recommendations,
                metadata={"analysis_text": response_text},
            )

        except Exception as e:
            logger.error(f"Log analysis failed: {e}")
            return AgentResponse(
                agent_name=self.name,
                insights=insights if "insights" in locals() else {},
                confidence=0.0,
                error=str(e),
            )

    def _extract_errors(self, logs: list[dict]) -> list[dict]:
        """Extract error-level logs."""
        errors = []
        for log in logs:
            level = str(log.get("level", "")).lower()
            message = log.get("message", "")
            if level in ["error", "fatal", "critical"] or "error" in message.lower():
                errors.append(log)
        return errors

    def _find_error_patterns(self, error_logs: list[dict]) -> dict[str, int]:
        """Find recurring error patterns."""
        patterns = Counter()

        for log in error_logs:
            message = log.get("message", "")

            # Extract error type from common patterns
            # e.g., "NullPointerException", "ConnectionError", etc.
            error_type = self._extract_error_type(message)
            if error_type:
                patterns[error_type] += 1

            # Extract stack trace signatures
            stack_trace = log.get("stack_trace", "")
            if stack_trace:
                signature = self._extract_stack_signature(stack_trace)
                if signature:
                    patterns[f"stack:{signature}"] += 1

        return dict(patterns.most_common(10))

    def _extract_error_type(self, message: str) -> str:
        """Extract error type from error message."""
        # Common patterns: "ErrorType: message", "Caused by ErrorType"
        patterns = [
            r"([A-Z][a-zA-Z]*(?:Error|Exception)):",
            r"Caused by ([A-Z][a-zA-Z]*(?:Error|Exception))",
            r"(NullPointerException|ConnectionError|TimeoutError)",
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)

        return "UnknownError"

    def _extract_stack_signature(self, stack_trace: str) -> str:
        """Extract signature from stack trace."""
        # Take first 3 unique class/method names
        lines = stack_trace.split("\n")
        signature = []

        for line in lines:
            # Pattern: "at com.example.Class.method(Class.java:123)"
            match = re.search(r"at\s+(\w+\.\w+\.\w+)", line)
            if match:
                parts = match.group(1).split(".")
                if len(parts) >= 2:
                    signature.append(parts[-2] + "." + parts[-1])
                    if len(signature) >= 3:
                        break

        return "->".join(signature) if signature else "unknown"

    def _detect_anomalies(self, logs: list[dict]) -> list[dict]:
        """Detect anomalies in log patterns."""
        anomalies = []

        # Check for log frequency anomalies
        if len(logs) > 100:
            _timestamps = [log.get("timestamp", "") for log in logs]
            # Simple implementation: check for gaps in timestamps
            # (Full implementation would use statistical methods)

        # Check for repeated error bursts
        error_bursts = self._find_error_bursts(logs)
        if error_bursts:
            anomalies.extend(
                {"type": "error_burst", "details": burst} for burst in error_bursts
            )

        # Check for unusual log size patterns
        large_logs = [log for log in logs if len(log.get("message", "")) > 1000]
        if len(large_logs) > len(logs) * 0.1:  # More than 10% large logs
            anomalies.append(
                {
                    "type": "large_log_entries",
                    "count": len(large_logs),
                    "percentage": len(large_logs) / len(logs),
                }
            )

        return anomalies

    @staticmethod
    def _timestamp_to_epoch(timestamp: Any) -> float | None:
        """Convert a log timestamp (ISO string or numeric epoch) to seconds."""
        if isinstance(timestamp, (int, float)):
            return float(timestamp)
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            return parsed.timestamp()
        except ValueError:
            return None

    def _find_error_bursts(self, logs: list[dict]) -> list[dict]:
        """Find periods of high error frequency."""
        # Group logs by time window (1 minute)
        window_size = 60  # seconds
        error_counts = Counter()

        for log in logs:
            if str(log.get("level", "")).lower() in ["error", "fatal"]:
                epoch = self._timestamp_to_epoch(log.get("timestamp", 0))
                if epoch is None:
                    continue
                window = int(epoch // window_size)
                error_counts[window] += 1

        # Find windows with abnormally high errors
        avg_errors = sum(error_counts.values()) / len(error_counts) if error_counts else 0
        threshold = avg_errors * 3  # 3x average

        bursts = []
        for window, count in error_counts.items():
            if count > threshold:
                bursts.append({"window_start": window * window_size, "error_count": count})

        return bursts

    def _prepare_log_sample(self, logs: list[dict], max_lines: int = 100) -> str:
        """Prepare a readable sample of logs for analysis.

        Each message is head-truncated (token-optimization 2026-08-31) — a
        single stack trace used to outweigh the rest of the sample.
        """
        sample = []
        for _i, log in enumerate(logs[:max_lines]):
            timestamp = log.get("timestamp", "")
            level = log.get("level", "")
            message = truncate_text(str(log.get("message", "")))
            sample.append(f"[{timestamp}] {level}: {message}")

        if len(logs) > max_lines:
            sample.append(f"... ({len(logs) - max_lines} more logs)")

        return "\n".join(sample)

    def _format_error_patterns(self, patterns: dict[str, int]) -> str:
        """Format error patterns for display."""
        if not patterns:
            return "No patterns detected"

        lines = []
        for pattern, count in patterns.items():
            lines.append(f"- {pattern}: {count} occurrences")

        return "\n".join(lines)

    def _format_anomalies(self, anomalies: list[dict]) -> str:
        """Format anomalies for display."""
        if not anomalies:
            return "No anomalies detected"

        lines = []
        for anomaly in anomalies:
            anomaly_type = anomaly.get("type", "unknown")
            lines.append(f"- {anomaly_type}: {anomaly}")

        return "\n".join(lines)
