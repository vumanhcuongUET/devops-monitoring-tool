"""Prometheus instrumentation for LLM token usage.

Every Claude call site (triage, streaming, simple-stream, agents, health)
records request count and input/output tokens here, so spend is observable
per path and per model — the Phase 14 review found usage was previously
captured nowhere except one output-token field on TriageCard.
"""
from typing import Any

from prometheus_client import Counter

LLM_REQUESTS = Counter(
    # NOT "llm_requests_total": app/api/v1/metrics.py already exports that
    # series with labels [model, status]; registering the same name here
    # (different labels) raises prometheus_client DuplicateTimeseries at
    # import time. This counter is the by-path view; theirs is by-status.
    "llm_api_requests_total",
    "LLM API requests by call path and model",
    ["path", "model"],
)
LLM_INPUT_TOKENS = Counter(
    "llm_input_tokens_total",
    "Input (prompt) tokens consumed by LLM calls",
    ["path", "model"],
)
LLM_OUTPUT_TOKENS = Counter(
    "llm_output_tokens_total",
    "Output (completion) tokens consumed by LLM calls",
    ["path", "model"],
)


def _usage_field(usage: Any, name: str) -> int:
    """Pull an int field off a usage object/dict; 0 when absent."""
    if usage is None:
        return 0
    if isinstance(usage, dict):
        value = usage.get(name, 0)
    else:
        value = getattr(usage, name, 0)
    return int(value or 0)


def record_request(path: str, model: str) -> None:
    """Count one LLM API request."""
    LLM_REQUESTS.labels(path=path, model=model).inc()

def record_usage(path: str, model: str, usage: Any) -> None:
    """Record input/output tokens from an Anthropic usage object or dict.

    Tolerates None (call failed / usage never arrived) and missing fields —
    partial data still increments whatever counters it can.
    """
    input_tokens = _usage_field(usage, "input_tokens")
    output_tokens = _usage_field(usage, "output_tokens")
    if input_tokens:
        LLM_INPUT_TOKENS.labels(path=path, model=model).inc(input_tokens)
    if output_tokens:
        LLM_OUTPUT_TOKENS.labels(path=path, model=model).inc(output_tokens)
