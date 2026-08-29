"""
Model Selector

Dynamically selects the optimal Claude model based on query complexity
and cost constraints.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ModelSelector:
    """
    Selects the optimal Claude model based on query complexity and cost.

    Models:
    - Haiku: Fast, cheap - simple queries
    - Sonnet: Balanced - most queries
    - Opus: Capable - complex queries requiring deep analysis
    """

    MODELS = {
        "fast": "claude-haiku-4-20250101",      # Fast, cheap
        "balanced": "claude-sonnet-4-20250514",  # Balanced
        "capable": "claude-opus-4-20250514"      # Most capable
    }

    # Cost per million tokens (input)
    COST_PER_INPUT = {
        "fast": 0.25,      # $0.25/M tokens
        "balanced": 3.0,   # $3.00/M tokens
        "capable": 15.0    # $15.00/M tokens
    }

    # Cost per million tokens (output)
    COST_PER_OUTPUT = {
        "fast": 1.25,
        "balanced": 15.0,
        "capable": 75.0
    }

    # Model capabilities
    MODEL_CAPABILITIES = {
        "fast": {
            "max_tokens": 200000,
            "context_window": 200000,
            "best_for": ["simple_analysis", "pattern_matching", "classification"],
        },
        "balanced": {
            "max_tokens": 200000,
            "context_window": 200000,
            "best_for": ["general_analysis", "trend_detection", "recommendations"],
        },
        "capable": {
            "max_tokens": 200000,
            "context_window": 200000,
            "best_for": ["complex_reasoning", "multi_hop_analysis", "creative_tasks"],
        },
    }

    def __init__(
        self,
        default_model: str = "balanced",
        cost_limit: float | None = None,
    ):
        """
        Initialize model selector.

        Args:
            default_model: Default model tier to use
            cost_limit: Maximum cost per query in USD
        """
        self.default_model = default_model
        self.cost_limit = cost_limit
        self._usage_stats: dict[str, int] = {}

    def select_model(
        self,
        context: dict[str, Any],
        task_type: str | None = None,
    ) -> str:
        """
        Select model based on query complexity and context.

        Args:
            context: Analysis context (logs, metrics, etc.)
            task_type: Specific task type if known

        Returns:
            Selected model name
        """
        # Check for explicit cost constraints
        if self.cost_limit:
            model = self._select_by_cost(context)
            if model:
                return self.MODELS[model]

        # Calculate complexity score
        complexity_score = self._calculate_complexity(context)

        # Select based on complexity
        if complexity_score < 0.3:
            model = "fast"
        elif complexity_score < 0.7:
            model = "balanced"
        else:
            model = "capable"

        # Track usage
        self._usage_stats[model] = self._usage_stats.get(model, 0) + 1

        return self.MODELS[model]

    def _calculate_complexity(self, context: dict[str, Any]) -> float:
        """
        Calculate complexity score (0.0 to 1.0).

        Factors:
        - Data volume (logs, metrics entries)
        - Number of data sources
        - Special requirements (deep analysis, multi-hop)
        - Task complexity indicators
        """
        score = 0.0

        # Data volume
        log_count = len(context.get("logs", []))
        if log_count > 1000:
            score += 0.4
        elif log_count > 100:
            score += 0.2
        elif log_count > 10:
            score += 0.1

        metrics_count = len(context.get("metrics", {}))
        if metrics_count > 50:
            score += 0.2
        elif metrics_count > 10:
            score += 0.1

        # Number of data sources
        sources = sum(
            1
            for v in context.values()
            if v and isinstance(v, (list, dict)) and len(v) > 0
        )
        score += min(sources * 0.15, 0.3)

        # Special requirements
        if context.get("requires_deep_analysis"):
            score += 0.2
        if context.get("multi_hop_reasoning"):
            score += 0.15
        if context.get("complex_correlation"):
            score += 0.15

        # Cost sensitivity (lower score for cost-critical queries)
        if context.get("cost_critical"):
            score -= 0.2

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def _select_by_cost(self, context: dict[str, Any]) -> str | None:
        """Select model based on cost limit."""
        # Estimate token count
        estimated_tokens = self._estimate_tokens(context)

        # Check each model
        for tier in ["fast", "balanced", "capable"]:
            model = self.MODELS[tier]
            input_cost = (estimated_tokens / 1_000_000) * self.COST_PER_INPUT[tier]
            output_cost = (
                (estimated_tokens / 10 / 1_000_000) * self.COST_PER_OUTPUT[tier]
            )  # Assume 1:10 input:output ratio
            total_cost = input_cost + output_cost

            if total_cost <= self.cost_limit:
                return tier

        # If even fast is too expensive, return None
        logger.warning(
            f"Cost limit {self.cost_limit} too low for estimated {estimated_tokens} tokens"
        )
        return None

    def _estimate_tokens(self, context: dict[str, Any]) -> int:
        """Estimate token count for the context."""
        # Rough estimation: 1 token ≈ 4 characters
        total_chars = 0

        for value in context.values():
            if isinstance(value, str):
                total_chars += len(value)
            elif isinstance(value, list):
                total_chars += sum(len(str(v)) for v in value)
            elif isinstance(value, dict):
                total_chars += len(str(value))

        return total_chars // 4

    def get_model_for_task(self, task_type: str) -> str:
        """Get recommended model for specific task type."""
        task_mappings = {
            # Fast model suitable
            "simple_classification": "fast",
            "pattern_detection": "fast",
            "log_filtering": "fast",
            "status_check": "fast",
            # Balanced model suitable
            "log_analysis": "balanced",
            "metrics_analysis": "balanced",
            "trend_detection": "balanced",
            "capacity_planning": "balanced",
            "root_cause_analysis": "balanced",
            # Capable model suitable
            "complex_reasoning": "capable",
            "multi_system_analysis": "capable",
            "security_audit": "capable",
            "architecture_review": "capable",
            "optimization_strategy": "capable",
        }

        tier = task_mappings.get(task_type, self.default_model)
        return self.MODELS[tier]

    def estimate_cost(self, context: dict[str, Any], model: str) -> dict[str, float]:
        """Estimate cost for running analysis with specific model."""
        # Find model tier
        tier = None
        for t, m in self.MODELS.items():
            if m == model:
                tier = t
                break

        if not tier:
            raise ValueError(f"Unknown model: {model}")

        estimated_tokens = self._estimate_tokens(context)
        estimated_output = estimated_tokens // 10  # Assume 1:10 ratio

        input_cost = (estimated_tokens / 1_000_000) * self.COST_PER_INPUT[tier]
        output_cost = (estimated_output / 1_000_000) * self.COST_PER_OUTPUT[tier]

        return {
            "input_tokens": estimated_tokens,
            "output_tokens": estimated_output,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": input_cost + output_cost,
        }

    def get_usage_stats(self) -> dict[str, int]:
        """Get model usage statistics."""
        return self._usage_stats.copy()
