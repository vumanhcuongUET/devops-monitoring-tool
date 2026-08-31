"""Token-optimization (2026-08-31): shared input-slimming helpers."""

from app.services.llm_input import (
    ALERT_MESSAGE_MAX_CHARS,
    LOG_MESSAGE_MAX_CHARS,
    dedupe_alerts,
    estimate_tokens,
    truncate_log_messages,
    truncate_text,
)


class TestTruncateText:
    def test_short_text_passes_through(self):
        assert truncate_text("boom", 400) == "boom"

    def test_long_message_keeps_head_and_marks_omission(self):
        message = "E" * 1000
        result = truncate_text(message, 400)

        assert result.startswith("E" * 400)
        assert "[truncated 600 chars]" in result
        assert len(result) < 450

    def test_custom_limit(self):
        assert truncate_text("a" * 10, 5) == "aaaaa [truncated 5 chars]"


class TestTruncateLogMessages:
    def test_caps_oversized_message_only(self):
        logs = [
            {"level": "ERROR", "message": "short"},
            {"level": "ERROR", "message": "x" * 1000},
        ]
        kept, truncated = truncate_log_messages(logs)

        assert truncated == 1
        assert kept[0] == logs[0]  # untouched
        assert "[truncated" in kept[1]["message"]
        assert logs[1]["message"] == "x" * 1000  # original not mutated

    def test_non_dict_and_messageless_entries_pass_through(self):
        logs = ["raw-string", {"level": "ERROR"}, {"message": 42}]
        kept, truncated = truncate_log_messages(logs)

        assert truncated == 0
        assert kept == logs

    def test_empty_and_none_inputs(self):
        assert truncate_log_messages([]) == ([], 0)
        assert truncate_log_messages(None) == ([], 0)

    def test_prompt_budget_note_counts(self):
        logs = [{"message": "y" * (LOG_MESSAGE_MAX_CHARS + 10)} for _ in range(3)]
        _, truncated = truncate_log_messages(logs)
        assert truncated == 3


class TestDedupeAlerts:
    def _alert(self, rule, severity="critical", message="m", ts="2026-08-31T00:00:00Z"):
        return {
            "rule_name": rule,
            "severity": severity,
            "status": "firing",
            "message": message,
            "timestamp": ts,
        }

    def test_storm_collapses_to_groups_with_counts(self):
        alerts = [self._alert("OOMKilled", message=f"pod-{i}") for i in range(17)]
        alerts.append(self._alert("HighLatency", severity="warning"))

        deduped = dedupe_alerts(alerts)

        assert len(deduped) == 2
        assert deduped[0]["occurrences"] == 17
        assert deduped[1]["occurrences"] == 1

    def test_latest_message_and_timestamp_win(self):
        alerts = [
            self._alert("OOMKilled", message="first", ts="2026-08-31T00:00:00Z"),
            self._alert("OOMKilled", message="last", ts="2026-08-31T01:00:00Z"),
        ]

        deduped = dedupe_alerts(alerts)

        assert deduped[0]["message"] == "last"
        assert deduped[0]["timestamp"] == "2026-08-31T01:00:00Z"

    def test_messages_are_truncated(self):
        alerts = [self._alert("R", message="z" * (ALERT_MESSAGE_MAX_CHARS + 100))]

        deduped = dedupe_alerts(alerts)

        assert len(deduped[0]["message"]) < ALERT_MESSAGE_MAX_CHARS + 40
        assert "[truncated" in deduped[0]["message"]

    def test_max_groups_cap_keeps_first_seen(self):
        alerts = [self._alert(f"rule-{i}") for i in range(15)]

        deduped = dedupe_alerts(alerts, max_groups=10)

        assert len(deduped) == 10
        assert deduped[0]["rule_name"] == "rule-0"
        assert deduped[-1]["rule_name"] == "rule-9"

    def test_same_rule_different_severity_stay_separate(self):
        alerts = [
            self._alert("CPU", severity="warning"),
            self._alert("CPU", severity="critical"),
        ]

        deduped = dedupe_alerts(alerts)

        assert len(deduped) == 2


class TestEstimateTokens:
    def test_rough_ratio(self):
        assert estimate_tokens("a" * 400) == 100

    def test_empty(self):
        assert estimate_tokens("") == 0
