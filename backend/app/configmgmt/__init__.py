"""
Configuration Management Package (configmgmt)

GitOps-based configuration storage, schema validation, version management
with rollback, security (encryption, sanitization) and audit logging.

Renamed from `app.config/` (2026-08-31): the old package shadowed the
settings module `app/config.py` of the same name, and the conflict was
resolved by an importlib spec_from_file_location hack that was invisible to
static analysis. Settings now live unambiguously in `app/settings.py`.
"""

from app.settings import Settings, settings

from .audit import AuditAction, AuditLogger
from .gitops import GitBranch, GitOpsManager
from .security import ConfigSecurity
from .validation import ConfigType, ConfigValidator, ValidationResult
from .versioning import ChangeType, ConfigVersion, ConfigVersionManager

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
