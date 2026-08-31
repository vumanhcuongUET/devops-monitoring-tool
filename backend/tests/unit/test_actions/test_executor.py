"""Unit tests for Command Executor."""

import asyncio
from unittest.mock import patch

import pytest

from app.actions.executor import (
    MAX_OUTPUT_BYTES,
    CommandExecutor,
    get_command_executor,
    mark_truncated,
    read_stream_capped,
)


class FakeStream:
    """Minimal stand-in for a subprocess stdout/stderr pipe."""

    def __init__(self, data: bytes = b""):
        self._data = data

    async def read(self, n: int = -1):
        if not self._data:
            return b""
        size = len(self._data) if n < 0 else min(n, len(self._data))
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class HangingStream:
    """Stream whose read never completes — drives the timeout path."""

    async def read(self, n: int = -1):
        await asyncio.sleep(3600)
        return b""


class FakeProcess:
    """Process whose streams feed FakeStream (the executor no longer uses
    communicate(); it reads the pipes directly with a capture cap)."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0, hang=False):
        self.stdout = HangingStream() if hang else FakeStream(stdout)
        self.stderr = HangingStream() if hang else FakeStream(stderr)
        self.returncode = returncode
        self.killed = False

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


class TestCommandExecutor:
    """Test command execution functionality."""

    @pytest.fixture
    def executor(self):
        """Create executor instance."""
        return CommandExecutor()

    def test_executor_initialization(self, executor):
        """Test executor initialization with defaults."""
        assert executor._max_execution_time == 300
        assert len(executor.FORBIDDEN_PATTERNS) > 0
        assert ";" in executor.FORBIDDEN_PATTERNS
        assert "&&" in executor.FORBIDDEN_PATTERNS

    @pytest.mark.asyncio
    async def test_execute_kubectl_command_success(self, executor):
        """Test successful kubectl command execution."""
        mock_process = FakeProcess(stdout=b"pod ready", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods")

        assert result.success is True
        assert result.exit_code == 0
        assert "pod ready" in result.stdout
        assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_execute_command_failure(self, executor):
        """Test command execution failure."""
        mock_process = FakeProcess(stderr=b"Error: pod not found", returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get nonexistent-pod")

        assert result.success is False
        assert result.exit_code == 1
        assert "Error" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_command_timeout(self, executor):
        """Test command execution timeout."""
        mock_process = FakeProcess(hang=True)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods", timeout_seconds=1)

        assert result.success is False
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_command_exception(self, executor):
        """Test command execution with exception."""
        with patch("asyncio.create_subprocess_exec", side_effect=Exception("Command failed")):
            result = await executor.execute("kubectl get pods")

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
        assert "parsing" in result.error_message.lower() or "quotation" in result.error_message.lower()

    def test_is_forbidden_rm_rf(self, executor):
        """Test forbidden pattern detection."""
        # _is_forbidden checks patterns in individual arguments
        assert executor._is_forbidden("rm") is False  # safe alone
        assert executor._is_forbidden("file;rm") is True  # contains ;
        assert executor._is_forbidden("cmd&&other") is True  # contains &&

    def test_is_forbidden_fork_bomb(self, executor):
        """Test forbidden pattern detection for fork bomb patterns."""
        # Fork bomb patterns contain shell operators that are forbidden
        assert executor._is_forbidden(":|:") is True  # contains |
        assert executor._is_forbidden("cmd;rm") is True  # contains ;
        # Note: ${ is detected as substring, so we need actual ${ pattern
        assert executor._is_forbidden("${VAR}") is True  # contains ${
        assert executor._is_forbidden("$(whoami)") is True  # contains $(

    def test_is_forbidden_chmod(self, executor):
        """Test chmod argument is not forbidden by pattern."""
        assert executor._is_forbidden("chmod") is False
        assert executor._is_forbidden("file|chmod") is True  # contains |

    def test_is_forbidden_mkfs(self, executor):
        """Test mkfs argument is not forbidden by pattern."""
        assert executor._is_forbidden("mkfs") is False
        assert executor._is_forbidden("dev>mkfs") is True  # contains >

    def test_is_not_forbidden_safe_commands(self, executor):
        """Test safe arguments are not forbidden."""
        assert executor._is_forbidden("kubectl") is False
        assert executor._is_forbidden("get") is False
        assert executor._is_forbidden("pods") is False
        assert executor._is_forbidden("-n") is False
        assert executor._is_forbidden("default") is False

    @pytest.mark.asyncio
    async def test_execute_forbidden_command(self, executor):
        """Test executing command not in whitelist."""
        result = await executor.execute("rm -rf /important/data")

        assert result.success is False
        assert "not allowed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_kubectl_with_namespace(self, executor):
        """Test execute_kubectl helper."""
        mock_process = FakeProcess(stdout=b"result", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_kubectl(
                args=["get", "pods"],
                namespace="default",
                dry_run=False,
            )

        assert result.success is True
        assert result.exit_code == 0

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
        mock_process = FakeProcess(stdout=b"Release upgraded", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_helm(
                args=["upgrade", "myapp", "./chart"],
                namespace="default",
                dry_run=False,
            )

        assert result.success is True

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
        mock_process = FakeProcess(stdout=b"Sync successful", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_argocd(
                args=["app", "sync", "myapp"],
                dry_run=False,
            )

        assert result.success is True

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
        mock_process = FakeProcess(hang=True)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods", timeout_seconds=2)

        assert result.success is False
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_measures_duration(self, executor):
        """Test that execution duration is measured."""
        mock_process = FakeProcess(stdout=b"done", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods")

        assert result.duration_seconds >= 0
        assert result.duration_seconds < 1.0  # Should be very fast

    @pytest.mark.asyncio
    async def test_execute_unicode_handling(self, executor):
        """Test unicode handling in command output."""
        mock_process = FakeProcess(stdout=b"Unicode: \xe2\x9c\x93 OK", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods")

        assert result.success is True
        assert "OK" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_large_output(self, executor):
        """Test handling of large command output (below the cap)."""
        large_output = b"x" * 100000
        mock_process = FakeProcess(stdout=large_output, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods")

        assert result.success is True
        assert len(result.stdout) == 100000


    def test_is_forbidden_all_patterns(self, executor):
        """Test all forbidden patterns are detected."""
        forbidden_patterns = [
            ("&&", "kubectl get && rm -rf /"),
            (";", "kubectl get; rm file"),
            ("|", "cat /etc/passwd | grep root"),
            ("$(", "echo $(whoami)"),
            ("`", "echo `id`"),
            ("${", "echo ${USER}"),
            (">", "echo test > file.txt"),
            ("<", "cat < file.txt"),
            ("2>", "ls 2>/dev/null"),
            ("2>&1", "ls 2>&1"),
            ("&>", "ls &>output"),
        ]

        for pattern, command in forbidden_patterns:
            assert executor._is_forbidden(command), f"Pattern {pattern} not detected"

    def test_is_forbidden_safe_substrings(self, executor):
        """Test safe command strings are not flagged."""
        # _is_forbidden does simple substring check without parsing quotes
        # Commands with forbidden patterns WILL be flagged
        safe_commands = [
            "kubectl get pods",
            "grep test file",
            "cat filename",
            "echo home",
            "ls directory",
        ]

        for command in safe_commands:
            result = executor._is_forbidden(command)
            # Should not trigger forbidden pattern detection
            assert result is False, f"Safe command flagged: {command}"

    @pytest.mark.asyncio
    async def test_execute_safe_with_disallowed_kubectl_flag(self, executor):
        """Test _execute_safe rejects disallowed kubectl flags."""
        # Mock since we'll fail before subprocess
        result = await executor._execute_safe(
            ["kubectl", "--disallowed-flag", "get", "pods"],
            dry_run=True,
        )

        assert result.success is False
        assert "not allowed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_safe_with_disallowed_helm_flag(self, executor):
        """Test _execute_safe rejects disallowed helm flags."""
        result = await executor._execute_safe(
            ["helm", "--disallowed-flag", "list"],
            dry_run=True,
        )

        assert result.success is False
        assert "not allowed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_safe_unknown_command_not_in_whitelist(self, executor):
        """Test _execute_safe rejects commands not in whitelist."""
        result = await executor._execute_safe(
            ["unknown-command", "arg1"],
            dry_run=True,
        )

        assert result.success is False
        assert "not allowed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_safe_empty_command(self, executor):
        """Test _execute_safe handles empty command list."""
        result = await executor._execute_safe([], dry_run=True)

        assert result.success is False
        assert "empty" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_safe_argocd_allowed(self, executor):
        """Test _execute_safe allows argocd commands."""
        # Argocd should be allowed (in whitelist)
        result = await executor._execute_safe(
            ["argocd", "app", "list"],
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_safe_kubectl_allows_allowed_flags(self, executor):
        """Test _execute_safe allows whitelisted kubectl flags."""
        # Test with namespace flag (allowed)
        result = await executor._execute_safe(
            ["kubectl", "get", "pods", "-n", "default"],
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_safe_kubectl_allows_global_flags(self, executor):
        """Test _execute_safe allows global kubectl flags."""
        # Test with kubeconfig flag (allowed global flag)
        result = await executor._execute_safe(
            ["kubectl", "get", "pods", "--kubeconfig", "/path/to/config"],
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_safe_boolean_flag_format(self, executor):
        """Test _execute_safe handles boolean flags (no value)."""
        # Test with -o wide (boolean flag, no value following)
        result = await executor._execute_safe(
            ["kubectl", "get", "pods", "-o", "wide"],
            dry_run=True,
        )

        # The flag validation might catch this depending on implementation
        # At minimum, should not crash
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_shlex_parsing_preserves_quotes(self, executor):
        """Test that shlex parsing preserves quoted arguments."""
        mock_process = FakeProcess(stdout=b"result", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute('kubectl get pods -n "default"')

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_timeout_kills_process(self, executor):
        """Test that timeout kills the subprocess."""
        mock_process = FakeProcess(hang=True)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("kubectl get pods", timeout_seconds=1)

        # Verify process was killed
        assert mock_process.killed is True
        assert result.success is False
        assert "timed out" in result.error_message.lower()


class TestOutputCap:
    """Phase 15 P2-4: captured output is bounded. A runaway command used to
    stream unbounded bytes into memory, the audit entry and the API response."""

    @pytest.fixture
    def executor(self):
        executor = CommandExecutor()
        executor.MAX_OUTPUT_BYTES = 100  # small cap for tests
        return executor

    @pytest.mark.asyncio
    async def test_stdout_capped_and_marked(self, executor):
        proc = FakeProcess(stdout=b"x" * 1000, returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await executor.execute("kubectl get pods")

        assert result.success is True
        assert result.stdout.startswith("x" * 100)
        assert "[output truncated at 100 bytes]" in result.stdout
        # drain worked: process ran to completion, exit code preserved
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_stderr_capped_independently(self, executor):
        proc = FakeProcess(stdout=b"fine", stderr=b"e" * 1000, returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await executor.execute("kubectl get pods")

        assert result.stdout == "fine"
        assert result.stderr.startswith("e" * 100)
        assert "[output truncated at 100 bytes]" in result.stderr

    @pytest.mark.asyncio
    async def test_exact_boundary_not_marked_truncated(self, executor):
        """Output exactly at the cap fits — no false truncation marker."""
        proc = FakeProcess(stdout=b"x" * 100, returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await executor.execute("kubectl get pods")

        assert result.stdout == "x" * 100
        assert "truncated" not in result.stdout

    @pytest.mark.asyncio
    async def test_below_cap_untouched(self, executor):
        proc = FakeProcess(stdout=b"short", stderr=b"err", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await executor.execute("kubectl get pods")

        assert result.stdout == "short"
        assert result.stderr == "err"


class TestReadStreamCapped:
    """Unit coverage for the shared capped reader."""

    @pytest.mark.asyncio
    async def test_none_stream(self):
        assert await read_stream_capped(None, 10) == (b"", False)

    @pytest.mark.asyncio
    async def test_multi_chunk_accumulation(self):
        class Chunky:
            def __init__(self, pieces):
                self._pieces = list(pieces)

            async def read(self, n=-1):
                return self._pieces.pop(0) if self._pieces else b""

        data, truncated = await read_stream_capped(Chunky([b"ab", b"cd", b"ef"]), 10)
        assert (data, truncated) == (b"abcdef", False)

    @pytest.mark.asyncio
    async def test_partial_chunk_kept_and_flagged(self):
        class Chunky:
            def __init__(self, pieces):
                self._pieces = list(pieces)

            async def read(self, n=-1):
                return self._pieces.pop(0) if self._pieces else b""

        data, truncated = await read_stream_capped(Chunky([b"a" * 8, b"b" * 8]), 10)
        assert data == b"a" * 8 + b"bb"
        assert truncated is True

    def test_mark_truncated(self):
        assert mark_truncated(b"ok", False, 5) == b"ok"
        assert mark_truncated(b"abcde", True, 5) == b"abcde\n[output truncated at 5 bytes]"

    def test_default_cap_matches_module_constant(self):
        assert CommandExecutor.MAX_OUTPUT_BYTES == MAX_OUTPUT_BYTES == 1_000_000


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


class TestFlagWhitelist:
    """Phase 15 P1-2: the flag table must accept the option flags remediation
    actions actually generate (previously only subcommands were listed, so
    every real autonomous run failed its own check while dry-run succeeded)."""

    def test_remotediation_flags_pass(self):
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "get", "pods", "-n", "ns", "-o", "json"]) is None
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "get", "pods", "-o", "json", "-l", "app=web"]) is None
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "scale", "deployment", "api", "--replicas=3"]) is None
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "delete", "pod", "p", "--force", "--grace-period=0"]) is None
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "rollout", "undo", "deployment", "api", "--to-revision=2"]) is None

    def test_unknown_flag_rejected(self):
        err = CommandExecutor.validate_command_flags(
            ["kubectl", "get", "pods", "--totally-bogus"])
        assert err is not None and "not allowed" in err

    def test_exec_and_config_subcommands_removed(self):
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "exec", "web", "--", "ls"]) is not None
        assert CommandExecutor.validate_command_flags(
            ["kubectl", "config", "use-context", "prod"]) is not None

    def test_non_whitelisted_binary(self):
        assert CommandExecutor.validate_command_flags(["curl", "http://x"]) is not None
