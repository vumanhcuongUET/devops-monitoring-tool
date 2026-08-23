"""
Configuration Versioning Module

Provides version management with Git integration, rollback capabilities,
and change tracking.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of configuration change."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ROLLBACK = "rollback"


@dataclass
class ConfigVersion:
    """Configuration version metadata."""
    version: str
    timestamp: datetime
    config: Dict[str, Any]
    checksum: str
    author: str
    message: str
    change_type: ChangeType
    size_bytes: int
    parent_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "checksum": self.checksum,
            "author": self.author,
            "message": self.message,
            "change_type": self.change_type.value,
            "size_bytes": self.size_bytes,
            "parent_version": self.parent_version,
            "config": self.config
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigVersion":
        """Create from dictionary."""
        return cls(
            version=data["version"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            checksum=data["checksum"],
            author=data["author"],
            message=data["message"],
            change_type=ChangeType(data["change_type"]),
            size_bytes=data["size_bytes"],
            parent_version=data.get("parent_version"),
            config=data["config"]
        )


class ConfigVersionManager:
    """Manage configuration versions with Git integration."""

    def __init__(self, storage_path: str, git_ops=None):
        """Initialize version manager.

        Args:
            storage_path: Base path for storing versions
            git_ops: Optional GitOpsManager instance for Git integration
        """
        self.storage_path = Path(storage_path)
        self.versions_path = self.storage_path / "versions"
        self.versions_path.mkdir(parents=True, exist_ok=True)
        self.git_ops = git_ops
        self._current_versions: Dict[str, str] = {}

    async def create_version(
        self,
        project: str,
        config: Dict[str, Any],
        author: str,
        message: str,
        change_type: ChangeType = ChangeType.UPDATE,
        commit_to_git: bool = True
    ) -> ConfigVersion:
        """Create a new configuration version.

        Args:
            project: Project name
            config: Configuration data
            author: Author name
            message: Commit message
            change_type: Type of change
            commit_to_git: Whether to commit to Git

        Returns:
            Created ConfigVersion
        """
        # Calculate checksum and size
        config_str = json.dumps(config, sort_keys=True, default=str)
        checksum = hashlib.sha256(config_str.encode()).hexdigest()
        size_bytes = len(config_str.encode())

        # Get parent version
        parent = await self._get_latest_version(project)

        # Generate version number
        versions = await self._list_versions(project)
        version_number = len(versions) + 1
        version_id = f"v{version_number}.0.0"

        version = ConfigVersion(
            version=version_id,
            timestamp=datetime.now(),
            config=config,
            checksum=checksum,
            author=author,
            message=message,
            change_type=change_type,
            size_bytes=size_bytes,
            parent_version=parent
        )

        # Save version to storage
        await self._save_version(project, version)

        # Update current version
        self._current_versions[project] = version_id

        # Commit to Git if enabled and GitOps is available
        if commit_to_git and self.git_ops:
            try:
                await self.git_ops.commit_change(
                    project=project,
                    author=author,
                    message=message
                )
                logger.info(f"Comitted version {version_id} to Git")
            except Exception as e:
                logger.error(f"Failed to commit to Git: {e}")

        logger.info(f"Created version {version_id} for project {project}")
        return version

    async def rollback(
        self,
        project: str,
        target_version: str,
        author: str,
        reason: str,
        push_to_git: bool = True
    ) -> ConfigVersion:
        """Rollback to a specific version.

        Args:
            project: Project name
            target_version: Version to rollback to
            author: Author name
            reason: Reason for rollback
            push_to_git: Whether to push to Git

        Returns:
            New rollback version
        """
        version = await self._get_version(project, target_version)

        if not version:
            raise ValueError(f"Version {target_version} not found for project {project}")

        # Create rollback version
        rollback_version = await self.create_version(
            project=project,
            config=version.config,
            author=author,
            message=f"Rollback to {target_version}: {reason}",
            change_type=ChangeType.ROLLBACK,
            commit_to_git=False
        )

        # Update current config
        await self._update_current_config(project, version.config)

        # Push to Git if enabled
        if push_to_git and self.git_ops:
            try:
                await self.git_ops.push_changes()
                logger.info(f"Pushed rollback to Git for {project}")
            except Exception as e:
                logger.error(f"Failed to push to Git: {e}")

        logger.info(f"Rolled back {project} to {target_version}")
        return rollback_version

    async def diff_versions(
        self,
        project: str,
        version_a: str,
        version_b: str
    ) -> Dict[str, Any]:
        """Compare two versions.

        Args:
            project: Project name
            version_a: First version
            version_b: Second version

        Returns:
            Dictionary with differences
        """
        v_a = await self._get_version(project, version_a)
        v_b = await self._get_version(project, version_b)

        if not v_a or not v_b:
            return {"error": "One or both versions not found"}

        return {
            "project": project,
            "version_a": version_a,
            "version_b": version_b,
            "version_a_timestamp": v_a.timestamp.isoformat(),
            "version_b_timestamp": v_b.timestamp.isoformat(),
            "changes": self._calculate_diff(v_a.config, v_b.config),
            "size_change": v_b.size_bytes - v_a.size_bytes,
            "size_change_percent": (
                ((v_b.size_bytes - v_a.size_bytes) / v_a.size_bytes * 100)
                if v_a.size_bytes > 0 else 0
            ),
            "time_delta_seconds": (v_b.timestamp - v_a.timestamp).total_seconds(),
            "authors": {
                "version_a": v_a.author,
                "version_b": v_b.author
            },
            "change_types": {
                "version_a": v_a.change_type.value,
                "version_b": v_b.change_type.value
            }
        }

    async def list_versions(
        self,
        project: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List versions for a project.

        Args:
            project: Project name
            limit: Maximum number of versions to return
            offset: Offset for pagination

        Returns:
            List of version summaries
        """
        versions = await self._list_versions(project)

        # Apply pagination
        versions = versions[offset:offset + limit]

        # Return summaries (without full config)
        return [
            {
                "version": v.version,
                "timestamp": v.timestamp.isoformat(),
                "checksum": v.checksum,
                "author": v.author,
                "message": v.message,
                "change_type": v.change_type.value,
                "size_bytes": v.size_bytes,
                "parent_version": v.parent_version
            }
            for v in versions
        ]

    async def get_version_history(
        self,
        project: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> List[ConfigVersion]:
        """Get version history for a project within a time range.

        Args:
            project: Project name
            since: Start of time range
            until: End of time range

        Returns:
            List of ConfigVersions in range
        """
        versions = await self._list_versions(project)

        filtered = []
        for version in versions:
            if since and version.timestamp < since:
                continue
            if until and version.timestamp > until:
                continue
            filtered.append(version)

        return filtered

    async def delete_version(
        self,
        project: str,
        version: str,
        author: str
    ) -> bool:
        """Delete a specific version (with proper authorization).

        Args:
            project: Project name
            version: Version to delete
            author: Author requesting deletion

        Returns:
            True if deleted successfully
        """
        project_dir = self.versions_path / project
        version_file = project_dir / f"{version}.json"

        if not version_file.exists():
            return False

        # Don't allow deleting current version
        current = self._current_versions.get(project)
        if current == version:
            raise ValueError(f"Cannot delete current version {version}")

        try:
            version_file.unlink()
            logger.info(f"Deleted version {version} for {project} by {author}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete version: {e}")
            return False

    def _calculate_diff(
        self,
        config_a: Dict[str, Any],
        config_b: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Calculate differences between configs."""
        changes = []

        # Find keys added/modified in B
        for key in set(list(config_b.keys()) + list(config_a.keys())):
            if key not in config_a:
                changes.append({
                    "type": "added",
                    "path": key,
                    "value": str(config_b[key])[:100]
                })
            elif key not in config_b:
                changes.append({
                    "type": "removed",
                    "path": key,
                    "value": str(config_a[key])[:100]
                })
            elif config_a[key] != config_b[key]:
                if isinstance(config_b[key], dict) and isinstance(config_a[key], dict):
                    # Nested diff
                    nested = self._calculate_diff(config_a[key], config_b[key])
                    for n in nested:
                        changes.append({
                            "type": n["type"],
                            "path": f"{key}.{n['path']}",
                            "value": n.get("value", "")
                        })
                else:
                    changes.append({
                        "type": "modified",
                        "path": key,
                        "old_value": str(config_a[key])[:100],
                        "new_value": str(config_b[key])[:100]
                    })

        return changes

    async def _save_version(self, project: str, version: ConfigVersion):
        """Save version to storage."""
        project_dir = self.versions_path / project
        project_dir.mkdir(exist_ok=True)

        version_file = project_dir / f"{version.version}.json"

        with open(version_file, "w") as f:
            json.dump(version.to_dict(), f, indent=2, default=str)

    async def _get_version(
        self,
        project: str,
        version_id: str
    ) -> Optional[ConfigVersion]:
        """Get specific version."""
        project_dir = self.versions_path / project
        version_file = project_dir / f"{version_id}.json"

        if not version_file.exists():
            return None

        try:
            with open(version_file) as f:
                data = json.load(f)
            return ConfigVersion.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load version {version_id}: {e}")
            return None

    async def _list_versions(self, project: str) -> List[ConfigVersion]:
        """List all versions for a project, sorted by timestamp."""
        project_dir = self.versions_path / project

        if not project_dir.exists():
            return []

        versions = []

        for version_file in sorted(project_dir.glob("v*.json")):
            try:
                with open(version_file) as f:
                    data = json.load(f)
                versions.append(ConfigVersion.from_dict(data))
            except Exception as e:
                logger.error(f"Failed to load version file {version_file}: {e}")

        # Sort by timestamp descending (newest first)
        versions.sort(key=lambda v: v.timestamp, reverse=True)
        return versions

    async def _get_latest_version(self, project: str) -> Optional[str]:
        """Get latest version number."""
        versions = await self._list_versions(project)
        return versions[0].version if versions else None

    async def _update_current_config(self, project: str, config: Dict[str, Any]):
        """Update current configuration file."""
        config_file = self.storage_path / "projects" / project / "config.yaml"

        if not config_file.parent.exists():
            config_file.parent.mkdir(parents=True, exist_ok=True)

        import yaml
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    async def get_version_count(self, project: str) -> int:
        """Get total number of versions for a project."""
        versions = await self._list_versions(project)
        return len(versions)

    async def cleanup_old_versions(
        self,
        project: str,
        author: str,
        keep_count: int = 10
    ) -> int:
        """Clean up old versions, keeping only the most recent N.

        Args:
            project: Project name
            keep_count: Number of versions to keep
            author: Author requesting cleanup

        Returns:
            Number of versions deleted
        """
        versions = await self._list_versions(project)

        if len(versions) <= keep_count:
            return 0

        # Keep current version
        current = self._current_versions.get(project)

        # Versions to delete (skip current)
        to_delete = []
        for version in versions[keep_count:]:
            if version.version != current:
                to_delete.append(version.version)

        # Delete
        deleted = 0
        for version_id in to_delete:
            if await self.delete_version(project, version_id, author):
                deleted += 1

        logger.info(f"Cleaned up {deleted} old versions for {project}")
        return deleted
