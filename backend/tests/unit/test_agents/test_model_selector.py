"""
Unit tests for the ModelSelector (Phase 10 Sprint 3).

Covers complexity scoring, tier selection (fast/balanced/capable),
cost-limit-driven selection, task-type mapping and cost estimation.
"""

import pytest

from app.agents.model_selector import ModelSelector


@pytest.fixture
def selector() -> ModelSelector:
    return ModelSelector()


@pytest.mark.unit
class TestComplexityScoring:
    """_calculate_complexity produces bounded 0-1 scores."""

    def test_empty_context_scores_zero(self, selector):
        assert selector._calculate_complexity({}) == 0.0

    def test_score_clamped_to_one(self, selector):
        context = {
            "logs": [{"m": i} for i in range(2000)],  # +0.4
            "metrics": {f"m{i}": i for i in range(100)},  # +0.2
            **{f"source_{i}": [1] for i in range(10)},  # +0.3
            "requires_deep_analysis": True,  # +0.2
            "multi_hop_reasoning": True,  # +0.15
            "complex_correlation": True,  # +0.15
            "cost_critical": True,  # -0.2
        }
        assert selector._calculate_complexity(context) == 1.0

    def test_cost_critical_lowers_score(self, selector):
        base = {"metrics": {f"m{i}": i for i in range(20)}}
        critical = {**base, "cost_critical": True}

        assert (
            selector._calculate_complexity(critical)
            < selector._calculate_complexity(base)
        )

    def test_negative_score_clamps_to_zero(self, selector):
        assert selector._calculate_complexity({"cost_critical": True}) == 0.0


@pytest.mark.unit
class TestTierSelection:
    """Context complexity maps onto fast/balanced/capable tiers."""

    def test_simple_context_selects_fast_model(self, selector):
        model = selector.select_model({"logs": [{"m": "hello"}]})
        assert model == ModelSelector.MODELS["fast"]

    def test_medium_context_selects_balanced_model(self, selector):
        context = {
            "logs": [{"m": str(i)} for i in range(50)],  # +0.1 volume
            "extra_source": [1, 2],  # sources contribution
        }
        # sources=2 -> +0.3 -> total 0.4 => balanced
        model = selector.select_model(context)
        assert model == ModelSelector.MODELS["balanced"]

    def test_complex_context_selects_capable_model(self, selector):
        context = {
            "logs": [{"m": str(i)} for i in range(2000)],  # +0.4
            "requires_deep_analysis": True,  # +0.2
            "multi_hop_reasoning": True,  # +0.15
            "complex_correlation": True,  # +0.15
        }
        model = selector.select_model(context)
        assert model == ModelSelector.MODELS["capable"]

    def test_usage_stats_track_selections(self, selector):
        simple = {"logs": [{"m": "hi"}]}
        selector.select_model(simple)
        selector.select_model(simple)

        stats = selector.get_usage_stats()
        assert stats == {"fast": 2}


@pytest.mark.unit
class TestCostLimitSelection:
    """Tight budgets force cheaper tiers regardless of complexity."""

    def test_tight_budget_downgrades_complex_context_to_fast(self):
        tight = ModelSelector(cost_limit=0.05)
        complex_context = {
            "logs": [{"message": f"log entry number {i}"} for i in range(500)]
        }

        model = tight.select_model(complex_context)

        # Cost-based path picks the cheapest tier that fits the budget;
        # complexity alone would have stopped at balanced.
        complexity_pick = ModelSelector().select_model(complex_context)
        assert complexity_pick == ModelSelector.MODELS["balanced"]
        assert model == ModelSelector.MODELS["fast"]

    def test_budget_picks_cheapest_fitting_tier(self):
        selector = ModelSelector(cost_limit=1.50)
        small_context = {"security_data": {"findings": [1]}}

        model = selector.select_model(small_context)

        # All tiers fit a tiny context; the cost path walks
        # fast -> balanced -> capable and takes the first fit.
        assert model == ModelSelector.MODELS["fast"]

    def test_impossibly_low_budget_falls_back_to_complexity(self):
        selector = ModelSelector(cost_limit=0.00000001)
        simple_context = {"logs": []}

        model = selector.select_model(simple_context)

        # No tier fits -> cost selection returns None -> complexity path (fast)
        assert model == ModelSelector.MODELS["fast"]


@pytest.mark.unit
class TestTaskMapping:
    """get_model_for_task resolves known task types."""

    @pytest.mark.parametrize(
        "task_type,expected_tier",
        [
            ("status_check", "fast"),
            ("pattern_detection", "fast"),
            ("root_cause_analysis", "balanced"),
            ("log_analysis", "balanced"),
            ("security_audit", "capable"),
            ("complex_reasoning", "capable"),
        ],
    )
    def test_known_task_types(self, selector, task_type, expected_tier):
        assert (
            selector.get_model_for_task(task_type)
            == ModelSelector.MODELS[expected_tier]
        )

    def test_unknown_task_uses_default(self, selector):
        default = ModelSelector(default_model="balanced")
        assert (
            default.get_model_for_task("nonexistent_task")
            == ModelSelector.MODELS["balanced"]
        )


@pytest.mark.unit
class TestCostEstimation:
    """estimate_cost returns per-model projections."""

    def test_estimate_cost_scales_with_tier(self, selector):
        context = {"logs": [{"message": "x" * 400}] * 10}  # ~1000 tokens

        fast_cost = selector.estimate_cost(
            context, ModelSelector.MODELS["fast"]
        )
        capable_cost = selector.estimate_cost(
            context, ModelSelector.MODELS["capable"]
        )

        assert capable_cost["total_cost"] > fast_cost["total_cost"] > 0

    def test_estimate_cost_structure(self, selector):
        result = selector.estimate_cost({"logs": ["abc"]}, ModelSelector.MODELS["fast"])

        assert set(result.keys()) == {
            "input_tokens",
            "output_tokens",
            "input_cost",
            "output_cost",
            "total_cost",
        }
        # Output assumes a 1:10 input:output token ratio
        assert result["output_tokens"] == result["input_tokens"] // 10
        assert result["total_cost"] == pytest.approx(
            result["input_cost"] + result["output_cost"]
        )

    def test_unknown_model_raises(self, selector):
        with pytest.raises(ValueError, match="Unknown model"):
            selector.estimate_cost({}, "gpt-4")
