"""
Tests for feature flags system.
"""

import pytest
from pathlib import Path
import yaml
import tempfile
import os

from core.config_loader import (
    load_feature_flags,
    get_feature_flags,
    is_feature_enabled,
    reload_feature_flags
)


@pytest.mark.unit
class TestFeatureFlags:
    """Tests for feature flag loading and checking."""

    def test_load_feature_flags_returns_dict(self):
        """Test that feature flags returns a dictionary."""
        flags = load_feature_flags()
        assert isinstance(flags, dict)

    def test_load_feature_flags_has_top_level_keys(self):
        """Test that feature flags has expected top-level keys."""
        flags = load_feature_flags()
        expected_keys = ["optimization", "output", "query", "monitoring"]
        for key in expected_keys:
            assert key in flags

    def test_get_feature_flags_is_cached(self):
        """Test that get_feature_flags caches results."""
        # First call
        flags1 = get_feature_flags()
        # Second call should return same object (cached)
        flags2 = get_feature_flags()
        assert flags1 is flags2

    def test_is_feature_enabled_query_flag(self):
        """Test checking query.validate_time_range flag."""
        enabled = is_feature_enabled("query.validate_time_range")
        assert isinstance(enabled, bool)

    def test_is_feature_enabled_nested_path(self):
        """Test checking nested feature paths."""
        # Test optimization.cache_enabled (should be True by default)
        enabled = is_feature_enabled("optimization.cache_enabled")
        assert enabled is True

    def test_is_feature_enabled_nonexistent_path(self):
        """Test that nonexistent paths return False."""
        enabled = is_feature_enabled("nonexistent.feature")
        assert enabled is False

    def test_is_feature_enabled_invalid_path(self):
        """Test that invalid intermediate paths return False."""
        enabled = is_feature_enabled("optimization.nonexistent.enabled")
        assert enabled is False

    def test_reload_feature_flags(self, tmp_path, monkeypatch):
        """Test that reload_feature_flags reloads from disk."""
        # Create temporary features file
        features_file = tmp_path / "features.yaml"
        features_file.write_text(yaml.dump({
            "optimization": {"cache_enabled": False},
            "output": {"use_emoji": False}
        }))

        # Create config subdirectory and move file there
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "features.yaml").write_text(features_file.read_text())

        # Monkeypatch ROOT to point to tmp_path
        import core.config_loader
        monkeypatch.setattr(core.config_loader, "ROOT", tmp_path)

        # Clear cache first
        monkeypatch.setattr(core.config_loader, "_FEATURE_FLAGS_CACHE", None)

        # Reload and check
        flags = reload_feature_flags()
        assert flags["optimization"]["cache_enabled"] is False
        assert flags["output"]["use_emoji"] is False

    def test_feature_flags_default_values(self):
        """Test that default values are set correctly."""
        flags = load_feature_flags()

        # Optimization should be enabled by default
        assert flags["optimization"]["cache_enabled"] is True
        assert flags["optimization"]["deduplication_enabled"] is True
        assert flags["optimization"]["parallel_queries"] is True

        # Output features
        assert flags["output"]["use_emoji"] is True
        assert flags["output"]["truncate_results"] is True

    def test_is_feature_enabled_optimization_flags(self):
        """Test checking all optimization feature flags."""
        paths = [
            "optimization.cache_enabled",
            "optimization.deduplication_enabled",
            "optimization.parallel_queries",
            "output.optimization_enabled",
            "query.enforce_timeout",
        ]
        for path in paths:
            enabled = is_feature_enabled(path)
            assert isinstance(enabled, bool)
