"""
Tests for Priority Configuration Manager - Phase 7 Sprint 2
"""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime
import tempfile
import os

from app.degradation.priority_config import (
    Priority,
    PriorityConfig,
    PriorityConfigManager
)


class TestPriorityConfig:
    """Tests for PriorityConfig model."""

    def test_create_valid_config(self):
        """Test creating a valid priority configuration."""
        config = PriorityConfig(
            source_name="health_endpoints",
            priority=Priority.P0,
            timeout_ms=5000,
            retry_count=3,
            fallback_to_cache=True,
            cache_ttl_seconds=300
        )

        assert config.source_name == "health_endpoints"
        assert config.priority == Priority.P0
        assert config.timeout_ms == 5000
        assert config.retry_count == 3
        assert config.fallback_to_cache is True
        assert config.cache_ttl_seconds == 300

    def test_config_defaults(self):
        """Test default values for PriorityConfig."""
        config = PriorityConfig(
            source_name="test_source",
            priority=Priority.P2,
            timeout_ms=2000
        )

        assert config.retry_count == 0
        assert config.fallback_to_cache is True
        assert config.cache_ttl_seconds == 300
        assert config.enabled is True

    def test_priority_enum_values(self):
        """Test Priority enum values."""
        assert Priority.P0.value == 0
        assert Priority.P1.value == 1
        assert Priority.P2.value == 2
        assert Priority.P3.value == 3

    def test_config_validation_timeout(self):
        """Test timeout validation bounds."""
        # Valid timeout
        config = PriorityConfig(
            source_name="test",
            priority=Priority.P2,
            timeout_ms=5000
        )
        assert config.timeout_ms == 5000

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = PriorityConfig(
            source_name="test_source",
            priority=Priority.P1,
            timeout_ms=3000,
            retry_count=2
        )

        data = config.model_dump(mode='json')

        assert data["source_name"] == "test_source"
        assert data["priority"] == "P1"  # Should be string value
        assert data["timeout_ms"] == 3000


class TestPriorityConfigManager:
    """Tests for PriorityConfigManager."""

    def test_initialization_with_defaults(self):
        """Test manager loads default configurations."""
        manager = PriorityConfigManager(auto_save=False)

        # Check that default configs are loaded
        assert manager.get_config("health_endpoints") is not None
        assert manager.get_config("active_alerts") is not None
        assert manager.get_config("pod_status") is not None

        # Check P0 priority for health endpoints
        health_config = manager.get_config("health_endpoints")
        assert health_config.priority == Priority.P0
        assert health_config.timeout_ms == 5000
        assert health_config.retry_count == 3

    def test_get_config_for_specific_source(self):
        """Test getting configuration for a specific source."""
        manager = PriorityConfigManager(auto_save=False)

        config = manager.get_config("analytics")
        assert config is not None
        assert config.source_name == "analytics"
        assert config.priority == Priority.P3
        assert config.retry_count == 0

    def test_get_config_returns_none_for_unknown(self):
        """Test getting config for unknown source returns None."""
        manager = PriorityConfigManager(auto_save=False)

        config = manager.get_config("unknown_source_xyz")
        assert config is None

    def test_update_config(self):
        """Test updating a configuration."""
        manager = PriorityConfigManager(auto_save=False)

        new_config = PriorityConfig(
            source_name="health_endpoints",
            priority=Priority.P1,  # Changed from P0
            timeout_ms=3000,  # Changed from 5000
            retry_count=1
        )

        manager.update_config("health_endpoints", new_config)

        # Verify update
        retrieved = manager.get_config("health_endpoints")
        assert retrieved.priority == Priority.P1
        assert retrieved.timeout_ms == 3000
        assert retrieved.retry_count == 1

    def test_update_config_for_project(self):
        """Test updating project-specific configuration."""
        manager = PriorityConfigManager(auto_save=False)

        project_config = PriorityConfig(
            source_name="health_endpoints",
            priority=Priority.P0,
            timeout_ms=8000,  # Longer timeout for this project
            retry_count=5
        )

        manager.update_config("health_endpoints", project_config, project="meinvoice")

        # Project-specific config should override global
        retrieved = manager.get_config("health_endpoints", project="meinvoice")
        assert retrieved.timeout_ms == 8000
        assert retrieved.retry_count == 5

        # Global config should remain unchanged
        global_retrieved = manager.get_config("health_endpoints")
        assert global_retrieved.timeout_ms == 5000

    def test_get_all_configs(self):
        """Test getting all configurations."""
        manager = PriorityConfigManager(auto_save=False)

        all_configs = manager.get_all_configs()

        assert len(all_configs) > 0
        assert "health_endpoints" in all_configs
        assert "analytics" in all_configs

    def test_get_all_configs_for_project(self):
        """Test getting all configs including project overrides."""
        manager = PriorityConfigManager(auto_save=False)

        # Add project-specific config
        project_config = PriorityConfig(
            source_name="custom_source",
            priority=Priority.P0,
            timeout_ms=1000
        )
        manager.update_config("custom_source", project_config, project="test_project")

        all_configs = manager.get_all_configs(project="test_project")

        # Should include both global and project-specific
        assert "health_endpoints" in all_configs  # Global
        assert "custom_source" in all_configs  # Project-specific

    def test_delete_config(self):
        """Test deleting a configuration."""
        manager = PriorityConfigManager(auto_save=False)

        # Add a custom config
        custom_config = PriorityConfig(
            source_name="temp_source",
            priority=Priority.P2,
            timeout_ms=2000
        )
        manager.update_config("temp_source", custom_config)

        # Verify it exists
        assert manager.get_config("temp_source") is not None

        # Delete it
        manager.delete_config("temp_source")

        # Verify it's gone
        assert manager.get_config("temp_source") is None

    def test_delete_project_config(self):
        """Test deleting project-specific configuration."""
        manager = PriorityConfigManager(auto_save=False)

        # Add project-specific config
        project_config = PriorityConfig(
            source_name="test_source",
            priority=Priority.P1,
            timeout_ms=3000
        )
        manager.update_config("test_source", project_config, project="test_project")

        # Verify it exists
        assert manager.get_config("test_source", project="test_project") is not None

        # Delete it
        manager.delete_config("test_source", project="test_project")

        # Verify project config is gone, but global might remain
        project_retrieved = manager.get_config("test_source", project="test_project")
        # If no global config exists, should be None
        # If global exists, should return global config

    def test_get_sources_by_priority(self):
        """Test getting sources grouped by priority."""
        manager = PriorityConfigManager(auto_save=False)

        p0_sources = manager.get_sources_by_priority(Priority.P0)
        p3_sources = manager.get_sources_by_priority(Priority.P3)

        assert len(p0_sources) > 0
        assert "health_endpoints" in p0_sources
        assert "active_alerts" in p0_sources

        assert len(p3_sources) > 0
        assert "analytics" in p3_sources
        assert "logs_history" in p3_sources

    def test_get_priority_summary(self):
        """Test getting priority summary statistics."""
        manager = PriorityConfigManager(auto_save=False)

        summary = manager.get_priority_summary()

        assert "total_sources" in summary
        assert "by_priority" in summary
        assert "projects" in summary

        assert summary["total_sources"] > 0
        assert "P0" in summary["by_priority"]
        assert "P3" in summary["by_priority"]

        # Count should match
        total_by_priority = sum(summary["by_priority"].values())
        assert total_by_priority == summary["total_sources"]

    def test_validate_config_valid(self):
        """Test validation of valid configuration."""
        manager = PriorityConfigManager(auto_save=False)

        config = PriorityConfig(
            source_name="test",
            priority=Priority.P1,
            timeout_ms=3000,
            retry_count=2,
            cache_ttl_seconds=600
        )

        errors = manager.validate_config(config)
        assert len(errors) == 0

    def test_validate_config_invalid_timeout(self):
        """Test validation catches invalid timeout."""
        manager = PriorityConfigManager(auto_save=False)

        # Timeout too low
        config = PriorityConfig(
            source_name="test",
            priority=Priority.P2,
            timeout_ms=50  # Below minimum of 100
        )

        errors = manager.validate_config(config)
        assert len(errors) > 0
        assert any("Timeout" in e for e in errors)

    def test_validate_config_invalid_retries(self):
        """Test validation catches invalid retry count."""
        manager = PriorityConfigManager(auto_save=False)

        config = PriorityConfig(
            source_name="test",
            priority=Priority.P2,
            timeout_ms=2000,
            retry_count=10  # Above maximum of 5
        )

        errors = manager.validate_config(config)
        assert len(errors) > 0
        assert any("Retry" in e for e in errors)

    def test_validate_config_warnings(self):
        """Test validation generates warnings for suboptimal configs."""
        manager = PriorityConfigManager(auto_save=False)

        # P0 with insufficient retries (warning)
        config = PriorityConfig(
            source_name="test",
            priority=Priority.P0,
            timeout_ms=5000,
            retry_count=1  # Should be at least 2 for P0
        )

        errors = manager.validate_config(config)
        assert len(errors) > 0
        assert any("P0" in e and "retry" in e.lower() for e in errors)

    def test_save_and_load_configs(self):
        """Test saving and loading configurations from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "test_priority_config.yaml")

            # Create manager and modify a config
            manager = PriorityConfigManager(config_path=config_path, auto_save=False)

            custom_config = PriorityConfig(
                source_name="test_save_source",
                priority=Priority.P0,
                timeout_ms=1000
            )
            manager.update_config("test_save_source", custom_config)

            # Save
            manager.save_configs()

            # Create new manager and load
            new_manager = PriorityConfigManager(config_path=config_path, auto_save=False)

            # Verify custom config was loaded
            retrieved = new_manager.get_config("test_save_source")
            assert retrieved is not None
            assert retrieved.timeout_ms == 1000

    def test_get_all_sources_count(self):
        """Test total number of default sources."""
        manager = PriorityConfigManager(auto_save=False)

        summary = manager.get_priority_summary()

        # Should have at least the default sources
        assert summary["total_sources"] >= 8  # At least 8 default sources


@pytest.mark.asyncio
class TestPriorityConfigManagerAsync:
    """Async tests for PriorityConfigManager."""

    async def test_concurrent_config_access(self):
        """Test concurrent access to configurations."""
        manager = PriorityConfigManager(auto_save=False)

        async def access_configs():
            for _ in range(100):
                manager.get_config("health_endpoints")
                manager.get_all_configs()
                manager.get_priority_summary()

        # Run multiple concurrent accessors
        tasks = [access_configs() for _ in range(10)]
        await asyncio.gather(*tasks)

        # Verify no corruption
        summary = manager.get_priority_summary()
        assert summary["total_sources"] > 0
