"""Tests for AI RBAC (Role-Based Access Control) system."""

import pytest

from app.governance.ai_rbac import (
    AIPermission,
    ENVIRONMENT_PERMISSIONS,
    Environment,
    get_ai_permission_matrix,
)


class TestAIPermission:
    """Tests for AIPermission enum."""

    def test_permission_values(self):
        """Test permission values."""
        assert AIPermission.VIEW == "view"
        assert AIPermission.ANALYZE == "analyze"
        assert AIPermission.PROPOSE == "propose"
        assert AIPermission.EXECUTE_SAFE == "execute_safe"
        assert AIPermission.EXECUTE_ALL == "execute_all"

    def test_all_permissions_defined(self):
        """Test all permissions are defined."""
        permissions = [
            AIPermission.VIEW,
            AIPermission.ANALYZE,
            AIPermission.PROPOSE,
            AIPermission.EXECUTE_SAFE,
            AIPermission.EXECUTE_ALL,
        ]
        assert len(permissions) == 5


class TestEnvironment:
    """Tests for Environment enum."""

    def test_environment_values(self):
        """Test environment values."""
        assert Environment.PRODUCTION == "production"
        assert Environment.STAGING == "staging"
        assert Environment.DEVELOPMENT == "development"
        assert Environment.TESTING == "testing"

    def test_all_environments_defined(self):
        """Test all environments are defined."""
        environments = [
            Environment.PRODUCTION,
            Environment.STAGING,
            Environment.DEVELOPMENT,
            Environment.TESTING,
        ]
        assert len(environments) == 4


class TestEnvironmentPermissions:
    """Tests for environment permission matrix."""

    def test_production_permissions(self):
        """Test production environment permissions."""
        permissions = ENVIRONMENT_PERMISSIONS[Environment.PRODUCTION]
        assert AIPermission.VIEW in permissions
        assert AIPermission.ANALYZE in permissions
        assert AIPermission.PROPOSE in permissions
        assert AIPermission.EXECUTE_SAFE not in permissions
        assert AIPermission.EXECUTE_ALL not in permissions

    def test_staging_permissions(self):
        """Test staging environment permissions."""
        permissions = ENVIRONMENT_PERMISSIONS[Environment.STAGING]
        assert AIPermission.VIEW in permissions
        assert AIPermission.ANALYZE in permissions
        assert AIPermission.PROPOSE in permissions
        assert AIPermission.EXECUTE_SAFE in permissions
        assert AIPermission.EXECUTE_ALL not in permissions

    def test_development_permissions(self):
        """Test development environment permissions."""
        permissions = ENVIRONMENT_PERMISSIONS[Environment.DEVELOPMENT]
        assert AIPermission.VIEW in permissions
        assert AIPermission.ANALYZE in permissions
        assert AIPermission.PROPOSE in permissions
        assert AIPermission.EXECUTE_SAFE in permissions
        assert AIPermission.EXECUTE_ALL in permissions

    def test_testing_permissions(self):
        """Test testing environment permissions."""
        permissions = ENVIRONMENT_PERMISSIONS[Environment.TESTING]
        assert AIPermission.VIEW in permissions
        assert AIPermission.ANALYZE in permissions
        assert AIPermission.PROPOSE in permissions
        assert AIPermission.EXECUTE_ALL in permissions

    def test_permission_hierarchy(self):
        """Test that permissions follow security hierarchy."""
        prod_perms = set(ENVIRONMENT_PERMISSIONS[Environment.PRODUCTION])
        staging_perms = set(ENVIRONMENT_PERMISSIONS[Environment.STAGING])
        dev_perms = set(ENVIRONMENT_PERMISSIONS[Environment.DEVELOPMENT])

        # Production should have the most restrictive permissions
        assert prod_perms.issubset(staging_perms)

        # Development should have the most permissive permissions
        assert staging_perms.issubset(dev_perms)


class TestAIPermissionMatrix:
    """Tests for AI permission matrix function."""

    def test_get_permission_matrix(self):
        """Test getting permission matrix."""
        matrix = get_ai_permission_matrix()
        assert Environment.PRODUCTION in matrix
        assert Environment.STAGING in matrix
        assert Environment.DEVELOPMENT in matrix
        assert Environment.TESTING in matrix

    def test_permission_matrix_structure(self):
        """Test permission matrix structure."""
        matrix = get_ai_permission_matrix()
        for env, permissions in matrix.items():
            assert isinstance(permissions, list)
            assert len(permissions) > 0
            for perm in permissions:
                assert isinstance(perm, AIPermission)

    def test_has_permission(self):
        """Test checking if permission exists in environment."""
        matrix = get_ai_permission_matrix()

        # Production should have VIEW
        assert AIPermission.VIEW in matrix[Environment.PRODUCTION]

        # Production should not have EXECUTE_ALL
        assert AIPermission.EXECUTE_ALL not in matrix[Environment.PRODUCTION]

        # Development should have EXECUTE_ALL
        assert AIPermission.EXECUTE_ALL in matrix[Environment.DEVELOPMENT]


class TestPermissionConstraints:
    """Tests for permission constraint logic."""

    def test_least_privilege_principle(self):
        """Test that least privilege principle is maintained."""
        matrix = get_ai_permission_matrix()

        # Production should be most restrictive
        prod_count = len(matrix[Environment.PRODUCTION])
        dev_count = len(matrix[Environment.DEVELOPMENT])

        assert prod_count < dev_count

    def test_no_execute_in_production(self):
        """Test that production doesn't allow execution without approval."""
        matrix = get_ai_permission_matrix()
        prod_perms = matrix[Environment.PRODUCTION]

        assert AIPermission.EXECUTE_SAFE not in prod_perms
        assert AIPermission.EXECUTE_ALL not in prod_perms

    def test_all_environments_have_view(self):
        """Test that all environments have at least VIEW permission."""
        matrix = get_ai_permission_matrix()

        for env, permissions in matrix.items():
            assert AIPermission.VIEW in permissions

    def test_all_environments_have_analyze(self):
        """Test that all environments have ANALYZE permission."""
        matrix = get_ai_permission_matrix()

        for env, permissions in matrix.items():
            assert AIPermission.ANALYZE in permissions
