"""
Token Budget Manager - Dynamic token budget allocation.

Manages token budgets based on severity, complexity, and other factors.

Phase 6: AI Input Optimization - Sprint 3
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class BudgetAllocation:
    """Token budget allocation for a request."""
    base_budget: int
    complexity_multiplier: float
    final_budget: int
    severity: str
    complexity_score: float


class TokenBudgetManager:
    """
    Dynamic token budget management.

    Allocates token budgets based on severity, incident complexity,
    and configurable limits.
    """

    # Default budgets by severity
    BUDGET_MATRIX = {
        'critical': 3000,
        'high': 2500,
        'medium': 2000,
        'low': 1500,
        'info': 1000
    }

    # Maximum hard limit
    MAX_BUDGET = 5000

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize token budget manager.

        Args:
            config: Optional configuration overrides
        """
        self.config = config or {}
        self.budget_matrix = self.config.get('budget_matrix', self.BUDGET_MATRIX)
        self.max_budget = self.config.get('max_budget', self.MAX_BUDGET)
        self.complexity_multiplier = self.config.get('complexity_multiplier', 0.2)

    def calculate_budget(
        self,
        severity: str,
        incident_type: str,
        context_data: Optional[Dict[str, Any]] = None
    ) -> BudgetAllocation:
        """
        Calculate token budget for a request.

        Args:
            severity: Severity level
            incident_type: Type of incident
            context_data: Optional incident context for complexity calculation

        Returns:
            BudgetAllocation with calculated budget
        """
        # Get base budget from severity
        base_budget = self.budget_matrix.get(severity.lower(), 2000)

        # Calculate complexity score
        complexity_score = self._calculate_complexity(incident_type, context_data)

        # Calculate complexity multiplier (0.0 to 0.4)
        multiplier = min(complexity_score * self.complexity_multiplier, 0.4)

        # Calculate final budget
        final_budget = int(base_budget * (1 + multiplier))

        # Enforce maximum limit
        final_budget = min(final_budget, self.max_budget)

        return BudgetAllocation(
            base_budget=base_budget,
            complexity_multiplier=multiplier,
            final_budget=final_budget,
            severity=severity,
            complexity_score=complexity_score
        )

    def _calculate_complexity(
        self,
        incident_type: str,
        context_data: Optional[Dict[str, Any]]
    ) -> float:
        """
        Calculate incident complexity score (0.0 to 1.0).

        Factors:
        - Number of affected services (0.0 - 0.3)
        - Duration of incident (0.0 - 0.3)
        - Number of related alerts (0.0 - 0.2)
        - Data source diversity (0.0 - 0.2)
        """
        if not context_data:
            return 0.5  # Default medium complexity

        complexity = 0.0

        # Affected services (up to 0.3)
        services = set()
        if 'kubernetes_state' in context_data:
            for pod in context_data['kubernetes_state'].get('pods', []):
                services.add(pod.get('service_name', 'unknown'))
        if 'apm_data' in context_data:
            services.add(context_data['apm_data'].get('service_name', 'unknown'))

        service_complexity = min(len(services) * 0.1, 0.3)
        complexity += service_complexity

        # Duration (up to 0.3)
        duration_minutes = context_data.get('duration_minutes', 30)
        duration_complexity = min(duration_minutes / 120, 0.3)  # 2 hours = max
        complexity += duration_complexity

        # Related alerts (up to 0.2)
        alerts = context_data.get('alerts', [])
        alert_complexity = min(len(alerts) * 0.05, 0.2)
        complexity += alert_complexity

        # Data source diversity (up to 0.2)
        sources = sum(1 for k in ['logs', 'metrics', 'apm_data', 'kubernetes_state', 'alerts']
                      if k in context_data and context_data[k])
        source_complexity = min(sources * 0.04, 0.2)
        complexity += source_complexity

        return min(complexity, 1.0)

    def adjust_budget_for_performance(
        self,
        current_budget: int,
        processing_time_ms: float,
        target_time_ms: float = 100.0
    ) -> int:
        """
        Adjust budget based on performance.

        If processing is too slow, reduce budget for next time.

        Args:
            current_budget: Current budget
            processing_time_ms: Actual processing time
            target_time_ms: Target processing time

        Returns:
            Adjusted budget
        """
        if processing_time_ms <= target_time_ms:
            return current_budget  # No adjustment needed

        # Calculate ratio and reduce proportionally
        ratio = target_time_ms / processing_time_ms
        adjusted = int(current_budget * ratio)

        # Don't reduce below minimum
        min_budget = 500
        return max(adjusted, min_budget)


# Singleton instance
_budget_manager: Optional[TokenBudgetManager] = None


def get_token_budget_manager(config: Optional[Dict[str, Any]] = None) -> TokenBudgetManager:
    """Get or create the singleton TokenBudgetManager instance."""
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = TokenBudgetManager(config)
    return _budget_manager
