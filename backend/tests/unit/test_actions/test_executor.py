"""Unit tests for Command Executor."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.actions.executor import CommandExecutor, get_command_executor
from app.models.actions import CommandType, ExecutionResult


class TestCommandExecutor:
    """Test command execution functionality."""

    @pytest.fixture
    def executor(self):
        """Create executor instance."""
        return CommandExecutor()

    def test_executor_initialization(self, executor):
        """Test executor initialization with defaults."""
        assert executor._max_execution_time == 300
        assert len(executor._forbidden_commands) > 0
        assert "rm -rf" in str(executor._forbidden_commands)

    @pytest.mark.asyncio
    async def test_execute_kubectl_command_success(self, executor):
        """Test successful kubectl command execution."""
        # Mock asyncio.create_subprocess_shell
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"pod ready", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("kubectl get pods")

        assert result.success is True
        assert result.exit_code == 0
        assert "pod ready" in result.stdout
        assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_execute_command_failure(self, executor):
        """Test command execution failure."""
        # Mock failing process
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error: pod not found"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("kubectl get nonexistent-pod")

        assert result.success is False
        assert result.exit_code == 1
        assert "Error" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_command_timeout(self, executor):
        """Test command execution timeout."""
        # Mock process that times out
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("sleep 100", timeout_seconds=1)

        assert result.success is False
        assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_command_exception(self, executor):
        """Test command execution with exception."""
        with patch("asyncio.create_subprocess_shell", side_effect=Exception("Command failed")):
            result = await executor.execute("invalid-command")

        assert result.success is False
        assert "Command failed" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_dry_run(self, executor):
        """Test dry run execution."""
        result = await executor.execute("kubectl get pods", dry_run=True)

        assert result.success is True
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert result.duration_seconds == 0.0

    @pytest.mark.asyncio
    async def test_execute_dry_run_invalid_command(self, executor):
        """Test dry run with invalid command."""
        result = await executor.execute("invalid command with 'unclosed quote", dry_run=True)

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    def test_is_forbidden_rm_rf(self, executor):
        """Test forbidden command detection for rm -rf."""
        assert executor._is_forbidden("rm -rf /") is True
        assert executor._is_forbidden("some command && rm -rf file") is True

    def test_is_forbidden_fork_bomb(self, executor):
        """Test forbidden command detection for fork bomb."""
        assert executor._is_forbidden(":(){ :|:& };:") is True

    def test_is_forbidden_chmod(self, executor):
        """Test forbidden command detection for dangerous chmod."""
        assert executor._is_forbidden("chmod 000 file") is True

    def test_is_forbidden_mkfs(self, executor):
        """Test forbidden command detection for mkfs."""
        assert executor._is_forbidden("mkfs /dev/sda1") is True

    def test_is_not_forbidden_safe_commands(self, executor):
        """Test safe commands are not forbidden."""
        assert executor._is_forbidden("kubectl get pods") is False
        assert executor._is_forbidden("ls -la") is False
        assert executor._is_forbidden("echo hello") is False

    @pytest.mark.asyncio
    async def test_execute_forbidden_command(self, executor):
        """Test executing forbidden command."""
        result = await executor.execute("rm -rf /important/data")

        assert result.success is False
        assert "forbidden" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_kubectl_with_namespace(self, executor):
        """Test execute_kubectl helper."""
        # Mock process
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"result", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute_kubectl(
                args=["get", "pods"],
                namespace="default",
                dry_run=False,
            )

        assert result.success is True
        assert "kubectl" in str(result)

    @pytest.mark.asyncio
    async def test_execute_kubectl_dry_run(self, executor):
        """Test execute_kubectl with dry run."""
        result = await executor.execute_kubectl(
            args=["get", "pods"],
            namespace="default",
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_helm_upgrade(self, executor):
        """Test execute_helm helper."""
        # Mock process
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Release upgraded", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute_helm(
                args=["upgrade", "myapp", "./chart"],
                namespace="default",
                dry_run=False,
            )

        assert result.success is True
        assert "helm" in str(result)

    @pytest.mark.asyncio
    async def test_execute_helm_dry_run(self, executor):
        """Test execute_helm with dry run."""
        result = await executor.execute_helm(
            args=["install", "myapp", "./chart"],
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_argocd_sync(self, executor):
        """Test execute_argocd helper."""
        # Mock process
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Sync successful", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute_argocd(
                args=["app", "sync", "myapp"],
                dry_run=False,
            )

        assert result.success is True
        assert "argocd" in str(result)

    @pytest.mark.asyncio
    async def test_execute_argocd_dry_run(self, executor):
        """Test execute_argocd with dry run."""
        result = await executor.execute_argocd(
            args=["app", "sync", "myapp"],
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_with_custom_timeout(self, executor):
        """Test execution with custom timeout."""
        # Mock process that will timeout
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("sleep 100", timeout_seconds=2)

        assert result.success is False
        assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_measures_duration(self, executor):
        """Test that execution duration is measured."""
        # Mock fast process
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"done", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("echo done")

        assert result.duration_seconds >= 0
        assert result.duration_seconds < 1.0  # Should be very fast

    @pytest.mark.asyncio
    async def test_execute_unicode_handling(self, executor):
        """Test unicode handling in command output."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"Unicode: \xe2\x9c\x93 OK", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("echo test")

        assert result.success is True
        assert "OK" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_large_output(self, executor):
        """Test handling of large command output."""
        large_output = b"x" * 100000
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(large_output, b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await executor.execute("cat large-file")

        assert result.success is True
        assert len(result.stdout) == 100000


class TestCommandExecutorSingleton:
    """Test CommandExecutor singleton pattern."""

    def test_get_command_executor_returns_singleton(self):
        """Test that get_command_executor returns same instance."""
        executor1 = get_command_executor()
        executor2 = get_command_executor()

        assert executor1 is executor2

    def test_get_command_executor_initializes_new_instance(self):
        """Test that first call initializes the executor."""
        from app.actions.executor import _executor
        _executor = None

        executor = get_command_executor()

        assert executor is not None
        assert isinstance(executor, CommandExecutor)
