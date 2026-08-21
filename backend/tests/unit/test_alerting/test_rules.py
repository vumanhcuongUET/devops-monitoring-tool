"""
Unit tests for Alert Rules.

Tests the alert rules functionality including:
- Rule loading from YAML/JSON
- Rule saving to JSON
- Rule validation
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock

from app.alerting.rules import load_rules, save_rules, DEFAULT_RULES_FILE, RULES_FILE
from app.models.alerts import AlertRule, AlertSeverity


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertRules:
    """Test suite for alert rules management."""

    def test_load_rules_from_default_yaml(self):
        """Test that load_rules loads rules from default YAML file."""
        # Mock default YAML file
        mock_yaml_data = {
            "rules": [
                {
                    "id": "test-rule-001",
                    "name": "Test Rule",
                    "enabled": True,
                    "source": "elasticsearch",
                    "metric": "error_count",
                    "condition": "gt",
                    "threshold": 100.0,
                    "duration_seconds": 300,
                    "severity": "warning"
                }
            ]
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch("yaml.safe_load", return_value=mock_yaml_data):
                rules = load_rules()

                assert len(rules) == 1
                assert rules[0].id == "test-rule-001"
                assert rules[0].name == "Test Rule"
                assert rules[0].source == "elasticsearch"
                assert isinstance(rules[0], AlertRule)

    def test_load_rules_from_custom_json(self):
        """Test that load_rules loads from JSON file when it exists."""
        mock_json_rules = [
            {
                "id": "json-rule-001",
                "name": "JSON Rule",
                "enabled": True,
                "source": "prometheus",
                "metric": "cpu_usage",
                "condition": "gt",
                "threshold": 80.0,
                "severity": "warning"
            }
        ]

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=mock_json_rules):
                    rules = load_rules()

                    assert len(rules) == 1
                    assert rules[0].id == "json-rule-001"
                    assert rules[0].source == "prometheus"

    def test_save_rules_to_json(self):
        """Test that save_rules persists rules to JSON file."""
        rules = [
            AlertRule(
                id="saved-rule-001",
                name="Saved Rule",
                enabled=True,
                source="elasticsearch",
                metric="error_count",
                condition="gt",
                threshold=50.0
            )
        ]

        with patch("os.makedirs"):
            with patch("builtins.open", MagicMock()):
                with patch("json.dump") as mock_dump:
                    save_rules(rules)

                    # Verify json.dump was called
                    mock_dump.assert_called_once()
                    # Check that rules were converted to dicts
                    call_args = mock_dump.call_args
                    dumped_rules = call_args[0][0]
                    assert len(dumped_rules) == 1
                    assert dumped_rules[0]["id"] == "saved-rule-001"

    def test_load_rules_with_empty_file(self):
        """Test that load_rules returns empty list when no rules file."""
        with patch("os.path.exists", return_value=False):
            with patch("pathlib.Path.exists", return_value=False):
                rules = load_rules()

                assert rules == []

    def test_save_rules_creates_directory_if_not_exists(self):
        """Test that save_rules creates data directory if needed."""
        rules = [
            AlertRule(id="test", name="Test", enabled=True, source="elasticsearch")
        ]

        with patch("os.makedirs") as mock_makedirs:
            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    save_rules(rules)

                    # Verify directory creation was attempted
                    mock_makedirs.assert_called_once()

    def test_save_rules_uses_model_dump(self):
        """Test that save_rules uses model_dump for Pydantic v2."""
        rules = [
            AlertRule(
                id="test-rule-001",
                name="Test Rule",
                enabled=True,
                source="prometheus",
                metric="cpu",
                condition="gt",
                threshold=90.0,
                severity=AlertSeverity.CRITICAL
            )
        ]

        with patch("os.makedirs"):
            with patch("builtins.open", MagicMock()):
                with patch("json.dump") as mock_dump:
                    save_rules(rules)

                    # Verify json.dump was called with dict representation
                    call_args = mock_dump.call_args
                    dumped_rules = call_args[0][0]
                    assert isinstance(dumped_rules, list)
                    assert isinstance(dumped_rules[0], dict)
                    assert dumped_rules[0]["severity"] == AlertSeverity.CRITICAL

    def test_alert_rule_model_defaults(self):
        """Test AlertRule model has correct defaults."""
        rule = AlertRule(id="test")

        assert rule.id == "test"
        assert rule.enabled is True
        assert rule.condition == "gt"
        assert rule.duration_seconds == 60
        assert rule.severity == AlertSeverity.WARNING
        assert rule.notify_slack is True
        assert rule.notify_email is False
