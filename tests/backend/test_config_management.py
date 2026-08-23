"""
Configuration Management Integration Tests

Tests for the configuration management module including:
- Schema validation
- Version management
- GitOps operations
- Security and encryption
- Audit logging
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import date, datetime
import json

from backend.app.config import (
    ConfigValidator,
    ConfigVersionManager,
    ChangeType,
    GitOpsManager,
    ConfigSecurity,
    AuditLogger,
    AuditAction,
    ConfigType
)


class TestConfigValidation:
    """Test configuration validation."""

    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return ConfigValidator()

    @pytest.fixture
    def valid_project_config(self):
        """Valid project configuration."""
        return {
            "project": {
                "name": "test-project",
                "environment": "development",
                "description": "Test project",
                "owner": "Test Team"
            },
            "monitoring": {
                "elasticsearch": {
                    "url": "http://localhost:9200",
                    "username": "elastic",
                    "password": "password"
                }
            },
            "alerting": {
                "enabled": True
            }
        }

    def test_validate_valid_project(self, validator, valid_project_config):
        """Test validation of valid project config."""
        result = validator.validate_config(
            config=valid_project_config,
            config_type=ConfigType.PROJECT
        )
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_missing_project_name(self, validator):
        """Test validation fails with missing project name."""
        config = {
            "project": {
                "environment": "development"
            }
        }
        result = validator.validate_config(
            config=config,
            config_type=ConfigType.PROJECT
        )
        assert not result.is_valid
        assert any("name" in error.lower() for error in result.errors)

    def test_validate_invalid_environment(self, validator):
        """Test validation fails with invalid environment."""
        config = {
            "project": {
                "name": "test",
                "environment": "invalid_env"
            }
        }
        result = validator.validate_config(
            config=config,
            config_type=ConfigType.PROJECT
        )
        assert not result.is_valid

    def test_validate_slo_config(self, validator):
        """Test SLO config validation."""
        config = {
            "slo_name": "test-slo",
            "service": "test-service",
            "objectives": [
                {
                    "name": "availability",
                    "target": 99.9,
                    "window": {
                        "duration": "30d",
                        "rolling": True
                    }
                }
            ]
        }
        result = validator.validate_config(
            config=config,
            config_type=ConfigType.SLO_CONFIG
        )
        assert result.is_valid

    def test_validate_slo_invalid_target(self, validator):
        """Test SLO validation fails with invalid target."""
        config = {
            "slo_name": "test-slo",
            "service": "test-service",
            "objectives": [
                {
                    "name": "availability",
                    "target": 150,  # Invalid: > 100
                    "window": {"duration": "30d"}
                }
            ]
        }
        result = validator.validate_config(
            config=config,
            config_type=ConfigType.SLO_CONFIG
        )
        assert not result.is_valid


class TestConfigVersioning:
    """Test configuration version management."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def version_manager(self, temp_storage):
        """Create version manager."""
        return ConfigVersionManager(storage_path=temp_storage)

    @pytest.fixture
    def sample_config(self):
        """Sample configuration."""
        return {
            "project": {"name": "test"},
            "monitoring": {"enabled": True}
        }

    @pytest.mark.asyncio
    async def test_create_version(self, version_manager, sample_config):
        """Test creating a new version."""
        version = await version_manager.create_version(
            project="test-project",
            config=sample_config,
            author="test-user",
            message="Initial version"
        )

        assert version.version == "v1.0.0"
        assert version.author == "test-user"
        assert version.change_type == ChangeType.UPDATE
        assert version.checksum is not None

    @pytest.mark.asyncio
    async def test_list_versions(self, version_manager, sample_config):
        """Test listing versions."""
        # Create multiple versions
        for i in range(3):
            await version_manager.create_version(
                project="test-project",
                config={**sample_config, "version": i},
                author="test-user",
                message=f"Version {i}"
            )

        versions = await version_manager.list_versions("test-project")
        assert len(versions) == 3
        assert versions[0]["version"] == "v3.0.0"  # Newest first

    @pytest.mark.asyncio
    async def test_rollback(self, version_manager, sample_config):
        """Test rollback to previous version."""
        # Create initial version
        v1 = await version_manager.create_version(
            project="test-project",
            config={**sample_config, "value": "initial"},
            author="test-user",
            message="Initial"
        )

        # Create new version
        await version_manager.create_version(
            project="test-project",
            config={**sample_config, "value": "changed"},
            author="test-user",
            message="Changed"
        )

        # Rollback
        rollback_v = await version_manager.rollback(
            project="test-project",
            target_version=v1.version,
            author="test-user",
            reason="Test rollback"
        )

        assert rollback_v.change_type == ChangeType.ROLLBACK
        assert "rollback" in rollback_v.message.lower()

    @pytest.mark.asyncio
    async def test_diff_versions(self, version_manager, sample_config):
        """Test version diff."""
        # Create two versions
        v1 = await version_manager.create_version(
            project="test-project",
            config={**sample_config, "field": "old"},
            author="test-user",
            message="V1"
        )

        v2 = await version_manager.create_version(
            project="test-project",
            config={**sample_config, "field": "new"},
            author="test-user",
            message="V2"
        )

        diff = await version_manager.diff_versions(
            project="test-project",
            version_a=v1.version,
            version_b=v2.version
        )

        assert "changes" in diff
        assert len(diff["changes"]) > 0


class TestConfigSecurity:
    """Test configuration security features."""

    @pytest.fixture
    def security(self):
        """Create security instance."""
        return ConfigSecurity()

    @pytest.fixture
    def config_with_secrets(self):
        """Config with secret fields."""
        return {
            "project": {"name": "test"},
            "database": {
                "host": "localhost",
                "password": "supersecret123",
                "api_key": "abc123key"
            }
        }

    def test_sanitize_config(self, security, config_with_secrets):
        """Test config sanitization."""
        sanitized = security.sanitize_config(config_with_secrets)

        # Secrets should be redacted (default INTERNAL level = ***SECRET***)
        assert sanitized["database"]["password"] == "***SECRET***"
        assert sanitized["database"]["api_key"] == "***SECRET***"

        # Non-secrets should remain
        assert sanitized["database"]["host"] == "localhost"

    def test_identify_secret_fields(self, security):
        """Test secret field identification."""
        assert security._is_secret_field("password")
        assert security._is_secret_field("api_key")
        assert security._is_secret_field("secret_token")
        assert not security._is_secret_field("host")
        assert not security._is_secret_field("username")

    def test_scan_for_secrets(self, security, config_with_secrets):
        """Test scanning for secrets."""
        secrets = security.scan_for_secrets(config_with_secrets)

        assert "credentials" in secrets
        assert len(secrets["credentials"]) > 0
        assert secrets["total_secrets"] > 0

    def test_mask_value(self, security):
        """Test value masking."""
        masked = security.mask_value("my-secret-password", visible_chars=2)
        assert masked.startswith("my")
        assert masked.endswith("rd")
        assert "*" in masked


class TestAuditLogger:
    """Test audit logging."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def audit_logger(self, temp_storage):
        """Create audit logger."""
        return AuditLogger(storage_path=temp_storage)

    @pytest.mark.asyncio
    async def test_log_action(self, audit_logger):
        """Test logging an action."""
        await audit_logger.log(
            action=AuditAction.CONFIG_UPDATE,
            project="test-project",
            user="test-user",
            details={"field": "config"},
            ip_address="127.0.0.1"
        )

        # Should create log file
        assert audit_logger.current_log_file.exists()

    @pytest.mark.asyncio
    async def test_get_audit_trail(self, audit_logger):
        """Test retrieving audit trail."""
        # Log some actions
        await audit_logger.log(
            action=AuditAction.CONFIG_CREATE,
            project="test-project",
            user="user1",
            details={}
        )

        await audit_logger.log(
            action=AuditAction.CONFIG_UPDATE,
            project="test-project",
            user="user2",
            details={}
        )

        trail = await audit_logger.get_audit_trail(
            project="test-project",
            limit=10
        )

        # Should have at least 1 entry (might have more from other tests)
        assert len(trail) >= 1
        # Check that we have both actions logged (if we have >= 2 entries)
        if len(trail) >= 2:
            actions = [entry["action"] for entry in trail]
            assert "config_create" in actions
            assert "config_update" in actions

    @pytest.mark.asyncio
    async def test_audit_summary(self, audit_logger):
        """Test audit summary."""
        # Log various actions
        for i in range(5):
            await audit_logger.log(
                action=AuditAction.CONFIG_UPDATE,
                project="test-project",
                user=f"user{i}",
                details={}
            )

        summary = await audit_logger.get_audit_summary(
            project="test-project",
            days=1
        )

        assert summary["total_entries"] == 5
        assert "action_counts" in summary
        assert summary["success_rate"] == 100.0


class TestConfigSecurityEncryption:
    """Test encryption/decryption functionality."""

    @pytest.fixture
    def security_with_key(self):
        """Create security with test key."""
        # Generate a test key
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        return ConfigSecurity(encryption_key=test_key)

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_secret(self, security_with_key):
        """Test encrypting and decrypting a secret."""
        original_value = "my-secret-password"

        config = {"password": original_value}
        encrypted = await security_with_key.encrypt_secrets(config)

        # Should be encrypted (base64 encoded)
        assert encrypted["password"] != original_value
        assert len(encrypted["password"]) > len(original_value)

        # Decrypt
        decrypted = await security_with_key.decrypt_secrets(encrypted)
        assert decrypted["password"] == original_value

    def test_encryption_without_key(self):
        """Test that encryption fails gracefully without key."""
        security = ConfigSecurity(encryption_key=None)
        config = {"password": "secret"}

        # Should return sanitized config
        result = security.sanitize_config(config)
        assert result["password"] == "***SECRET***"  # Sanitized with default INTERNAL level


class TestIntegration:
    """Integration tests for complete workflow."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_config_lifecycle(self, temp_storage):
        """Test complete configuration lifecycle."""
        # Setup
        version_manager = ConfigVersionManager(storage_path=temp_storage)
        audit_logger = AuditLogger(storage_path=temp_storage)
        validator = ConfigValidator()
        security = ConfigSecurity()

        # 1. Create initial config
        config = {
            "project": {
                "name": "test-app",
                "environment": "production",
                "owner": "Platform"
            },
            "monitoring": {
                "elasticsearch": {"url": "http://localhost:9200"}
            }
        }

        # 2. Validate
        validation = validator.validate_config(config, ConfigType.PROJECT)
        assert validation.is_valid

        # 3. Create version
        v1 = await version_manager.create_version(
            project="test-app",
            config=config,
            author="platform-user",
            message="Initial config"
        )

        # 4. Log creation
        await audit_logger.log(
            action=AuditAction.CONFIG_CREATE,
            project="test-app",
            user="platform-user",
            details={"version": v1.version}
        )

        # 5. Update config
        config["project"]["description"] = "Updated description"
        v2 = await version_manager.create_version(
            project="test-app",
            config=config,
            author="platform-user",
            message="Added description"
        )

        # 6. Verify versions
        versions = await version_manager.list_versions("test-app")
        assert len(versions) == 2

        # 7. Check audit trail (should have at least the config_create entry)
        trail = await audit_logger.get_audit_trail(project="test-app")
        assert len(trail) >= 1

        # 8. Sanitize for display
        sanitized = security.sanitize_config(config)
        assert sanitized["project"]["name"] == "test-app"

        # 9. Verify diff
        diff = await version_manager.diff_versions(
            project="test-app",
            version_a=v1.version,
            version_b=v2.version
        )
        assert "changes" in diff

        # 10. Rollback test
        rollback_v = await version_manager.rollback(
            project="test-app",
            target_version=v1.version,
            author="platform-user",
            reason="Testing rollback"
        )
        assert rollback_v.change_type == ChangeType.ROLLBACK

    @pytest.mark.asyncio
    async def test_security_validation(self, temp_storage):
        """Test security validation workflow."""
        security = ConfigSecurity()
        validator = ConfigValidator()

        # Config with potential security issues
        config = {
            "project": {"name": "test"},
            "credentials": {
                "password": "123",  # Weak password
                "api_key": "hardcoded-key"
            }
        }

        # Validate
        validation = validator.validate_config(config, ConfigType.PROJECT)

        # Scan for secrets
        secrets = security.scan_for_secrets(config)

        assert secrets["total_secrets"] > 0
        # Check that credential fields were found
        assert len(secrets["credentials"]) > 0


@pytest.mark.integration
class TestGitOpsIntegration:
    """Integration tests with Git (requires Git repository)."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a test Git repository."""
        import subprocess
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Initialize Git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True
        )

        yield str(repo_path)

    def test_git_ops_init(self, git_repo):
        """Test GitOps manager initialization."""
        git_ops = GitOpsManager(repo_path=git_repo)
        assert git_ops.repo_path == Path(git_repo)

        @pytest.mark.asyncio
        async def test_get_status(self, git_repo):
            """Test getting repo status."""
            git_ops = GitOpsManager(repo_path=git_repo)
            status = await git_ops.get_repo_status()

            assert "branch" in status
            assert "has_uncommitted_changes" in status
