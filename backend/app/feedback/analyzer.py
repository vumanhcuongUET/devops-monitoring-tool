"""Feedback analyzer for continuous learning.

This module analyzes feedback patterns to:
- Calculate approval rates by action type
- Identify high-confidence patterns (>95% approval)
- Detect low-confidence patterns needing review
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dataclasses import dataclass

from app.feedback.collector import get_feedback_collector, FeedbackEvent

logger = logging.getLogger(__name__)


@dataclass
class ActionPattern:
    """Represents an action pattern with learning metrics."""
    action_type: str
    total_actions: int
    approved_count: int
    rejected_count: int
    success_count: int
    failure_count: int
    approval_rate: float
    success_rate: float
    confidence_level: str  # "high" (>95%), "medium" (70-95%), "low" (<70%)
    last_updated: datetime


class LearningMetrics:
    """Aggregated learning metrics."""

    def __init__(self):
        self.total_actions_analyzed = 0
        self.high_confidence_patterns: List[str] = []
        self.medium_confidence_patterns: List[str] = []
        self.low_confidence_patterns: List[str] = []
        self.action_patterns: Dict[str, ActionPattern] = {}


class FeedbackAnalyzer:
    """Analyzes feedback patterns for continuous learning."""

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.95  # 95% approval rate
    MEDIUM_CONFIDENCE_MIN = 0.70      # 70% approval rate
    LOW_CONFIDENCE_THRESHOLD = 0.70   # Below 70% is low confidence

    def __init__(self, window_days: int = 30):
        """Initialize feedback analyzer.

        Args:
            window_days: Number of days to look back for analysis
        """
        self.window_days = window_days
        self.collector = get_feedback_collector()

    def _get_events_in_window(self) -> List[FeedbackEvent]:
        """Get feedback events within the analysis window.

        Returns:
            List of feedback events within the window
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        all_feedback = self.collector.get_all_feedback()

        events_in_window = []
        for events in all_feedback.values():
            for event in events:
                if event.timestamp > cutoff:
                    events_in_window.append(event)

        return events_in_window

    def _extract_action_type(self, action_id: str) -> str:
        """Extract action type from action ID.

        Args:
            action_id: Action ID (e.g., "kubectl_delete_pod", "helm_upgrade")

        Returns:
            Action type string (e.g., "delete", "upgrade")
        """
        # Action IDs follow pattern: command_action_resource
        # Extract the action part
        parts = action_id.split("_")
        if len(parts) >= 2:
            return parts[1]
        return "unknown"

    def analyze_approval_rates(self) -> Dict[str, ActionPattern]:
        """Analyze approval rates by action type.

        Returns:
            Dict mapping action_type to ActionPattern
        """
        events = self._get_events_in_window()
        action_metrics = defaultdict(lambda: {
            "total": 0,
            "approved": 0,
            "rejected": 0,
            "executed": 0,
            "failed": 0,
        })

        # Group events by action type
        for event in events:
            action_type = self._extract_action_type(event.action_id)
            metrics = action_metrics[action_type]
            metrics["total"] += 1

            if event.event_type == "approved":
                metrics["approved"] += 1
            elif event.event_type == "rejected":
                metrics["rejected"] += 1
            elif event.event_type == "executed":
                metrics["executed"] += 1
            elif event.event_type == "failed":
                metrics["failed"] += 1

        # Calculate patterns
        patterns = {}
        for action_type, metrics in action_metrics.items():
            total = metrics["total"]
            approved = metrics["approved"]
            executed = metrics["executed"]
            failed = metrics["failed"]

            approval_rate = approved / total if total > 0 else 0.0
            success_rate = executed / (executed + failed) if (executed + failed) > 0 else 0.0

            if approval_rate >= self.HIGH_CONFIDENCE_THRESHOLD:
                confidence = "high"
            elif approval_rate >= self.MEDIUM_CONFIDENCE_MIN:
                confidence = "medium"
            else:
                confidence = "low"

            patterns[action_type] = ActionPattern(
                action_type=action_type,
                total_actions=total,
                approved_count=approved,
                rejected_count=metrics["rejected"],
                success_count=executed,
                failure_count=failed,
                approval_rate=approval_rate,
                success_rate=success_rate,
                confidence_level=confidence,
                last_updated=datetime.now(timezone.utc),
            )

        return patterns

    def generate_confidence_report(self) -> LearningMetrics:
        """Generate comprehensive learning metrics report.

        Returns:
            LearningMetrics with aggregated analysis
        """
        patterns = self.analyze_approval_rates()

        metrics = LearningMetrics()
        metrics.action_patterns = patterns
        metrics.total_actions_analyzed = sum(p.total_actions for p in patterns.values())

        for action_type, pattern in patterns.items():
            if pattern.confidence_level == "high":
                metrics.high_confidence_patterns.append(action_type)
            elif pattern.confidence_level == "medium":
                metrics.medium_confidence_patterns.append(action_type)
            else:
                metrics.low_confidence_patterns.append(action_type)

        return metrics

    def get_auto_approval_candidates(self, min_confidence: float = 0.99) -> List[str]:
        """Get action types that could be auto-approved based on confidence.

        Args:
            min_confidence: Minimum confidence level for auto-approval

        Returns:
            List of action types meeting the confidence threshold
        """
        patterns = self.analyze_approval_rates()
        candidates = []

        for action_type, pattern in patterns.items():
            if pattern.approval_rate >= min_confidence and pattern.total_actions >= 10:
                candidates.append(action_type)

        return candidates

    def get_patterns_needing_review(self) -> List[ActionPattern]:
        """Get action patterns that need human review.

        Returns:
            List of low-confidence patterns needing attention
        """
        patterns = self.analyze_approval_rates()
        needs_review = []

        for action_type, pattern in patterns.items():
            # Flag for review if:
            # 1. Low confidence (<70% approval)
            # 2. OR high rejection rate (>30%)
            # 3. OR high failure rate (>20%)
            if (
                pattern.confidence_level == "low"
                or pattern.approval_rate < 0.7
                or pattern.success_rate < 0.8
            ):
                needs_review.append(pattern)

        return sorted(needs_review, key=lambda p: p.approval_rate)

    def calculate_recommended_confidence(
        self,
        action_id: str,
        base_confidence: float,
    ) -> float:
        """Calculate recommended confidence score based on historical data.

        Args:
            action_id: ID of the action
            base_confidence: Base confidence from AI/model

        Returns:
            Adjusted confidence score (0.0-1.0)
        """
        action_type = self._extract_action_type(action_id)
        patterns = self.analyze_approval_rates()

        if action_type not in patterns:
            # No historical data, return base confidence
            return base_confidence

        pattern = patterns[action_type]

        # Adjust confidence based on historical performance
        if pattern.confidence_level == "high" and pattern.total_actions >= 20:
            # Boost confidence for proven patterns
            return min(1.0, base_confidence + 0.1)
        elif pattern.confidence_level == "low":
            # Reduce confidence for problematic patterns
            return max(0.0, base_confidence - 0.2)

        # For medium confidence, use weighted average
        historical_weight = min(0.3, pattern.total_actions / 100)  # Max 30% weight
        adjusted = (
            base_confidence * (1 - historical_weight) +
            pattern.approval_rate * historical_weight
        )
        return adjusted

    def get_learning_summary(self) -> Dict[str, Any]:
        """Get summary of learning metrics.

        Returns:
            Dict with learning summary
        """
        metrics = self.generate_confidence_report()

        return {
            "analysis_window_days": self.window_days,
            "total_actions_analyzed": metrics.total_actions_analyzed,
            "high_confidence_patterns": metrics.high_confidence_patterns,
            "medium_confidence_patterns": metrics.medium_confidence_patterns,
            "low_confidence_patterns": metrics.low_confidence_patterns,
            "auto_approval_candidates": self.get_auto_approval_candidates(),
            "patterns_needing_review_count": len(metrics.low_confidence_patterns),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


# Singleton instance
_analyzer: Optional[FeedbackAnalyzer] = None


def get_feedback_analyzer(window_days: int = 30) -> FeedbackAnalyzer:
    """Get or create the singleton FeedbackAnalyzer instance.

    Args:
        window_days: Number of days to look back for analysis

    Returns:
        FeedbackAnalyzer instance
    """
    global _analyzer
    if _analyzer is None or _analyzer.window_days != window_days:
        _analyzer = FeedbackAnalyzer(window_days=window_days)
    return _analyzer
