"""
Accuracy Validator - Quality assurance for optimization results.

Validates that optimization maintains accuracy while reducing tokens.

Phase 6: AI Input Optimization - Sprint 2
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TriageCard:
    """Mock triage card for validation."""
    findings: List[Dict[str, Any]]
    severity: str
    recommendations: List[str]
    incident_type: str


@dataclass
class AccuracyReport:
    """Report of accuracy validation."""
    finding_recall: float  # TP / (TP + FN)
    finding_precision: float  # TP / (TP + FP)
    severity_accuracy: float  # Correct severity / total
    recommendation_relevance: float  # Actionable / total
    total_baseline_findings: int
    total_optimized_findings: int
    true_positives: int
    false_positives: int
    false_negatives: int
    timestamp: datetime


class AccuracyValidator:
    """
    Validate accuracy of optimization results.

    Compares baseline and optimized triage cards against ground truth
    to ensure optimization doesn't degrade quality.
    """

    def __init__(self):
        """Initialize accuracy validator."""
        self.validation_history: List[AccuracyReport] = []

    def compare_triage_cards(
        self,
        baseline: TriageCard,
        optimized: TriageCard,
        ground_truth: Optional[Dict[str, Any]] = None
    ) -> AccuracyReport:
        """
        Compare accuracy between baseline and optimized.

        Args:
            baseline: Baseline triage card (without optimization)
            optimized: Optimized triage card
            ground_truth: Optional ground truth for validation

        Returns:
            AccuracyReport with metrics
        """
        # Extract findings
        baseline_findings = set(self._extract_finding_keys(baseline.findings))
        optimized_findings = set(self._extract_finding_keys(optimized.findings))

        # Calculate confusion matrix
        true_positives = len(baseline_findings & optimized_findings)
        false_positives = len(optimized_findings - baseline_findings)
        false_negatives = len(baseline_findings - optimized_findings)

        # Calculate metrics
        finding_recall = self._safe_divide(
            true_positives,
            true_positives + false_negatives
        )
        finding_precision = self._safe_divide(
            true_positives,
            true_positives + false_positives
        )

        # Severity accuracy
        severity_accuracy = self._calculate_severity_accuracy(
            baseline.findings,
            optimized.findings
        )

        # Recommendation relevance
        recommendation_relevance = self._calculate_recommendation_relevance(
            optimized.recommendations
        )

        report = AccuracyReport(
            finding_recall=finding_recall,
            finding_precision=finding_precision,
            severity_accuracy=severity_accuracy,
            recommendation_relevance=recommendation_relevance,
            total_baseline_findings=len(baseline_findings),
            total_optimized_findings=len(optimized_findings),
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            timestamp=datetime.now()
        )

        self.validation_history.append(report)
        return report

    def validate_quality_gates(
        self,
        report: AccuracyReport,
        min_recall: float = 0.90,
        min_precision: float = 0.85,
        min_severity_accuracy: float = 0.95
    ) -> bool:
        """
        Validate that report meets quality gates.

        Args:
            report: Accuracy report to validate
            min_recall: Minimum finding recall threshold
            min_precision: Minimum finding precision threshold
            min_severity_accuracy: Minimum severity accuracy threshold

        Returns:
            True if all gates pass, False otherwise
        """
        gates = {
            'finding_recall': (report.finding_recall, min_recall),
            'finding_precision': (report.finding_precision, min_precision),
            'severity_accuracy': (report.severity_accuracy, min_severity_accuracy)
        }

        passed = all(value >= threshold for value, threshold in gates.values())

        if not passed:
            failed = [k for k, (v, t) in gates.items() if v < t]
            logger.warning(f"Quality gates failed: {failed}")

        return passed

    def get_aggregate_metrics(self) -> Dict[str, float]:
        """
        Get aggregate accuracy metrics from history.

        Returns:
            Dict with average metrics
        """
        if not self.validation_history:
            return {
                'avg_recall': 0.0,
                'avg_precision': 0.0,
                'avg_severity_accuracy': 0.0,
                'total_validations': 0
            }

        total = len(self.validation_history)
        return {
            'avg_recall': sum(r.finding_recall for r in self.validation_history) / total,
            'avg_precision': sum(r.finding_precision for r in self.validation_history) / total,
            'avg_severity_accuracy': sum(r.severity_accuracy for r in self.validation_history) / total,
            'total_validations': total
        }

    def _extract_finding_keys(self, findings: List[Dict[str, Any]]) -> List[str]:
        """
        Extract unique keys from findings for comparison.

        Uses incident type + service + message to identify findings.
        """
        keys = []
        for finding in findings:
            key = f"{finding.get('incident_type', 'unknown')}:{finding.get('service', 'unknown')}:{finding.get('message', '')[:50]}"
            keys.append(key)
        return keys

    def _calculate_severity_accuracy(
        self,
        baseline_findings: List[Dict[str, Any]],
        optimized_findings: List[Dict[str, Any]]
    ) -> float:
        """Calculate percentage of matching severity levels."""
        if not baseline_findings:
            return 1.0

        # Create map of findings
        baseline_map = {f.get('id', i): f for i, f in enumerate(baseline_findings)}
        optimized_map = {f.get('id', i): f for i, f in enumerate(optimized_findings)}

        matching = 0
        total = 0

        for key, baseline_finding in baseline_map.items():
            if key in optimized_map:
                total += 1
                if baseline_finding.get('severity') == optimized_map[key].get('severity'):
                    matching += 1

        return self._safe_divide(matching, total)

    def _calculate_recommendation_relevance(self, recommendations: List[str]) -> float:
        """
        Calculate percentage of actionable recommendations.

        Simple heuristic: recommendations containing action verbs are relevant.
        """
        if not recommendations:
            return 1.0

        action_verbs = ['fix', 'resolve', 'check', 'investigate', 'restart', 'scale', 'update']
        actionable = sum(
            1 for rec in recommendations
            if any(verb in rec.lower() for verb in action_verbs)
        )

        return self._safe_divide(actionable, len(recommendations))

    def _safe_divide(self, numerator: int, denominator: int) -> float:
        """Safe division that returns 0 when dividing by zero."""
        if denominator == 0:
            return 0.0
        return numerator / denominator


# Singleton instance
_accuracy_validator: Optional[AccuracyValidator] = None


def get_accuracy_validator() -> AccuracyValidator:
    """Get or create the singleton AccuracyValidator instance."""
    global _accuracy_validator
    if _accuracy_validator is None:
        _accuracy_validator = AccuracyValidator()
    return _accuracy_validator
