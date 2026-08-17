"""Command executor for running kubectl, helm, and argocd commands."""

import asyncio
import logging
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Optional

from app.models.actions import CommandType, ExecutionResult

logger = logging.getLogger(__name__)


class CommandExecutor:
    """Execute shell commands with safety constraints."""

    def __init__(self):
        self._max_execution_time = 300  # 5 minutes default
        self._forbidden_commands = [
            "rm -rf",
            "mkfs",
            ":(){ :|:& };:",  # Fork bomb
            "chmod 000",
        ]

    async def execute(
        self,
        command: str,
        dry_run: bool = False,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """Execute a command and return the result."""
        if dry_run:
            return await self._dry_run(command)

        # Check for forbidden commands
        if self._is_forbidden(command):
            return ExecutionResult(
                success=False,
                error_message="Command contains forbidden pattern",
                timestamp=datetime.now(timezone.utc),
            )

        # Execute the command
        start_time = datetime.now(timezone.utc)
        try:
            process = await asyncio.create_subprocess_shell(
                command,
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
            # Kill the process
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

    async def _dry_run(self, command: str) -> ExecutionResult:
        """Perform a dry run validation of the command."""
        # For dry run, we just validate the command syntax
        try:
            # Try to parse the command
            shlex.split(command)
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout="[DRY RUN] Command validation passed",
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

    def _is_forbidden(self, command: str) -> bool:
        """Check if command contains forbidden patterns."""
        command_lower = command.lower()
        for forbidden in self._forbidden_commands:
            if forbidden.lower() in command_lower:
                logger.warning(f"Command contains forbidden pattern: {forbidden}")
                return True
        return False

    async def execute_kubectl(
        self,
        args: list[str],
        namespace: Optional[str] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute a kubectl command with proper context."""
        command = "kubectl"
        if namespace:
            command += f" -n {namespace}"
        command += " " + " ".join(args)

        return await self.execute(command, dry_run=dry_run)

    async def execute_helm(
        self,
        args: list[str],
        namespace: Optional[str] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute a helm command."""
        command = "helm"
        if namespace:
            command += f" --namespace {namespace}"
        command += " " + " ".join(args)

        return await self.execute(command, dry_run=dry_run)

    async def execute_argocd(
        self,
        args: list[str],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute an argocd command."""
        command = "argocd " + " ".join(args)
        return await self.execute(command, dry_run=dry_run)


# Singleton instance
_executor: Optional[CommandExecutor] = None


def get_command_executor() -> CommandExecutor:
    """Get or create the singleton CommandExecutor instance."""
    global _executor
    if _executor is None:
        _executor = CommandExecutor()
    return _executor
