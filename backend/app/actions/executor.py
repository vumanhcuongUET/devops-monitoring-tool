"""Command executor for running kubectl, helm, and argocd commands."""

import asyncio
import logging
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Optional, List

from app.models.actions import CommandType, ExecutionResult

logger = logging.getLogger(__name__)


class CommandExecutor:
    """Execute shell commands with safety constraints."""

    # Whitelist of allowed commands
    ALLOWED_COMMANDS = {
        "kubectl": {
            "allowed_flags": ["get", "describe", "logs", "apply", "delete", "create",
                             "config", "top", "auth", "rollout", "scale", "exec"],
            "allowed_global_flags": ["-n", "--namespace", "--context", "--kubeconfig"],
        },
        "helm": {
            "allowed_flags": ["list", "install", "upgrade", "uninstall", "status", "ls",
                             "history", "rollback", "get", "repo"],
            "allowed_global_flags": ["-n", "--namespace", "--kubeconfig"],
        },
        "argocd": {
            "allowed_flags": ["app", "repository", "project", "cluster", "account"],
            "allowed_global_flags": [],
        },
    }

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
        namespace: Optional[str] = None,
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
        namespace: Optional[str] = None,
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
        """
        if dry_run:
            return await self._dry_run_safe(cmd_args)

        start_time = datetime.now(timezone.utc)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            return ExecutionResult(
                success=process.returncode == 0,
                exit_code=process.returncode,
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
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
_executor: Optional[CommandExecutor] = None


def get_command_executor() -> CommandExecutor:
    """Get or create the singleton CommandExecutor instance."""
    global _executor
    if _executor is None:
        _executor = CommandExecutor()
    return _executor
