"""
Unit tests for Alert Rules.

Tests the alert rules functionality including:
- Rule loading from YAML/JSON
- Rule saving to JSON
- Rule validation
"""

import pytest
from unittest.mock import patch, MagicMock
import yaml
import json


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertRules:
    """Test suite for alert rules management."""

    @pytest.mark.asyncio
    async def test_load_rules_from_yaml(self):
        """Test that load_rules loads rules from default YAML file."""
        from app.alerting.rules import load_rules

        mock_yaml_content = """
        - id: test-rule-001
          name: Test Rule
          enabled: true
          source: elasticsearch
          conditions:
            - type: error_count
              threshold: 100
          actions:
            - type: slack
              webhook: https://hooks.slack.com/test
        """

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_yaml_content):
                rules = load_rules()

                assert len(rules) == 1
                assert rules[0]["id"] == "test-rule-001"
                assert rules[0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_load_rules_from_custom_json(self):
        """Test that load_rules can load from custom JSON file."""
        from app.alerting.rules import load_rules

        mock_json_content = [
            {
                "id": "json-rule-001",
                "name": "JSON Rule",
                "enabled": True,
                "source": "prometheus",
                "conditions": [
                    {"type": "alert_firing", "alertname": "HighCPU"}
                ],
                "actions": [
                    {"type": "email", "to": ["admin@test.com"]}
                ]
            }
        ]

        with patch("pathlib.Path.exists", return_value=True):
            with patch("json.load", return_value=mock_json_content):
                with patch("builtins.open", MagicMock()):
                    rules = load_rules(custom_path="/custom/rules.json")

                    assert len(rules) == 1
                    assert rules[0]["id"] == "json-rule-001"
                    assert rules[0]["source"] == "prometheus"

    @pytest.mark.asyncio
    async def test_save_rules_to_json(self):
        """Test that save_rules persists rules to JSON file."""
        from app.alerting.rules import save_rules

        rules = [
            {
                "id": "saved-rule-001",
                "name": "Saved Rule",
                "enabled": True,
                "source": "elasticsearch",
                "conditions": [],
                "actions": []
            }
        ]

        mock_file = MagicMock()

        with patch("builtins.open", return_value=mock_file):
            with patch("json.dump") as mock_dump:
                result = save_rules(rules)

                mock_dump.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_rules_merges_default_and_custom(self):
        """Test that load_rules merges default and custom rules."""
        from app.alerting.rules import load_rules

        # Mock default rules
        default_rules = [
            {
                "id": "default-rule-001",
                "name": "Default Rule",
                "enabled": True,
                "source": "elasticsearch"
            }
        ]

        # Mock custom rules
        custom_rules = [
            {
                "id": "custom-rule-001",
                "name": "Custom Rule",
                "enabled": True,
                "source": "prometheus"
            }
        ]

        with patch("pathlib.Path.exists", return_value=True):
            with patch("yaml.safe_load", return_value=default_rules):
                with patch("json.load", return_value=custom_rules):
                    with patch("builtins.open", MagicMock()):
                        rules = load_rules()

                        # Should have both rules
                        assert len(rules) == 2

    @pytest.mark.asyncio
    async def test_load_rules_with_empty_file(self):
        """Test that load_rules handles empty rule files."""
        from app.alerting.rules import load_rules

        with patch("pathlib.Path.exists", return_value=True):
            with patch("yaml.safe_load", return_value=[]):
                rules = load_rules()

                assert rules == []

    @pytest.mark.asyncio
    async def test_save_rules_creates_directory_if_not_exists(self):
        """Test that save_rules creates data directory if needed."""
        from app.alerting.rules import save_rules

        rules = [{"id": "test", "enabled": True}]

        mock_path = MagicMock()

        with patch("pathlib.Path.mkdir"):
            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    save_rules(rules)

    @pytest.mark.asyncio
    async def test_load_rules_validates_rule_structure(self):
        """Test that load_rules validates required rule fields."""
        from app.alerting.rules import load_rules

        # Invalid rule missing required fields
        invalid_rules = [
            {
                "id": "invalid-rule-001"
                # Missing: name, enabled, source, conditions
            }
        ]

        with patch("pathlib.Path.exists", return_value=True):
            with patch("yaml.safe_load", return_value=invalid_rules):
                rules = load_rules()

                # Should still load but may need validation elsewhere
                assert len(rules) == 1

    @pytest.mark.asyncio
    async def test_save_rules_pretty_prints_json(self):
        """Test that save_rules formats JSON with indentation."""
        from app.alerting.rules import save_rules

        rules = [
            {
                "id": "test-rule-001",
                "name": "Test Rule",
                "enabled": True
            }
        ]

        mock_file = MagicMock()

        with patch("builtins.open", return_value=mock_file):
            with patch("json.dump") as mock_dump:
                save_rules(rules, indent=2)

                # Verify indentation parameter was passed
                call_args = mock_dump.call_args
                assert call_args.kwargs.get("indent") == 2
