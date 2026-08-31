"""Shared input-slimming helpers for LLM prompt construction.

Token-optimization (2026-08-31): log `message` fields are unbounded in
Elasticsearch — a single stack trace can carry more tokens than the rest of
the prompt combined — and several consumers (triage prompt builder,
simple-stream, log agent, alert dedupe) need the same cap. Kept dependency-
free so any app module can import it without cycles.
"""

import copy

# A log/alert message longer than this adds cost without adding signal: the
# exception name and the first stack frames are at the head.
LOG_MESSAGE_MAX_CHARS = 400
# Slightly tighter for alert bubbles — they are pre-processed summaries, and
# up to 10 groups ship per analysis.
ALERT_MESSAGE_MAX_CHARS = 300

_TRUNCATION_MARKER = " [truncated {} chars]"


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
    return max(1, len(text) // 4)
