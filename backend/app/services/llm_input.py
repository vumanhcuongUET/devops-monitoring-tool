"""Shared input-slimming helpers for LLM prompt construction.

Token-optimization (2026-08-31): log `message` fields are unbounded in
Elasticsearch — a single stack trace can carry more tokens than the rest of
the prompt combined — and several consumers (triage prompt builder,
simple-stream, log agent, alert dedupe) need the same cap. Kept dependency-
free so any app module can import it without cycles.
"""

import copy
from typing import Any

# A log/alert message longer than this adds cost without adding signal: the
# exception name and the first stack frames are at the head.
LOG_MESSAGE_MAX_CHARS = 400
# Slightly tighter for alert bubbles — they are pre-processed summaries, and
# up to 10 groups ship per analysis.
ALERT_MESSAGE_MAX_CHARS = 300

_TRUNCATION_MARKER = " [truncated {} chars]"

# Per-severity keep quotas applied when a log payload is too large to ship
# wholesale. Sum = 30 logs max. Quotas only kick in above LOG_QUOTA_TRIGGER.
LOG_SEVERITY_QUOTAS: dict[str, int] = {
    "critical": 5,
    "error": 10,
    "warning": 10,
    "info": 5,
}
LOG_QUOTA_TRIGGER = 50

_LEVEL_TO_BUCKET = {
    "critical": "critical",
    "fatal": "critical",
    "alert": "critical",
    "emerg": "critical",
    "error": "error",
    "err": "error",
    "warn": "warning",
    "warning": "warning",
    # everything else (info/debug/trace/missing) lands in the info bucket
}


def _bucket_for_log(log: Any) -> str:
    """Map a log entry to its severity bucket (default: info)."""
    if not isinstance(log, dict):
        return "info"
    level = str(log.get("level", "")).lower().strip()
    return _LEVEL_TO_BUCKET.get(level, "info")


def sample_logs_by_severity(
    logs: list[Any],
    quotas: dict[str, int] | None = None,
    trigger: int = LOG_QUOTA_TRIGGER,
) -> tuple[list[Any], str | None]:
    """Sample oversized log lists by severity quotas.

    Replaces the old blunt ``logs[:50]`` cut, which starved the model of
    critical entries while flooding it with info noise. When more than
    ``trigger`` logs arrive, keep at most ``quotas`` entries per severity
    bucket (most recent first — ES returns desc-by-timestamp) and drop the
    rest. Original relative order is preserved.

    Returns:
        (kept_logs, note) where note is None when no sampling was applied,
        else a human-readable summary to embed in the prompt.
    """
    quotas = quotas if quotas is not None else LOG_SEVERITY_QUOTAS
    logs = list(logs or [])
    if len(logs) <= trigger:
        return logs, None

    seen: dict[str, int] = {bucket: 0 for bucket in ("critical", "error", "warning", "info")}
    kept: dict[str, int] = {bucket: 0 for bucket in seen}
    sampled: list[Any] = []

    for log in logs:
        bucket = _bucket_for_log(log)
        seen[bucket] += 1
        if kept[bucket] < quotas.get(bucket, 0):
            sampled.append(log)
            kept[bucket] += 1

    breakdown = ", ".join(f"{b} {kept[b]}/{seen[b]}" for b in seen)
    note = f"showing {len(sampled)} of {len(logs)} logs by severity ({breakdown})"
    return sampled, note


def truncate_text(message: str, max_chars: int = LOG_MESSAGE_MAX_CHARS) -> str:
    """Cap a single message, keeping the head and marking the omission."""
    text = str(message)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + _TRUNCATION_MARKER.format(len(text) - max_chars)


def truncate_log_messages(
    logs: list,
    max_chars: int = LOG_MESSAGE_MAX_CHARS,
) -> tuple[list, int]:
    """Return a copy of `logs` with over-long `message` fields capped.

    Non-dict entries and entries without a string `message` pass through
    untouched. Returns (logs, number_truncated) so callers can surface the
    omission in their sampling note.
    """
    if not logs:
        return list(logs or []), 0

    result = []
    truncated = 0
    for entry in logs:
        if isinstance(entry, dict) and isinstance(entry.get("message"), str):
            if len(entry["message"]) > max_chars:
                entry = dict(entry)
                entry["message"] = truncate_text(entry["message"], max_chars)
                truncated += 1
        result.append(entry)
    return result, truncated


def dedupe_alerts(
    alerts: list[dict],
    max_groups: int = 10,
    message_max_chars: int = ALERT_MESSAGE_MAX_CHARS,
) -> list[dict]:
    """Collapse alert storms to one entry per (rule_name, severity).

    During an incident a single rule can fire dozens of times; shipping all
    of them repeats the same payload. Each group keeps the first entry's
    position, the latest message/timestamp, and an `occurrences` count.
    Order of first appearance is preserved; at most `max_groups` ship.
    """
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for alert in alerts or []:
        if not isinstance(alert, dict):
            continue
        key = (alert.get("rule_name"), alert.get("severity"))
        if key not in groups:
            entry = copy.deepcopy(alert)
            entry["occurrences"] = 1
            groups[key] = entry
            order.append(key)
        else:
            entry = groups[key]
            entry["occurrences"] += 1
            # Alerts are iterated in history order — the last one seen is
            # the most recent state of the rule.
            for field in ("message", "timestamp", "status"):
                if alert.get(field) is not None:
                    entry[field] = alert[field]

    deduped = [groups[key] for key in order[:max_groups]]
    for entry in deduped:
        message = entry.get("message")
        if isinstance(message, str):
            entry["message"] = truncate_text(message, message_max_chars)
    return deduped


def estimate_tokens(text: str) -> int:
    """Cheap input-token estimate (~4 chars/token) for budget guarding.

    Deliberately not a tokenizer: this runs on every triage request and only
    needs to catch grossly oversized prompts.
    """
    if not text:
        return 0
    # chars//3, not //4: JSON-dense and Vietnamese-diacritic text runs
    # denser than 4 chars/token, so //4 systematically underestimates and
    # lets oversized prompts through the budget guard.
    return max(1, len(text) // 3)


def slim_context(context: dict, quotas: dict[str, int] | None = None) -> dict:
    """Best-effort slimming for ad-hoc context blobs sent to the model.

    The known key is `logs` (the shared `_collect_context_data` shape):
    severity sampling + per-message truncation apply. Everything else passes
    through untouched — shapes vary by caller and the model needs them.
    Returns a new dict; the caller's context is never mutated.
    """
    if not isinstance(context, dict):
        return context

    result = dict(context)
    logs = result.get("logs")
    if isinstance(logs, list):
        sampled, _note = sample_logs_by_severity(logs, quotas=quotas)
        sampled, _truncated = truncate_log_messages(sampled)
        result["logs"] = sampled
    return result
