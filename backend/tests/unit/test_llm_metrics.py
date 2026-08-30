"""Unit tests for app.llm_metrics — token usage recording."""

from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from app.llm_metrics import (
    LLM_INPUT_TOKENS,
    LLM_OUTPUT_TOKENS,
    LLM_REQUESTS,
    record_request,
    record_usage,
)


def _value(counter_name: str, path: str, model: str) -> float:
    return REGISTRY.get_sample_value(counter_name, {"path": path, "model": model}) or 0.0


@pytest.mark.unit
class TestRecordUsage:
    """record_usage must tolerate every shape real code can hand it."""

    def test_records_dict_usage(self):
        before_in = _value("llm_input_tokens_total", "triage", "m-dict")
        before_out = _value("llm_output_tokens_total", "triage", "m-dict")

        record_usage("triage", "m-dict", {"input_tokens": 100, "output_tokens": 50})

        assert _value("llm_input_tokens_total", "triage", "m-dict") == before_in + 100
        assert _value("llm_output_tokens_total", "triage", "m-dict") == before_out + 50

    def test_records_sdk_usage_object(self):
        usage = SimpleNamespace(input_tokens=7, output_tokens=3)
        before_in = _value("llm_input_tokens_total", "agents", "m-obj")

        record_usage("agents", "m-obj", usage)

        assert _value("llm_input_tokens_total", "agents", "m-obj") == before_in + 7
        assert _value("llm_output_tokens_total", "agents", "m-obj") >= 3

    def test_none_usage_is_a_no_op(self):
        before_in = _value("llm_input_tokens_total", "health", "m-none")
        before_out = _value("llm_output_tokens_total", "health", "m-none")

        record_usage("health", "m-none", None)

        assert _value("llm_input_tokens_total", "health", "m-none") == before_in
        assert _value("llm_output_tokens_total", "health", "m-none") == before_out

    def test_missing_fields_are_tolerated(self):
        record_usage("stream", "m-partial", {})

        assert _value("llm_input_tokens_total", "stream", "m-partial") == 0

    def test_none_and_zero_fields_do_not_increment(self):
        before_out = _value("llm_output_tokens_total", "stream", "m-zero")

        record_usage(
            "stream", "m-zero", {"input_tokens": None, "output_tokens": 0}
        )

        assert _value("llm_output_tokens_total", "stream", "m-zero") == before_out
        assert _value("llm_input_tokens_total", "stream", "m-zero") == 0

    def test_counters_are_labeled_by_path_and_model(self):
        record_usage("simple_stream", "m-labels", {"input_tokens": 10, "output_tokens": 5})

        # Same metric, different label set — independent series.
        assert _value("llm_input_tokens_total", "simple_stream", "m-labels") >= 10
        assert _value("llm_input_tokens_total", "triage", "m-labels") == 0


@pytest.mark.unit
class TestRecordRequest:
    def test_increments_request_counter(self):
        before = _value("llm_api_requests_total", "triage", "m-req")

        record_request("triage", "m-req")
        record_request("triage", "m-req")

        assert _value("llm_api_requests_total", "triage", "m-req") == before + 2

    def test_counter_families_exist_with_labels(self):
        # Guards against accidental rename/drift of the exported series:
        # prometheus_client strips the _total suffix internally and restores
        # it on exposition, so both forms must round-trip. The request
        # counter is llm_api_requests_* — llm_requests_total is already
        # exported by app/api/v1/metrics.py with a different label set.
        for counter, base in (
            (LLM_REQUESTS, "llm_api_requests"),
            (LLM_INPUT_TOKENS, "llm_input_tokens"),
            (LLM_OUTPUT_TOKENS, "llm_output_tokens"),
        ):
            assert counter._name == base
