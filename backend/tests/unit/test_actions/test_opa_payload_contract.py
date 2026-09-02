"""Phase 16 P1-9: the OPA input contract.

actions.rego reads risk_level / status / parsed_params / command_type /
resource fields off input.action. The engine used to send only
{"command", "id"}, so every rule was undefined and OPA_ENFORCE could only
ever deny. Pin the payload shape here; policies/opa are compile-checked and
behavior-tested against the same shape (docs/phase-16-full-review-findings.md).
"""
import pytest

from app.actions.engine import get_action_engine


@pytest.mark.asyncio
async def test_opa_payload_carries_the_fields_the_policies_read():
    engine = get_action_engine(k8s_client=None)
    payload = engine._build_opa_action_payload(
        action_id="act-1",
        command="kubectl delete namespace prod",
        state={
            "command": "kubectl delete namespace prod",
            "command_type": "kubectl",
            "status": "approved",
            "risk_level": "critical",
            "title": "delete ns",
            "project": "meinvoice",
            "parsed_params": {
                "command_type": "kubectl",
                "action": "delete",
                "resource_type": "namespace",
                "resource_name": "prod",
                "flags": {},
                "args": [],
            },
            "context": {"environment": "production"},
        },
        environment="production",
    )

    # Fields the rego rules directly reference
    for key in ("risk_level", "status", "parsed_params", "command_type",
                "resource_type", "resource_name", "labels", "context", "title"):
        assert key in payload, f"OPA payload missing {key!r} — policies go undefined"
    assert payload["risk_level"] == "critical"
    assert payload["status"] == "approved"
    assert payload["parsed_params"]["action"] == "delete"
    assert payload["parsed_params"]["resource_type"] == "namespace"


@pytest.mark.asyncio
async def test_opa_payload_normalizes_enum_values():
    """Tracker state may carry enum members, not plain strings — the payload
    must deliver plain strings or every rego comparison goes undefined."""
    from app.models.actions import ActionStatus, RiskLevel, CommandType

    engine = get_action_engine(k8s_client=None)
    payload = engine._build_opa_action_payload(
        action_id="act-1",
        command="kubectl get pods",
        state={
            "command_type": CommandType.KUBECTL,
            "status": ActionStatus.APPROVED,
            "risk_level": RiskLevel.SAFE,
            "parsed_params": {},
            "context": {},
        },
        environment="production",
    )

    assert payload["command_type"] == "kubectl"
    assert payload["status"] == "approved"
    assert payload["risk_level"] == "safe"
