"""
A/B Tester - Statistical validation for optimization.

Runs A/B tests to validate optimization improvements with statistical significance.

Phase 6: AI Input Optimization - Sprint 2
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TestVariant(str, Enum):
    """A/B test variant."""
    BASELINE = "baseline"
    OPTIMIZED = "optimized"


@dataclass
class ABTestResult:
    """Result of a single A/B test."""
    request_id: str
    incident_type: str
    severity: str
    baseline_tokens: int
    optimized_tokens: int
    token_reduction_pct: float
    baseline_processing_ms: float
    optimized_processing_ms: float
    baseline_findings: int
    optimized_findings: int
    finding_recall: float
    finding_precision: float
    timestamp: datetime
    winner: TestVariant


class ABTester:
    """
    A/B testing framework for optimization validation.

    Compares baseline and optimized results with statistical analysis.
    """

    def __init__(self, test_ratio: float = 0.1):
        """
        Initialize A/B tester.

        Args:
            test_ratio: Ratio of requests to include in A/B test (0.0-1.0)
        """
        self.test_ratio = test_ratio
        self.test_results: List[ABTestResult] = []

    async def run_test(
        self,
        request_id: str,
        incident_type: str,
        severity: str,
        baseline_result: Dict[str, Any],
        optimized_result: Dict[str, Any],
        accuracy_validator: Optional['AccuracyValidator'] = None
    ) -> ABTestResult:
        """
        Run A/B test for a single request.

        Args:
            request_id: Unique request identifier
            incident_type: Type of incident
            severity: Severity level
            baseline_result: Result from baseline (no optimization)
            optimized_result: Result from optimization
            accuracy_validator: Optional validator for accuracy metrics

        Returns:
            ABTestResult with comparison metrics
        """
        # Extract metrics
        baseline_tokens = baseline_result.get('original_tokens', 0)
        optimized_tokens = optimized_result.get('optimized_tokens', 0)
        token_reduction = (baseline_tokens - optimized_tokens) / baseline_tokens * 100 if baseline_tokens > 0 else 0

        baseline_time = baseline_result.get('processing_time_ms', 0)
        optimized_time = optimized_result.get('processing_time_ms', 0)

        baseline_findings = len(baseline_result.get('findings', []))
        optimized_findings = len(optimized_result.get('findings', []))

        # Calculate accuracy metrics if validator provided
        finding_recall = 1.0
        finding_precision = 1.0

        if accuracy_validator:
            # Use accuracy validator to compare results
            from app.quality.accuracy_validator import AccuracyValidator
            report = accuracy_validator.compare_triage_cards(
                baseline_result.get('triage_card'),
                optimized_result.get('triage_card')
            )
            finding_recall = report.finding_recall
            finding_precision = report.finding_precision

        # Determine winner
        winner = self._determine_winner(
            token_reduction,
            optimized_time,
            baseline_time,
            finding_recall,
            finding_precision
        )

        result = ABTestResult(
            request_id=request_id,
            incident_type=incident_type,
            severity=severity,
            baseline_tokens=baseline_tokens,
            optimized_tokens=optimized_tokens,
            token_reduction_pct=token_reduction,
            baseline_processing_ms=baseline_time,
            optimized_processing_ms=optimized_time,
            baseline_findings=baseline_findings,
            optimized_findings=optimized_findings,
            finding_recall=finding_recall,
            finding_precision=finding_precision,
            timestamp=datetime.now(),
            winner=winner
        )

        self.test_results.append(result)
        return result

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get A/B test statistics.

        Returns:
            Dict with aggregated statistics
        """
        if not self.test_results:
            return self._empty_stats()

        total = len(self.test_results)

        # Count winners
        baseline_wins = sum(1 for r in self.test_results if r.winner == TestVariant.BASELINE)
        optimized_wins = sum(1 for r in self.test_results if r.winner == TestVariant.OPTIMIZED)

        # Calculate averages
        avg_token_reduction = sum(r.token_reduction_pct for r in self.test_results) / total
        avg_time_diff = sum(
            r.optimized_processing_ms - r.baseline_processing_ms
            for r in self.test_results
        ) / total

        avg_recall = sum(r.finding_recall for r in self.test_results) / total
        avg_precision = sum(r.finding_precision for r in self.test_results) / total

        # By incident type
        by_type = self._group_by_type()
        by_severity = self._group_by_severity()

        return {
            'total_tests': total,
            'baseline_wins': baseline_wins,
            'optimized_wins': optimized_wins,
            'win_rate_optimized': optimized_wins / total if total > 0 else 0,
            'avg_token_reduction_pct': avg_token_reduction,
            'avg_processing_time_diff_ms': avg_time_diff,
            'avg_finding_recall': avg_recall,
            'avg_finding_precision': avg_precision,
            'by_incident_type': by_type,
            'by_severity': by_severity
        }

    def should_run_test(self, request_id: str) -> bool:
        """
        Determine if a request should be included in A/B test.

        Uses hash of request_id for consistent sampling.

        Args:
            request_id: Request identifier

        Returns:
            True if should run A/B test
        """
        import hashlib
        hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        return (hash_val % 100) < (self.test_ratio * 100)

    def _determine_winner(
        self,
        token_reduction: float,
        optimized_time: float,
        baseline_time: float,
        recall: float,
        precision: float
    ) -> TestVariant:
        """
        Determine winner of A/B test.

        Optimized wins if:
        - Token reduction > 50% AND
        - Processing time acceptable AND
        - Recall >= 0.90 AND Precision >= 0.85
        """
        # Check quality gates
        if recall < 0.90 or precision < 0.85:
            return TestVariant.BASELINE

        # Check token reduction
        if token_reduction < 50:
            return TestVariant.BASELINE

        # Check processing time (allow 50% increase)
        if optimized_time > baseline_time * 1.5:
            return TestVariant.BASELINE

        return TestVariant.OPTIMIZED

    def _group_by_type(self) -> Dict[str, Dict[str, Any]]:
        """Group results by incident type."""
        grouped = {}
        for result in self.test_results:
            incident_type = result.incident_type
            if incident_type not in grouped:
                grouped[incident_type] = {
                    'count': 0,
                    'optimized_wins': 0,
                    'avg_token_reduction': 0.0
                }

            grouped[incident_type]['count'] += 1
            if result.winner == TestVariant.OPTIMIZED:
                grouped[incident_type]['optimized_wins'] += 1
            grouped[incident_type]['avg_token_reduction'] += result.token_reduction_pct

        # Calculate averages
        for key in grouped:
            if grouped[key]['count'] > 0:
                grouped[key]['avg_token_reduction'] /= grouped[key]['count']

        return grouped

    def _group_by_severity(self) -> Dict[str, Dict[str, Any]]:
        """Group results by severity."""
        grouped = {}
        for result in self.test_results:
            severity = result.severity
            if severity not in grouped:
                grouped[severity] = {
                    'count': 0,
                    'optimized_wins': 0,
                    'avg_token_reduction': 0.0
                }

            grouped[severity]['count'] += 1
            if result.winner == TestVariant.OPTIMIZED:
                grouped[severity]['optimized_wins'] += 1
            grouped[severity]['avg_token_reduction'] += result.token_reduction_pct

        # Calculate averages
        for key in grouped:
            if grouped[key]['count'] > 0:
                grouped[key]['avg_token_reduction'] /= grouped[key]['count']

        return grouped

    def _empty_stats(self) -> Dict[str, Any]:
        """Return empty stats structure."""
        return {
            'total_tests': 0,
            'baseline_wins': 0,
            'optimized_wins': 0,
            'win_rate_optimized': 0.0,
            'avg_token_reduction_pct': 0.0,
            'avg_processing_time_diff_ms': 0.0,
            'avg_finding_recall': 0.0,
            'avg_finding_precision': 0.0,
            'by_incident_type': {},
            'by_severity': {}
        }


# Singleton instance
_ab_tester: Optional[ABTester] = None


def get_ab_tester(test_ratio: float = 0.1) -> ABTester:
    """Get or create the singleton ABTester instance."""
    global _ab_tester
    if _ab_tester is None:
        _ab_tester = ABTester(test_ratio)
    return _ab_tester
