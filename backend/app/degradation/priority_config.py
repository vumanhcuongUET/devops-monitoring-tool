"""
Priority Configuration System - Phase 7 Sprint 2 Day 11-12

Purpose: Manage priority configurations for data sources during degradation

Priority Levels:
- P0 (Critical): Always fetch, no matter what
- P1 (High): Fetch if possible, with retries
- P2 (Medium): Fetch if time permits
- P3 (Low): Best effort only, skip if degraded

Features:
- Per-source priority configuration
- Timeout and retry settings
- Fallback to cache option
- Project-specific overrides
- Runtime configuration updates
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Priority levels for data fetching during degradation."""
    P0 = 0  # Critical - Always fetch (health, active alerts)
    P1 = 1  # High - Fetch if possible (pod status, current metrics)
    P2 = 2  # Medium - Fetch if time permits (recent logs, historical metrics)
    P3 = 3  # Low - Best effort only (historical logs, analytics)


class PriorityConfig(BaseModel):
    """Priority configuration for a data source."""
    source_name: str = Field(..., description="Name of the data source")
    priority: Priority = Field(..., description="Priority level")
    timeout_ms: int = Field(..., ge=100, le=30000, description="Timeout in milliseconds")
    retry_count: int = Field(default=0, ge=0, le=5, description="Number of retries")
    fallback_to_cache: bool = Field(default=True, description="Fallback to cache on failure")
    cache_ttl_seconds: int = Field(default=300, ge=0, description="Cache TTL for fallback data")
    enabled: bool = Field(default=True, description="Whether this source is enabled")

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "source_name": "health_endpoints",
                "priority": "P0",
                "timeout_ms": 5000,
                "retry_count": 3,
                "fallback_to_cache": True,
                "cache_ttl_seconds": 300,
                "enabled": True
            }
        }


class PriorityConfigManager:
    """
    Manage priority configurations for data sources.

    Features:
    - Default configurations for common sources
    - Project-specific overrides
    - Runtime configuration updates
    - Configuration validation
    - File-based persistence
    """

    # Default configurations for common data sources
    DEFAULT_CONFIGS: Dict[str, Dict[str, Any]] = {
        "health_endpoints": {
            "source_name": "health_endpoints",
            "priority": "P0",
            "timeout_ms": 5000,
            "retry_count": 3,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 300
        },
        "active_alerts": {
            "source_name": "active_alerts",
            "priority": "P0",
            "timeout_ms": 5000,
            "retry_count": 3,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 300
        },
        "pod_status": {
            "source_name": "pod_status",
            "priority": "P1",
            "timeout_ms": 3000,
            "retry_count": 2,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 180
        },
        "metrics_current": {
            "source_name": "metrics_current",
            "priority": "P1",
            "timeout_ms": 3000,
            "retry_count": 2,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 180
        },
        "logs_recent": {
            "source_name": "logs_recent",
            "priority": "P2",
            "timeout_ms": 2000,
            "retry_count": 1,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 120
        },
        "metrics_history": {
            "source_name": "metrics_history",
            "priority": "P2",
            "timeout_ms": 2000,
            "retry_count": 1,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 600
        },
        "logs_history": {
            "source_name": "logs_history",
            "priority": "P3",
            "timeout_ms": 1000,
            "retry_count": 0,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 900
        },
        "analytics": {
            "source_name": "analytics",
            "priority": "P3",
            "timeout_ms": 1000,
            "retry_count": 0,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 3600
        },
        "slo_data": {
            "source_name": "slo_data",
            "priority": "P2",
            "timeout_ms": 2000,
            "retry_count": 1,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 600
        },
        "deployment_status": {
            "source_name": "deployment_status",
            "priority": "P1",
            "timeout_ms": 3000,
            "retry_count": 2,
            "fallback_to_cache": True,
            "cache_ttl_seconds": 180
        }
    }

    def __init__(
        self,
        config_path: Optional[str] = None,
        auto_save: bool = True
    ):
        """
        Initialize priority configuration manager.

        Args:
            config_path: Path to configuration file (YAML)
            auto_save: Auto-save configuration on changes
        """
        self.config_path = config_path or "config/priority_config.yaml"
        self.auto_save = auto_save

        # Configurations: project -> source_name -> PriorityConfig
        self.configs: Dict[str, Dict[str, PriorityConfig]] = {}

        # Global defaults
        self.global_configs: Dict[str, PriorityConfig] = {}

        self._load_configs()

    def _load_configs(self):
        """Load configurations from file."""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    data = yaml.safe_load(f)

                if data:
                    self._parse_configs(data)
                    logger.info(f"Loaded priority configs from {self.config_path}")
                    return
        except Exception as e:
            logger.warning(f"Failed to load priority configs: {e}")

        # Load defaults
        self._load_defaults()

    def _parse_configs(self, data: Dict[str, Any]):
        """Parse configuration data."""
        # Parse global configs
        global_data = data.get("global", {})
        for source_name, config_data in global_data.items():
            try:
                self.global_configs[source_name] = PriorityConfig(**config_data)
            except Exception as e:
                logger.error(f"Invalid config for {source_name}: {e}")

        # Parse project-specific configs
        projects_data = data.get("projects", {})
        for project_name, project_configs in projects_data.items():
            self.configs[project_name] = {}
            for source_name, config_data in project_configs.items():
                try:
                    self.configs[project_name][source_name] = PriorityConfig(**config_data)
                except Exception as e:
                    logger.error(f"Invalid config for {project_name}/{source_name}: {e}")

    def _load_defaults(self):
        """Load default configurations."""
        for source_name, config_data in self.DEFAULT_CONFIGS.items():
            try:
                self.global_configs[source_name] = PriorityConfig(**config_data)
            except Exception as e:
                logger.error(f"Invalid default config for {source_name}: {e}")

        logger.info("Loaded default priority configurations")

    def get_config(
        self,
        source_name: str,
        project: Optional[str] = None
    ) -> Optional[PriorityConfig]:
        """
        Get configuration for a source.

        Args:
            source_name: Name of the data source
            project: Optional project name for project-specific config

        Returns:
            PriorityConfig or None if not found
        """
        # Try project-specific first
        if project and project in self.configs:
            if source_name in self.configs[project]:
                return self.configs[project][source_name]

        # Fall back to global config
        return self.global_configs.get(source_name)

    def get_all_configs(self, project: Optional[str] = None) -> Dict[str, PriorityConfig]:
        """
        Get all configurations.

        Args:
            project: Optional project name

        Returns:
            Dictionary of source_name -> PriorityConfig
        """
        if project and project in self.configs:
            # Merge project configs with global
            result = self.global_configs.copy()
            result.update(self.configs[project])
            return result

        return self.global_configs.copy()

    def update_config(
        self,
        source_name: str,
        config: PriorityConfig,
        project: Optional[str] = None
    ):
        """
        Update configuration for a source.

        Args:
            source_name: Name of the data source
            config: New configuration
            project: Optional project name (None for global)
        """
        if project:
            if project not in self.configs:
                self.configs[project] = {}
            self.configs[project][source_name] = config
        else:
            self.global_configs[source_name] = config

        logger.info(f"Updated priority config for {source_name} (project: {project or 'global'})")

        if self.auto_save:
            self.save_configs()

    def delete_config(
        self,
        source_name: str,
        project: Optional[str] = None
    ):
        """
        Delete configuration for a source.

        Args:
            source_name: Name of the data source
            project: Optional project name (None for global)
        """
        if project and project in self.configs:
            if source_name in self.configs[project]:
                del self.configs[project][source_name]
                logger.info(f"Deleted priority config for {project}/{source_name}")
                if self.auto_save:
                    self.save_configs()
                return

        if source_name in self.global_configs:
            del self.global_configs[source_name]
            logger.info(f"Deleted global priority config for {source_name}")
            if self.auto_save:
                self.save_configs()

    def save_configs(self):
        """Save configurations to file."""
        try:
            config_file = Path(self.config_path)
            config_file.parent.mkdir(parents=True, exist_ok=True)

            data: Dict[str, Any] = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "global": {},
                "projects": {}
            }

            # Save global configs
            for source_name, config in self.global_configs.items():
                data["global"][source_name] = config.model_dump(mode='json')

            # Save project configs
            for project_name, project_configs in self.configs.items():
                data["projects"][project_name] = {}
                for source_name, config in project_configs.items():
                    data["projects"][project_name][source_name] = config.model_dump(mode='json')

            with open(config_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)

            logger.info(f"Saved priority configs to {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to save priority configs: {e}")

    def get_sources_by_priority(self, priority: Priority) -> List[str]:
        """
        Get all sources with a given priority.

        Args:
            priority: Priority level

        Returns:
            List of source names
        """
        return [
            name for name, config in self.global_configs.items()
            if config.priority == priority
        ]

    def get_priority_summary(self) -> Dict[str, Any]:
        """
        Get summary of priority configurations.

        Returns:
            Dictionary with priority statistics
        """
        summary = {
            "total_sources": len(self.global_configs),
            "by_priority": {},
            "projects": len(self.configs)
        }

        for priority in Priority:
            count = sum(
                1 for config in self.global_configs.values()
                if config.priority == priority
            )
            summary["by_priority"][priority.name] = count

        return summary

    def validate_config(self, config: PriorityConfig) -> List[str]:
        """
        Validate a priority configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if config.timeout_ms < 100 or config.timeout_ms > 30000:
            errors.append(f"Timeout must be between 100 and 30000ms, got {config.timeout_ms}")

        if config.retry_count < 0 or config.retry_count > 5:
            errors.append(f"Retry count must be between 0 and 5, got {config.retry_count}")

        if config.cache_ttl_seconds < 0:
            errors.append(f"Cache TTL must be non-negative, got {config.cache_ttl_seconds}")

        # Check for priority-specific recommendations
        if config.priority == Priority.P0 and config.retry_count < 2:
            errors.append("Warning: P0 sources should have at least 2 retries for reliability")

        if config.priority == Priority.P3 and config.retry_count > 1:
            errors.append("Warning: P3 sources should have minimal retries (0-1)")

        return errors
