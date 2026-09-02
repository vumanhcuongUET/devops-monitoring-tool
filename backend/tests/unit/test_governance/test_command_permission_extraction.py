"""Phase 16 P1-2: command-to-action extraction for RBAC must survive global
flags and argocd's resource-group-first syntax.

The old extraction returned ``parts[1]``: a global flag for flag-first
commands ("kubectl -n prod delete pod x" → "-n") and "app" for every argocd
command. Both fell through ``get_required_permission``'s EXECUTE default, so
DELETE-tier commands passed the execute-time check in staging (no DELETE in
the matrix, but unknown → EXECUTE is) while read-only ``argocd_app_get`` was
denied in production (argocd "app" → EXECUTE, EXECUTE not in the prod
matrix).
"""
import pytest

from app.governance.ai_rbac import AIPermission, get_required_permission
from app.governance.permission_checker import AIPermissionChecker


@pytest.fixture
def checker() -> AIPermissionChecker:
    return AIPermissionChecker(default_environment="production", enable_rate_limit=False)


class TestExtractAction:
    def test_kubectl_flag_first_delete(self, checker):
        assert checker._extract_action("kubectl -n prod delete pod x") == "delete"

    def test_kubectl_long_flag_first(self, checker):
        assert checker._extract_action("kubectl --namespace=prod delete pod x") == "delete"

    def test_kubectl_verb_first_unchanged(self, checker):
        assert checker._extract_action("kubectl get pods -n prod") == "get"

    def test_kubectl_unknown_verb_surfaces_itself(self, checker):
        # "edit" is not in the parser's pattern — it must still extract as
        # "edit" (→ MODIFY), not as "-n" (→ EXECUTE default).
        assert checker._extract_action("kubectl -n prod edit deploy foo") == "edit"

    def test_helm_flag_first_uninstall(self, checker):
        assert checker._extract_action("helm -n prod uninstall my-release") == "uninstall"

    def test_helm_verb_first_unchanged(self, checker):
        assert checker._extract_action("helm upgrade my-release ./chart") == "upgrade"

    def test_argocd_delete(self, checker):
        assert checker._extract_action("argocd app delete myapp") == "delete"

    def test_argocd_read_only_get(self, checker):
        assert checker._extract_action("argocd app get myapp") == "get"

    def test_argocd_sync(self, checker):
        assert checker._extract_action("argocd app sync myapp") == "sync"


class TestPermissionMappingConsequences:
    def test_flag_first_delete_maps_to_delete_permission(self):
        assert get_required_permission("delete") == AIPermission.DELETE

    def test_argocd_get_maps_to_view_permission(self):
        assert get_required_permission("get") == AIPermission.VIEW

    def test_staging_denies_delete_tier_at_execute_time(self, checker):
        result = checker.check_command("kubectl -n prod delete pod x", environment="staging")
        # staging has no DELETE in its matrix — before the fix this passed
        # because "-n" degraded to EXECUTE.
        assert not result.allowed or result.required_permission == AIPermission.DELETE

    def test_production_allows_argocd_read(self, checker):
        result = checker.check_command("argocd app get myapp", environment="production")
        # Before the fix "app" → EXECUTE, which production denies — the
        # registry's read-only argocd_app_get was permanently unexecutable.
        assert result.allowed
        assert result.required_permission == AIPermission.VIEW
