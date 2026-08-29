"""Context Registry loader for project-specific configuration."""

import json
import os
from pathlib import Path
from typing import Optional

import yaml

from app.models.registry import ProjectConfig, RegistryConfig

# Anchored to backend/ (not CWD) so the loader works regardless of launch dir
_REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = _REPO_ROOT / "projects"
DEFAULT_REGISTRY_FILE = Path(__file__).resolve().parent / "default_projects.yaml"
REGISTRY_CACHE_FILE = _REPO_ROOT / "data" / "registry_cache.json"


def load_registry() -> RegistryConfig:
    """Load the complete registry configuration."""
    # Try cache first
    if os.path.exists(REGISTRY_CACHE_FILE):
        try:
            with open(REGISTRY_CACHE_FILE) as f:
                data = json.load(f)
                return RegistryConfig(**data)
        except (json.JSONDecodeError, ValueError):
            pass  # Fall through to rebuild cache

    # Load from project YAML files
    registry = _load_from_projects()
    _save_cache(registry)
    return registry


def _load_from_projects() -> RegistryConfig:
    """Load registry configuration from individual project YAML files."""
    projects = []

    # If projects directory exists, load from there
    if os.path.exists(REGISTRY_DIR):
        for filename in os.listdir(REGISTRY_DIR):
            if not filename.endswith(".yaml") and not filename.endswith(".yml"):
                continue

            filepath = os.path.join(REGISTRY_DIR, filename)
            try:
                with open(filepath) as f:
                    data = yaml.safe_load(f)
                    if data:
                        projects.append(ProjectConfig(**data))
            except (yaml.YAMLError, ValueError) as e:
                print(f"Warning: Failed to load {filename}: {e}")
                continue

    return RegistryConfig(projects=projects)


def _save_cache(registry: RegistryConfig):
    """Save registry to cache file for faster loading."""
    os.makedirs(os.path.dirname(REGISTRY_CACHE_FILE), exist_ok=True)
    with open(REGISTRY_CACHE_FILE, "w") as f:
        json.dump(registry.model_dump(), f, indent=2)


def get_project_config(project_name: str) -> Optional[ProjectConfig]:
    """Get configuration for a specific project."""
    registry = load_registry()
    for project in registry.projects:
        if project.name == project_name:
            return project
    return None


def invalidate_cache():
    """Invalidate the registry cache (force reload)."""
    if os.path.exists(REGISTRY_CACHE_FILE):
        os.remove(REGISTRY_CACHE_FILE)


def reload_registry() -> RegistryConfig:
    """Force reload of the registry configuration."""
    invalidate_cache()
    return load_registry()


# Singleton cache
_registry_cache: Optional[RegistryConfig] = None


def get_registry() -> RegistryConfig:
    """Get or load the registry configuration (cached)."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = load_registry()
    return _registry_cache


def refresh_registry():
    """Refresh the in-memory cache from disk."""
    global _registry_cache
    _registry_cache = load_registry()
