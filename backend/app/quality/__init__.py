"""
Quality Assurance Package - Validation and testing components.

Provides accuracy validation, A/B testing, and quality gates for
optimization results.

Phase 6: AI Input Optimization
"""

from app.quality.accuracy_validator import (
    AccuracyValidator,
    AccuracyReport,
    get_accuracy_validator
)

from app.quality.ab_tester import (
    ABTester,
    ABTestResult,
    TestVariant,
    get_ab_tester
)

__all__ = [
    "AccuracyValidator",
    "AccuracyReport",
    "get_accuracy_validator",
    "ABTester",
    "ABTestResult",
    "TestVariant",
    "get_ab_tester"
]
