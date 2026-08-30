"""
Configuration Loader for AI Assistant.

Extracted from run_query.py for better modularity and testing.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent


def load_config(project: str) -> Dict[str, Any]:
    """
    Load configuration for a project.

    Merges global config with project-specific config.
    Project config can inherit or override global sources.

    Args:
        project: Project name (must exist in projects/)

    Returns:
        Merged configuration dictionary
    """
    # Load global config
    global_cfg_path = ROOT / "config" / "global.yaml"
    if not global_cfg_path.exists():
        raise FileNotFoundError(f"Global config not found: {global_cfg_path}")

    global_cfg = yaml.safe_load(global_cfg_path.read_text("utf-8"))

    # Load project config
    project_cfg_path = ROOT / "projects" / project / "config.yaml"
    if not project_cfg_path.exists():
        # Use minimal config if project doesn't exist
        return {**global_cfg, "project": project}

    project_cfg = yaml.safe_load(project_cfg_path.read_text("utf-8"))

    # Merge sources: global + project (respects inherit flag)
    g_sources = global_cfg.get("sources", {})
    p_sources = project_cfg.get("sources", {})
    merged_sources = dict(g_sources)

    for src_type, src_def in p_sources.items():
        if isinstance(src_def, dict):
            inherit = src_def.get("inherit", True)
            extra = src_def.get("extra", [])
            base = g_sources.get(src_type, []) if inherit else []
            merged_sources[src_type] = base + extra
        else:
            # Not a dict, just replace
            merged_sources[src_type] = src_def

    # Merge query vars: global defaults < project overrides
    g_vars = dict(global_cfg.get("defaults", {}))
    p_vars = project_cfg.get("query_vars", {})

    result = {**global_cfg, **project_cfg}
    result["sources"] = merged_sources
    result["query_vars"] = {**g_vars, **p_vars}

    return result


def load_query_def(project: str, section: str) -> Dict[str, Any]:
    """
    Load query definition for a section.

    Project override takes priority over common definitions.

    Args:
        project: Project name
        section: Section identifier (e.g., 'errors', 'alerts')

    Returns:
        Query definition dictionary

    Raises:
        FileNotFoundError: If no query definition found
    """
    candidates = [
        ROOT / "projects" / project / "queries" / f"{section}.yaml",
        ROOT / "queries" / "common" / f"{section}.yaml",
    ]

    for path in candidates:
        if path.exists():
            return yaml.safe_load(path.read_text("utf-8"))

    raise FileNotFoundError(
        f"No query definition found for section '{section}'. "
        f"Checked: {[str(p) for p in candidates]}"
    )


def load_feature_flags() -> Dict[str, Any]:
    """
    Load feature flags from features.yaml.

    Returns empty dict if file doesn't exist (all features disabled).

    Returns:
        Feature flags dictionary with nested structure
    """
    features_path = ROOT / "config" / "features.yaml"
    if not features_path.exists():
        # Default: optimization enabled
        return {
            "optimization": {
                "cache_enabled": True,
                "cache_ttl_seconds": 60,
                "deduplication_enabled": True,
                "parallel_queries": True,
                "max_parallel_workers": 8
            },
            "output": {
                "use_emoji": True,
                "use_colors": True,
                "truncate_results": True,
                "max_results_per_source": 10
            },
            "query": {
                "validate_time_range": True,
                "max_time_range_hours": 168,
                "enforce_timeout": True,
                "default_timeout_seconds": 10
            },
            "monitoring": {
                "track_metrics": False,
                "metrics_output_file": None,
                "debug_mode": False
            }
        }

    return yaml.safe_load(features_path.read_text("utf-8"))


# Feature flag cache (module-level)
_FEATURE_FLAGS_CACHE: Optional[Dict[str, Any]] = None


def get_feature_flags() -> Dict[str, Any]:
    """
    Get feature flags with caching.

    Returns:
        Cached feature flags dictionary
    """
    global _FEATURE_FLAGS_CACHE
    if _FEATURE_FLAGS_CACHE is None:
        _FEATURE_FLAGS_CACHE = load_feature_flags()
    return _FEATURE_FLAGS_CACHE


def is_feature_enabled(feature_path: str) -> bool:
    """
    Check if a specific feature is enabled.

    Args:
        feature_path: Dot-notation path to feature, e.g., "optimization.cache_enabled"
                      or "optimization.parallel_queries"

    Returns:
        True if feature is enabled, False otherwise

    Examples:
        >>> is_feature_enabled("optimization.cache_enabled")
        True
        >>> is_feature_enabled("output.use_emoji")
        True
    """
    flags = get_feature_flags()
    keys = feature_path.split(".")
    value = flags
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return False
    return bool(value)


def reload_feature_flags() -> Dict[str, Any]:
    """
    Force reload feature flags from disk.

    Useful when features.yaml changes during runtime.

    Returns:
        Reloaded feature flags dictionary
    """
    global _FEATURE_FLAGS_CACHE
    _FEATURE_FLAGS_CACHE = load_feature_flags()
    return _FEATURE_FLAGS_CACHE


def render_template(template: str, vars_: Dict[str, Any]) -> str:
    """
    Replace {{ key }} placeholders in template string.

    Missing keys become empty string.

    Args:
        template: Template string with {{ key }} placeholders
        vars_: Variables to substitute

    Returns:
        Rendered string
    """
    import re

    def replacer(match: re.Match) -> str:
        """Replace a single placeholder with its value or empty string."""
        key = match.group(1)
        value = vars_.get(key)
        if value is None:
            return ""
        return str(value)

    # Replace all {{ key }} placeholders
    pattern = r"{{\s*(\w+)\s*}}"
    return re.sub(pattern, replacer, template)
