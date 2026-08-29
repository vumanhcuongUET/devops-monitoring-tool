"""
Configuration Management Module

This module provides comprehensive configuration management including:
- GitOps-based configuration storage
- Schema validation
- Version management with rollback
- Security (encryption, sanitization)
- Audit logging
"""

# Import settings from config.py to resolve package/module conflict
# When both config.py and config/ exist, Python treats config/ as package
# We need to import settings from config.py which is at the parent level
import importlib.util
import os
import sys

from .audit import AuditAction, AuditLogger
from .gitops import GitBranch, GitOpsManager
from .security import ConfigSecurity
from .validation import ConfigType, ConfigValidator, ValidationResult
from .versioning import ChangeType, ConfigVersion, ConfigVersionManager

# Load config.py module directly
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
spec = importlib.util.spec_from_file_location("app.config_module", config_path)
config_module = importlib.util.module_from_spec(spec)
sys.modules["app.config_module"] = config_module
spec.loader.exec_module(config_module)

# Export settings and Settings class
settings = config_module.settings
Settings = config_module.Settings

__all__ = [
    "AuditAction",
    "AuditLogger",
    "ChangeType",
    "ConfigSecurity",
    "ConfigType",
    "ConfigValidator",
    "ConfigVersion",
    "ConfigVersionManager",
    "GitBranch",
    "GitOpsManager",
    "Settings",
    "ValidationResult",
    "settings",
]
