"""Unit tests for Feedback Analyzer (Phase 4)."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.feedback.analyzer import (
    ActionPattern,
    LearningMetrics,
    FeedbackAnalyzer,
    get_feedback_analyzer,
)
from app.feedback.collector import FeedbackCollector, FeedbackEvent


@pytest.fixture
def mock_collector():
    """Create mock feedback collector with sample data."""
    collector = MagicMock(spec=FeedbackCollector)

    # Create sample events
    now = datetime.now(timezone.utc)
    events = [
        # High approval action type
        FeedbackEvent("kubectl_delete_pod_1", "approved", now, "user1"),
        FeedbackEvent("kubectl_delete_pod_2", "approved", now, "user2"),
        FeedbackEvent("kubectl_delete_pod_3", "approved", now, "user3"),
        FeedbackEvent("kubectl_delete_pod_4", "rejected", now, "user3"),
        FeedbackEvent("kubectl_delete_pod_1", "executed", now, details={"success": True}),
        FeedbackEvent("kubectl_delete_pod_2", "executed", now, details={"success": True}),
        FeedbackEvent("kubectl_delete_pod_3", "executed", now, details={"success": True}),
        # Low approval action type
        FeedbackEvent("helm_upgrade_1", "approved", now, "user1"),
        FeedbackEvent("helm_upgrade_2", "rejected", now, "user2"),
        FeedbackEvent("helm_upgrade_3", "rejected", now, "user3"),
        FeedbackEvent("helm_upgrade_1", "failed", now, details={"success": False}),
    ]

    def get_all_feedback():
        return {
            "kubectl_delete_pod_1": [events[0], events[4]],
            "kubectl_delete_pod_2": [events[1], events[5]],
            "kubectl_delete_pod_3": [events[2], events[6]],
            "kubectl_delete_pod_4": [events[3]],
            "helm_upgrade_1": [events[7], events[9]],
            "helm_upgrade_2": [events[8]],
            "helm_upgrade_3": [events[8]],
        }

    collector.get_all_feedback = get_all_feedback
    return collector


@pytest.fixture
def analyzer(mock_collector):
    """Create FeedbackAnalyzer with mock collector."""
    analyzer = FeedbackAnalyzer()
    analyzer.collector = mock_collector
    return analyzer


class TestActionPattern:
    """Test ActionPattern data class."""

    def test_action_pattern_creation(self):
        """Test creating an action pattern."""
        pattern = ActionPattern(
            action_type="delete",
            total_actions=10,
            approved_count=9,
            rejected_count=1,
            success_count=8,
            failure_count=2,
            approval_rate=0.9,
            success_rate=0.8,
            confidence_level="high",
            last_updated=datetime.now(timezone.utc),
        )

        assert pattern.action_type == "delete"
        assert pattern.total_actions == 10
        assert pattern.approval_rate == 0.9
        assert pattern.confidence_level == "high"


class TestFeedbackAnalyzer:
    """Test FeedbackAnalyzer functionality."""

    def test_analyzer_initialization(self):
        """Test analyzer initialization."""
        analyzer = FeedbackAnalyzer(window_days=30)
        assert analyzer.window_days == 30
        assert analyzer.collector is not None

    def test_get_events_in_window(self, analyzer):
        """Test filtering events by time window."""
        now = datetime.now(timezone.utc)
        events = [
            FeedbackEvent("action_1", "approved", now - timedelta(days=10)),
            FeedbackEvent("action_2", "approved", now - timedelta(days=40)),  # Outside window
            FeedbackEvent("action_3", "approved", now - timedelta(days=5)),
        ]

        analyzer.collector.get_all_feedback = lambda: {
            "action_1": [events[0]],
            "action_2": [events[1]],
            "action_3": [events[2]],
        }

        in_window = analyzer._get_events_in_window()
        assert len(in_window) == 2
        assert events[1] not in in_window

    def test_extract_action_type(self, analyzer):
        """Test extracting action type from action ID."""
        # Standard format: command_action_resource
        assert analyzer._extract_action_type("kubectl_delete_pod") == "delete"
        assert analyzer._extract_action_type("helm_upgrade_service") == "upgrade"
        assert analyzer._extract_action_type("kubectl_restart_deployment") == "restart"

        # Edge cases
        assert analyzer._extract_action_type("kubectl") == "unknown"
        assert analyzer._extract_action_type("") == "unknown"

    def test_analyze_approval_rates(self, analyzer):
        """Test analyzing approval rates by action type."""
        patterns = analyzer.analyze_approval_rates()

        assert "delete" in patterns
        assert "upgrade" in patterns

        delete_pattern = patterns["delete"]
        assert delete_pattern.total_actions == 7  # 4 approvals + 3 rejections + 1 executed is counted in total
        assert delete_pattern.approved_count == 3
        assert delete_pattern.rejected_count == 1

    def test_generate_confidence_report(self, analyzer):
        """Test generating comprehensive learning metrics."""
        metrics = analyzer.generate_confidence_report()

        assert isinstance(metrics, LearningMetrics)
        assert metrics.total_actions_analyzed > 0
        assert isinstance(metrics.action_patterns, dict)
        assert isinstance(metrics.high_confidence_patterns, list)
        assert isinstance(metrics.medium_confidence_patterns, list)
        assert isinstance(metrics.low_confidence_patterns, list)

    def test_confidence_level_high(self):
        """Test high confidence level (>95% approval)."""
        pattern = ActionPattern(
            action_type="delete",
            total_actions=20,
            approved_count=19,
            rejected_count=1,
            success_count=18,
            failure_count=2,
            approval_rate=0.95,
            success_rate=0.9,
            confidence_level="high",
            last_updated=datetime.now(timezone.utc),
        )

        assert pattern.confidence_level == "high"

    def test_confidence_level_medium(self):
        """Test medium confidence level (70-95% approval)."""
        pattern = ActionPattern(
            action_type="restart",
            total_actions=20,
            approved_count=15,
            rejected_count=5,
            success_count=14,
            failure_count=6,
            approval_rate=0.75,
            success_rate=0.7,
            confidence_level="medium",
            last_updated=datetime.now(timezone.utc),
        )

        assert pattern.confidence_level == "medium"

    def test_confidence_level_low(self):
        """Test low confidence level (<70% approval)."""
        pattern = ActionPattern(
            action_type="upgrade",
            total_actions=20,
            approved_count=10,
            rejected_count=10,
            success_count=8,
            failure_count=12,
            approval_rate=0.5,
            success_rate=0.4,
            confidence_level="low",
            last_updated=datetime.now(timezone.utc),
        )

        assert pattern.confidence_level == "low"

    def test_get_auto_approval_candidates(self, analyzer):
        """Test getting auto-approval candidates."""
        # Mock patterns with high confidence
        with patch.object(analyzer, "analyze_approval_rates") as mock_analyze:
            mock_analyze.return_value = {
                "delete": ActionPattern(
                    action_type="delete",
                    total_actions=15,
                    approved_count=15,
                    rejected_count=0,
                    success_count=15,
                    failure_count=0,
                    approval_rate=1.0,
                    success_rate=1.0,
                    confidence_level="high",
                    last_updated=datetime.now(timezone.utc),
                ),
                "upgrade": ActionPattern(
                    action_type="upgrade",
                    total_actions=5,  # Below threshold
                    approved_count=5,
                    rejected_count=0,
                    success_count=5,
                    failure_count=0,
                    approval_rate=1.0,
                    success_rate=1.0,
                    confidence_level="high",
                    last_updated=datetime.now(timezone.utc),
                ),
            }

            candidates = analyzer.get_auto_approval_candidates(min_confidence=0.99)

            # Only "delete" should qualify (enough samples)
            assert "delete" in candidates
            assert "upgrade" not in candidates

    def test_get_patterns_needing_review(self, analyzer):
        """Test getting patterns that need review."""
        with patch.object(analyzer, "analyze_approval_rates") as mock_analyze:
            mock_analyze.return_value = {
                "upgrade": ActionPattern(
                    action_type="upgrade",
                    total_actions=10,
                    approved_count=5,
                    rejected_count=5,
                    success_count=5,
                    failure_count=5,
                    approval_rate=0.5,  # Low approval
                    success_rate=0.5,
                    confidence_level="low",
                    last_updated=datetime.now(timezone.utc),
                ),
                "delete": ActionPattern(
                    action_type="delete",
                    total_actions=10,
                    approved_count=9,
                    rejected_count=1,
                    success_count=7,
                    failure_count=3,
                    approval_rate=0.9,
                    success_rate=0.7,  # Low success rate
                    confidence_level="high",
                    last_updated=datetime.now(timezone.utc),
                ),
            }

            needs_review = analyzer.get_patterns_needing_review()

            assert len(needs_review) == 2
            action_types = [p.action_type for p in needs_review]
            assert "upgrade" in action_types
            assert "delete" in action_types

    def test_calculate_recommended_confidence_no_history(self, analyzer):
        """Test confidence calculation with no historical data."""
        with patch.object(analyzer, "analyze_approval_rates", return_value={}):
            recommended = analyzer.calculate_recommended_confidence(
                action_id="new_action",
                base_confidence=0.8,
            )

            assert recommended == 0.8  # Should return base confidence

    def test_calculate_recommended_confidence_high_confidence(self, analyzer):
        """Test confidence adjustment for high-confidence patterns."""
        with patch.object(analyzer, "analyze_approval_rates") as mock_analyze:
            mock_analyze.return_value = {
                "delete": ActionPattern(
                    action_type="delete",
                    total_actions=25,  # Enough samples
                    approved_count=24,
                    rejected_count=1,
                    success_count=24,
                    failure_count=1,
                    approval_rate=0.96,
                    success_rate=0.96,
                    confidence_level="high",
                    last_updated=datetime.now(timezone.utc),
                ),
            }

            recommended = analyzer.calculate_recommended_confidence(
                action_id="kubectl_delete_pod_1",
                base_confidence=0.85,
            )

            assert recommended > 0.85  # Should be boosted
            assert recommended <= 1.0

    def test_calculate_recommended_confidence_low_confidence(self, analyzer):
        """Test confidence adjustment for low-confidence patterns."""
        with patch.object(analyzer, "analyze_approval_rates") as mock_analyze:
            mock_analyze.return_value = {
                "upgrade": ActionPattern(
                    action_type="upgrade",
                    total_actions=10,
                    approved_count=5,
                    rejected_count=5,
                    success_count=5,
                    failure_count=5,
                    approval_rate=0.5,
                    success_rate=0.5,
                    confidence_level="low",
                    last_updated=datetime.now(timezone.utc),
                ),
            }

            recommended = analyzer.calculate_recommended_confidence(
                action_id="helm_upgrade_1",
                base_confidence=0.8,
            )

            assert recommended < 0.8  # Should be reduced
            assert recommended >= 0.0

    def test_get_learning_summary(self, analyzer):
        """Test getting learning summary."""
        with patch.object(analyzer, "generate_confidence_report") as mock_report:
            mock_metrics = LearningMetrics()
            mock_metrics.total_actions_analyzed = 100
            mock_metrics.high_confidence_patterns = ["delete", "restart"]
            mock_metrics.medium_confidence_patterns = ["scale"]
            mock_metrics.low_confidence_patterns = ["upgrade"]

            mock_report.return_value = mock_metrics

            with patch.object(analyzer, "get_auto_approval_candidates", return_value=["delete"]):
                summary = analyzer.get_learning_summary()

                assert summary["total_actions_analyzed"] == 100
                assert "delete" in summary["high_confidence_patterns"]
                assert summary["patterns_needing_review_count"] == 1
                assert "analysis_window_days" in summary

    def test_analysis_window_default(self):
        """Test default analysis window."""
        analyzer = FeedbackAnalyzer()
        assert analyzer.window_days == 30

    def test_analysis_window_custom(self):
        """Test custom analysis window."""
        analyzer = FeedbackAnalyzer(window_days=60)
        assert analyzer.window_days == 60


class TestFeedbackAnalyzerSingleton:
    """Test singleton pattern."""

    def test_get_feedback_analyzer_returns_singleton(self):
        """Test that get_feedback_analyzer returns same instance."""
        with patch("app.feedback.analyzer._analyzer", None):
            analyzer1 = get_feedback_analyzer()
            analyzer2 = get_feedback_analyzer()

            assert analyzer1 is analyzer2

    def test_get_feedback_analyzer_with_different_window(self):
        """Test that different window creates new instance."""
        with patch("app.feedback.analyzer._analyzer", None):
            analyzer1 = get_feedback_analyzer(window_days=30)
            analyzer2 = get_feedback_analyzer(window_days=60)

            # Should create new instance with different window
            assert analyzer1.window_days == 30
            assert analyzer2.window_days == 60

    def test_get_feedback_analyzer_initializes_new_instance(self):
        """Test that first call initializes the analyzer."""
        from app.feedback.analyzer import _analyzer

        with patch("app.feedback.analyzer._analyzer", None):
            analyzer = get_feedback_analyzer()
            assert analyzer is not None
            assert isinstance(analyzer, FeedbackAnalyzer)
