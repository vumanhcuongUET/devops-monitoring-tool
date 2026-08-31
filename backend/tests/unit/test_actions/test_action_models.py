"""Unit tests for action request/response models (Phase 15 P2-4)."""

import pytest
from pydantic import ValidationError

from app.models.actions import ExecuteActionRequest


class TestExecuteActionRequestTimeout:
    """Phase 15 P2-4: the engine used to hardcode a 30s subprocess timeout —
    helm upgrades (est. 45s) were guaranteed killed. timeout_seconds is now a
    caller-visible field, bounded so a request can't pin the executor."""

    def test_default_is_120(self):
        req = ExecuteActionRequest(executed_by="op")
        assert req.timeout_seconds == 120

    def test_accepts_helm_upgrade_window(self):
        req = ExecuteActionRequest(executed_by="op", timeout_seconds=300)
        assert req.timeout_seconds == 300

    @pytest.mark.parametrize("value", [9, 0, -5])
    def test_below_minimum_rejected(self, value):
        with pytest.raises(ValidationError):
            ExecuteActionRequest(executed_by="op", timeout_seconds=value)

    @pytest.mark.parametrize("value", [601, 100000])
    def test_above_maximum_rejected(self, value):
        with pytest.raises(ValidationError):
            ExecuteActionRequest(executed_by="op", timeout_seconds=value)

    def test_string_coerced(self):
        req = ExecuteActionRequest(executed_by="op", timeout_seconds="240")
        assert req.timeout_seconds == 240
