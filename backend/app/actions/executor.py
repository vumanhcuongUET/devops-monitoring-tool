"""Command executor for running kubectl, helm, and argocd commands."""

import asyncio
import logging
import shlex
from datetime import datetime, timezone

from app.models.actions import ExecutionResult

logger = logging.getLogger(__name__)

# Phase 15: captured stdout/stderr per stream is capped (a runaway command
# used to stream unbounded bytes into memory, the audit entry and the API
# response). Overflow is drained to EOF and discarded so the process still
# runs to completion — only the capture is bounded.
MAX_OUTPUT_BYTES = 1_000_000

_TRUNCATION_MARKER = b"\n[output truncated at %d bytes]"


async def read_stream_capped(stream, limit: int = MAX_OUTPUT_BYTES) -> tuple[bytes, bool]:
    """Read a subprocess stream to EOF, keeping at most ``limit`` bytes.

    Returns ``(data, truncated)``. Bytes past the limit are drained and
    discarded so the child never blocks on a full pipe.
    """
    if stream is None:
        return b"", False
    buf = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if len(buf) < limit:
            space = limit - len(buf)
            buf += chunk[:space]
            if len(chunk) > space:
                truncated = True
        else:
            truncated = True
    return bytes(buf), truncated


def mark_truncated(data: bytes, truncated: bool, limit: int = MAX_OUTPUT_BYTES) -> bytes:
    """Append the truncation marker when the capture hit the cap."""
    if truncated:
        return data + (_TRUNCATION_MARKER % limit)
    return data


class CommandExecutor:
    """Execute shell commands with safety constraints."""

    # Whitelist of allowed commands
    ALLOWED_COMMANDS = {
        "kubectl": {
            # Subcommands plus the option flags remediation actions actually
            # generate (`-o json`, `-l selector`, `--replicas`,
            # `--grace-period`, `--force`, `--type`, `--to-revision`,
            # `--cascade`, `--patch`). Before Phase 15 only subcommands were
            # listed here, so every real autonomous remediation failed its own
            # flag check while dry-run (which skips it) reported success.
            # `exec` and `config` were removed: exec runs arbitrary in-pod
            # commands, and config use-context is superseded by the
            # stateless --context flag.
            "allowed_flags": ["get", "describe", "logs", "apply", "delete", "create",
                             "top", "auth", "rollout", "scale",
                             "o", "output", "l", "selector", "filename", "f",
                             "force", "grace-period", "replicas", "type",
                             "to-revision", "cascade", "patch", "p", "wait",
                             "revision", "record"],
            "allowed_global_flags": ["-n", "--namespace", "--context", "--kubeconfig"],
        },
        "helm": {
            "allowed_flags": ["list", "install", "upgrade", "uninstall", "status", "ls",
                             "history", "rollback", "get", "repo",
                             "reuse-values", "set", "version", "wait"],
            "allowed_global_flags": ["-n", "--namespace", "--kubeconfig"],
        },
        "argocd": {
            "allowed_flags": ["app", "repository", "project", "cluster", "account"],
            "allowed_global_flags": [],
        },
    }

    @classmethod
    def validate_command_flags(cls, cmd_args: list[str]) -> str | None:
        """Shared flag-whitelist check; returns an error string or None.

        Used by CommandExecutor._execute_safe and (Phase 15) by the
        env-aware executor's _validate_command so both execution paths
        enforce the same table.
        """
        if not cmd_args:
            return None
        binary = cmd_args[0].lower()
        config = cls.ALLOWED_COMMANDS.get(binary)
        if config is None:
            return f"Command '{binary}' not in whitelist"
        allowed = set(config["allowed_flags"])
        for g in config["allowed_global_flags"]:
            allowed.add(g)
            allowed.add(g.lstrip("-"))
        # The first positional argument is the subcommand — it must be
        # whitelisted explicitly (`kubectl exec`/`config` are not).
        if len(cmd_args) > 1 and not cmd_args[1].startswith("-"):
            if cmd_args[1] not in config["allowed_flags"]:
                return f"Subcommand '{cmd_args[1]}' is not allowed for command '{binary}'"
        i = 1
        while i < len(cmd_args):
            arg = cmd_args[i]
            if arg.startswith("-"):
                key = arg.split("=", 1)[0].lstrip("-")
                if not key:
                    return f"Separator '{arg}' is not allowed for command '{binary}'"
                if key not in allowed:
                    return f"Flag '{arg}' is not allowed for command '{binary}'"
                # skip the value of a --flag value pair
                if "=" not in arg and i + 1 < len(cmd_args) and not cmd_args[i + 1].startswith("-"):
                    i += 1
            i += 1
        return None

    # Forbidden command patterns (additional layer of defense)
    FORBIDDEN_PATTERNS = [
        "&&",
        ";",
        "|",
        "$(",
        "`",
        "${",
        ">",
        "<",
        "2>",
        "2>&1",
        "&>",
    ]

    def __init__(self):
        self._max_execution_time = 300  # 5 minutes default

    # Kept as a class attribute for callers that reference it there.
    MAX_OUTPUT_BYTES = MAX_OUTPUT_BYTES

    async def execute(
        self,
        command: str,
        dry_run: bool = False,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """Execute a command safely by parsing it into arguments.

        WARNING: This method takes a string command but safely parses it using
        shlex.split() to prevent shell injection. The parsed arguments are then
        passed directly to the binary without shell interpretation.

        For new code, prefer using execute_kubectl(), execute_helm(), or
        execute_argocd() which take argument lists directly.
        """
        # Parse command string safely
        try:
            cmd_args = shlex.split(command)
        except ValueError as e:
            return ExecutionResult(
                success=False,
                error_message=f"Command parsing failed: {e}",
                timestamp=datetime.now(timezone.utc),
            )

        # Validate parsed arguments
        if not cmd_args:
            return ExecutionResult(
                success=False,
                error_message="Empty command after parsing",
                timestamp=datetime.now(timezone.utc),
            )

        # Check for forbidden patterns in parsed arguments
        for arg in cmd_args:
            if self._is_forbidden(arg):
                return ExecutionResult(
                    success=False,
                    error_message=f"Command contains forbidden pattern in argument: {arg}",
                    timestamp=datetime.now(timezone.utc),
                )

        # Execute using safe method
        return await self._execute_safe(cmd_args, dry_run=dry_run, timeout_seconds=timeout_seconds)

    def _is_forbidden(self, arg: str) -> bool:
        """Check if a single argument contains forbidden patterns."""
        arg_lower = arg.lower()
        for forbidden in self.FORBIDDEN_PATTERNS:
            if forbidden.lower() in arg_lower:
                logger.warning(f"Argument contains forbidden pattern '{forbidden}' in: {arg[:50]}...")
                return True
        return False

    async def execute_kubectl(
        self,
        args: list[str],
        namespace: str | None = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute a kubectl command with proper context."""
        # Build command as list to prevent injection
        cmd_args = ["kubectl"]
        if namespace:
            cmd_args.extend(["-n", namespace])
        cmd_args.extend(args)

        return await self._execute_safe(cmd_args, dry_run=dry_run)

    async def execute_helm(
        self,
        args: list[str],
        namespace: str | None = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute a helm command."""
        # Build command as list to prevent injection
        cmd_args = ["helm"]
        if namespace:
            cmd_args.extend(["--namespace", namespace])
        cmd_args.extend(args)

        return await self._execute_safe(cmd_args, dry_run=dry_run)

    async def execute_argocd(
        self,
        args: list[str],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute an argocd command."""
        # Build command as list to prevent injection
        cmd_args = ["argocd"] + args
        return await self._execute_safe(cmd_args, dry_run=dry_run)

    async def _execute_safe(
        self,
        cmd_args: list[str],
        dry_run: bool = False,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """Execute command safely using subprocess with argument list.

        This prevents shell injection by avoiding shell interpretation.
        Validates that only whitelisted commands can be executed.
        """
        # Validate command is in whitelist
        if not cmd_args:
            return ExecutionResult(
                success=False,
                error_message="Empty command list",
                timestamp=datetime.now(timezone.utc),
            )

        command_name = cmd_args[0]
        if command_name not in self.ALLOWED_COMMANDS:
            allowed = ", ".join(self.ALLOWED_COMMANDS.keys())
            logger.error(f"Command '{command_name}' not in whitelist. Allowed: {allowed}")
            return ExecutionResult(
                success=False,
                error_message=f"Command '{command_name}' is not allowed. Allowed commands: {allowed}",
                timestamp=datetime.now(timezone.utc),
            )

        # Validate flags and arguments against the shared whitelist table
        # (also enforced by the env-aware executor since Phase 15)
        flag_error = self.validate_command_flags(cmd_args)
        if flag_error is not None:
            logger.error(f"{flag_error}")
            return ExecutionResult(
                success=False,
                error_message=flag_error,
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            return await self._dry_run_safe(cmd_args)

        start_time = datetime.now(timezone.utc)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Phase 15: capture is capped per stream (see read_stream_capped).
            limit = self.MAX_OUTPUT_BYTES

            (stdout, out_trunc), (stderr, err_trunc) = await asyncio.wait_for(
                asyncio.gather(
                    read_stream_capped(process.stdout, limit),
                    read_stream_capped(process.stderr, limit),
                ),
                timeout=timeout_seconds,
            )
            await process.wait()

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            stdout = mark_truncated(stdout, out_trunc, limit)
            stderr = mark_truncated(stderr, err_trunc, limit)

            return ExecutionResult(
                success=process.returncode == 0,
                exit_code=process.returncode,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=duration,
                timestamp=datetime.now(timezone.utc),
            )

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass

            return ExecutionResult(
                success=False,
                error_message=f"Command timed out after {timeout_seconds} seconds",
                duration_seconds=timeout_seconds,
                timestamp=datetime.now(timezone.utc),
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ExecutionResult(
                success=False,
                error_message=str(e),
                duration_seconds=duration,
                timestamp=datetime.now(timezone.utc),
            )

    async def _dry_run_safe(self, cmd_args: list[str]) -> ExecutionResult:
        """Perform a dry run validation of the command list."""
        # Validate that all arguments are strings
        try:
            for arg in cmd_args:
                if not isinstance(arg, str):
                    raise ValueError(f"Argument must be string, got {type(arg)}")
                # Check for shell injection patterns
                for forbidden in self.FORBIDDEN_PATTERNS:
                    if forbidden in arg:
                        raise ValueError(f"Argument contains forbidden pattern: {forbidden}")

            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Command validation passed: {' '.join(cmd_args)}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        except ValueError as e:
            return ExecutionResult(
                success=False,
                error_message=f"Command validation failed: {e}",
                timestamp=datetime.now(timezone.utc),
            )


# Singleton instance
_executor: CommandExecutor | None = None


def get_command_executor() -> CommandExecutor:
    """Get or create the singleton CommandExecutor instance."""
    global _executor
    if _executor is None:
        _executor = CommandExecutor()
    return _executor
