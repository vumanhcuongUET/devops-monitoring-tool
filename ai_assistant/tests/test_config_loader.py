"""
Tests for config_loader module.
"""

import pytest
from core.config_loader import (
    load_config,
    load_query_def,
    load_feature_flags,
    render_template
)


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_config_with_valid_project(self, sample_config):
        """Test loading config for existing project."""
        # This test assumes meinvoice project exists
        config = load_config("meinvoice")

        assert "project" in config
        assert "query_vars" in config
        assert "sources" in config

    def test_load_config_nonexistent_project(self):
        """Test loading config for non-existent project."""
        # Should return minimal config with global defaults
        config = load_config("nonexistent_project")

        assert config["project"] == "nonexistent_project"

    def test_load_config_merges_sources(self):
        """Test that project config merges with global config."""
        config = load_config("meinvoice")

        # Should have sources (merged from global + project)
        assert "sources" in config
        # Should have query vars (merged from defaults + project)
        assert "query_vars" in config


class TestLoadQueryDef:
    """Tests for query definition loading."""

    def test_load_query_def_from_common(self):
        """Test loading common query definition."""
        query_def = load_query_def("meinvoice", "alerts")

        assert "type" in query_def
        assert "source_types" in query_def

    def test_load_query_def_nonexistent_section(self):
        """Test loading non-existent query definition."""
        with pytest.raises(FileNotFoundError):
            load_query_def("meinvoice", "nonexistent_section")


class TestLoadFeatureFlags:
    """Tests for feature flags loading."""

    def test_load_feature_flags(self):
        """Test loading feature flags."""
        flags = load_feature_flags()

        # Should always return a dict, even if file doesn't exist
        assert isinstance(flags, dict)
        # Should have optimization key
        assert "optimization" in flags or flags == {}


class TestRenderTemplate:
    """Tests for template rendering."""

    def test_render_template_basic(self):
        """Test basic placeholder replacement."""
        template = "Hello {{ name }}"
        result = render_template(template, {"name": "World"})

        assert result == "Hello World"

    def test_render_template_multiple_placeholders(self):
        """Test multiple placeholder replacement."""
        template = "{{ greeting }} {{ name }}, {{ greeting }}!"
        result = render_template(
            template,
            {"greeting": "Hello", "name": "Claude"}
        )

        assert result == "Hello Claude, Hello!"

    def test_render_template_missing_key_raises(self):
        """Phase 15 P2-13: a missing key used to render as empty string,
        silently dropping query filters (data-widening). It now raises."""
        template = "Value is {{ missing_key }}"

        with pytest.raises(KeyError, match="missing_key"):
            render_template(template, {})

    def test_render_template_explicit_empty_still_renders_empty(self):
        """An explicitly provided empty value is an intentional opt-out."""
        template = '"filter": [{{ project_filter }}]'
        result = render_template(template, {"project_filter": ""})

        assert result == '"filter": []'

    def test_render_template_none_value(self):
        """Test that None values become empty string."""
        template = "Value is {{ value }}"
        result = render_template(template, {"value": None})

        assert result == "Value is "

    def test_render_template_names_all_missing_keys(self):
        """The error lists every missing placeholder at once."""
        template = "{{ alpha }} {{ beta }} {{ alpha }}"

        with pytest.raises(KeyError, match="alpha.*beta") as exc_info:
            render_template(template, {})
        assert "beta" in str(exc_info.value)

    def test_render_template_preserves_literal(self):
        """Test that literal text is preserved."""
        template = "Prefix {{ key }} Suffix"
        result = render_template(template, {"key": "REPLACED"})

        assert result == "Prefix REPLACED Suffix"
