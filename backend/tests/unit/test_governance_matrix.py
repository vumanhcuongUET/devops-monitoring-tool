"""Phase 12 manual-smoke follow-up: the APPROVE permission must stay reachable.

The Phase 12 S6 decision gate (`engine._check_decision_permission`) checks
`check(action="approve", environment=...)` against the same environment matrix
that gates auto-execution. Dropping APPROVE from staging/production made the
human-approval step itself impossible there — no user, admin included, could
approve (found live 2026-08-31: every production approve returned
"lacks 'approve' permission").
"""
from app.governance.ai_rbac import (
    AIPermission,
    check_permission,
    get_required_permission,
    role_allows,
)


class TestApproveReachable:
    def test_approve_action_maps_to_approve_permission(self):
        # Without this mapping "approve" fell through to the EXECUTE default.
        assert get_required_permission("approve") == AIPermission.APPROVE

    def test_approve_allowed_in_production(self):
        allowed, required, _ = check_permission("approve", "production")
        assert allowed, "production matrix must keep APPROVE (it IS the human approval)"
        assert required == AIPermission.APPROVE

    def test_approve_allowed_in_staging(self):
        allowed, required, _ = check_permission("approve", "staging")
        assert allowed
        assert required == AIPermission.APPROVE

    def test_approve_still_denied_in_read_only_prod(self):
        allowed, _, _ = check_permission("approve", "production-read-only")
        assert not allowed

    def test_role_narrowing_decides_who_may_approve(self):
        # Matrix widening must not widen roles: in production only admin approves.
        assert role_allows("admin", AIPermission.APPROVE, "production")
        assert not role_allows("operator", AIPermission.APPROVE, "production")
        assert not role_allows("viewer", AIPermission.APPROVE, "production")

    def test_executable_actions_unchanged(self):
        # The fix widens only APPROVE — auto-execution gates stay as strict.
        allowed_delete, _, _ = check_permission("delete", "production")
        allowed_exec, _, _ = check_permission("exec", "production")
        assert not allowed_delete
        assert not allowed_exec
