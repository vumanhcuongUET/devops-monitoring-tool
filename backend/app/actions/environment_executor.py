"""Environment-Aware Command Executor with Service Account Isolation.

This module provides command execution with environment-specific service accounts:
- Development: Full admin access
- Staging: Operator access (create, modify, execute)
- Production: View-only or Scale-only access
- Production Read-Only: View-only access

SECURITY: All commands are executed using create_subprocess_exec with proper
argument lists to prevent shell injection. Environment variables are set
via the env parameter rather than shell string interpolation.
"""

import asyncio
import logging
import os
import shlex
import subprocess
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.governance.ai_rbac import ENVIRONMENT_PERMISSIONS, AIPermission
from app.actions.parser import ALLOWED_BINARIES
from app.models.actions import ExecutionResult
from app.utils.logging import sanitize_command

logger = logging.getLogger(__name__)


class ExecutionEnvironment(str, Enum):
    """Execution environments with different permission levels."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    PRODUCTION_READONLY = "production-read-only"


class ServiceAccountConfig:
    """Configuration for environment-specific service accounts.

    SECURITY NOTE:
    - Uses in-cluster config when available (no persistent credentials)
    - Kubeconfig paths are placeholders for local development
    - In production, always use in-cluster service account tokens
    """

    # Service account names per environment
    SERVICE_ACCOUNTS = {
        ExecutionEnvironment.DEVELOPMENT: "ai-dev-admin",
        ExecutionEnvironment.STAGING: "ai-staging-operator",
        ExecutionEnvironment.PRODUCTION: "ai-prod-operator",
        ExecutionEnvironment.PRODUCTION_READONLY: "ai-prod-viewer",
    }

    # Kubeconfig paths per environment (for local development only)
    KUBECONFIG_PATHS = {
        ExecutionEnvironment.DEVELOPMENT: "~/.kube/config-dev",
        ExecutionEnvironment.STAGING: "~/.kube/config-staging",
        ExecutionEnvironment.PRODUCTION: "~/.kube/config-prod",
        ExecutionEnvironment.PRODUCTION_READONLY: "~/.kube/config-prod-readonly",
    }

    # Cluster contexts per environment
    CLUSTER_CONTEXTS = {
        ExecutionEnvironment.DEVELOPMENT: "dev-cluster",
        ExecutionEnvironment.STAGING: "staging-cluster",
        ExecutionEnvironment.PRODUCTION: "prod-cluster",
        ExecutionEnvironment.PRODUCTION_READONLY: "prod-cluster",
    }

    # Token rotation settings
    TOKEN_ROTATION_INTERVAL_HOURS = 24  # Rotate tokens daily
    TOKEN_REFRESH_THRESHOLD_HOURS = 2  # Refresh 2 hours before expiry

    # In-cluster service account token path
    IN_CLUSTER_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    IN_CLUSTER_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    @classmethod
    def detect_in_cluster(cls) -> bool:
        """Detect if running in a Kubernetes cluster.

        Returns:
            True if in-cluster configuration is available
        """
        from pathlib import Path
        return Path(cls.IN_CLUSTER_TOKEN_PATH).exists()

    @classmethod
    def get_kubeconfig_path(cls, environment: ExecutionEnvironment) -> str:
        """Get the appropriate kubeconfig path for an environment.

        Args:
            environment: Target environment

        Returns:
            Kubeconfig path (in-cluster or file-based)
        """
        # Use in-cluster config if available
        if cls.detect_in_cluster():
            logger.debug("Using in-cluster Kubernetes configuration")
            return ""  # Empty string triggers in-cluster config

        # Fall back to file-based config for local development
        return str(Path(cls.KUBECONFIG_PATHS[environment]).expanduser())

    @classmethod
    def validate_credentials(cls, environment: ExecutionEnvironment) -> bool:
        """Validate that credentials are available for the environment.

        Args:
            environment: Target environment

        Returns:
            True if credentials are valid and accessible
        """
        if cls.detect_in_cluster():
            # In-cluster credentials are always valid
            return True

        # Check file-based kubeconfig
        kubeconfig_path = str(Path(cls.KUBECONFIG_PATHS[environment]).expanduser())
        if not Path(kubeconfig_path).exists():
            logger.warning(f"Kubeconfig not found: {kubeconfig_path}")
            return False

        # Verify file is readable
        try:
            Path(kubeconfig_path).chmod(0o600)  # Ensure restrictive permissions
            return True
        except Exception as e:
            logger.error(f"Failed to validate kubeconfig: {e}")
            return False


class EnvironmentAwareCommandExecutor:
    """Execute commands with environment-specific service accounts.

    This executor:
    - Uses different service accounts per environment
    - Enforces permission constraints
    - Logs all executions for audit
    - Supports dry-run mode for safety
    """

    def __init__(
        self,
        default_environment: ExecutionEnvironment = ExecutionEnvironment.PRODUCTION_READONLY,
        dry_run: bool = False,
        enable_logging: bool = True,
    ):
        """Initialize the executor.

        Args:
            default_environment: Default environment for executions
            dry_run: If True, simulate execution without running commands
            enable_logging: Enable execution logging
        """
        self.default_environment = default_environment
        self.dry_run = dry_run
        self.enable_logging = enable_logging
        self._execution_history: list[ExecutionResult] = []

    async def execute(
        self,
        command: str,
        environment: ExecutionEnvironment | None = None,
        required_permission: AIPermission | None = None,
        timeout_seconds: int = 30,
        dry_run: bool | None = None,
    ) -> ExecutionResult:
        """Execute a command with environment-specific service account.

        Args:
            command: Command to execute
            environment: Target environment (uses default if None)
            required_permission: Required permission for the operation
            timeout_seconds: Execution timeout
            dry_run: Override the executor's dry_run mode for this call
                (None = use the executor default)

        Returns:
            ExecutionResult

        Raises:
            PermissionError: If required permission not available
            ValueError: If command validation fails
            subprocess.TimeoutExpired: If command times out
        """
        env = environment or self.default_environment
        use_dry_run = self.dry_run if dry_run is None else dry_run

        # Validate permissions
        if required_permission:
            if not self._check_permission(env, required_permission):
                raise PermissionError(
                    f"Permission {required_permission.value} not allowed in {env.value}"
                )

        # Validate command
        if not self._validate_command(command):
            raise ValueError(f"Command validation failed: {command}")

        # Get environment-specific config
        service_account = ServiceAccountConfig.SERVICE_ACCOUNTS[env]
        kubeconfig = ServiceAccountConfig.get_kubeconfig_path(env)
        context = ServiceAccountConfig.CLUSTER_CONTEXTS.get(environment)

        # Validate credentials before execution
        if not ServiceAccountConfig.validate_credentials(env):
            raise RuntimeError(
                f"Invalid credentials for {env.value}. "
                f"Ensure kubeconfig exists or running in-cluster."
            )

        start_time = datetime.now(timezone.utc)

        try:
            if use_dry_run:
                sanitized_cmd = sanitize_command(command)
                logger.info(f"DRY RUN: Would execute in {env.value} with SA {service_account}: {sanitized_cmd}")
                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"DRY RUN: {command}",
                    stderr="",
                    duration_seconds=0,
                    environment=env.value,
                    command=command,
                )
            else:
                sanitized_cmd = sanitize_command(command)
                logger.info(f"Executing in {env.value} with SA {service_account}: {sanitized_cmd}")

                # Parse the command into arguments safely
                try:
                    cmd_args = shlex.split(command)
                except ValueError as e:
                    raise ValueError(f"Failed to parse command: {e}") from e

                # Stateless per-command context selection — never `kubectl config
                # use-context`, which mutates shared kubeconfig state (concurrent
                # actions could cross-apply each other's cluster context).
                if context and kubeconfig:
                    # File-based kubeconfig only; in-cluster config has no contexts.
                    binary = cmd_args[0].lower() if cmd_args else ""
                    if binary.startswith("kubectl"):
                        cmd_args = (
                            cmd_args[:1]
                            + ["--context", context, "--kubeconfig", kubeconfig]
                            + cmd_args[1:]
                        )
                    elif binary == "helm":
                        cmd_args = (
                            cmd_args[:1]
                            + ["--kube-context", context, "--kubeconfig", kubeconfig]
                            + cmd_args[1:]
                        )
                    # argocd has no context concept — runs as-is

                proc_env = os.environ.copy()
                proc_env["KUBECONFIG"] = kubeconfig

                process = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    env=proc_env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise subprocess.TimeoutExpired(command, timeout_seconds) from None

                result = ExecutionResult(
                    success=process.returncode == 0,
                    exit_code=process.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=(
                        datetime.now(timezone.utc) - start_time
                        ).total_seconds(),
                    environment=env.value,
                    command=command,
                )

        except Exception as e:
            logger.error(f"Execution failed in {env.value}: {e}")
            result = ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=(
                    datetime.now(timezone.utc) - start_time
                    ).total_seconds(),
                environment=env.value,
                command=command,
            )

        # Log execution
        if self.enable_logging:
            self._log_execution(result)

        # Store in history
        self._execution_history.append(result)

        return result

    def _check_permission(
        self,
        environment: ExecutionEnvironment,
        required_permission: AIPermission,
    ) -> bool:
        """Check if permission is allowed in environment.

        Args:
            environment: Target environment
            required_permission: Permission to check

        Returns:
            True if permission allowed
        """
        allowed_permissions = ENVIRONMENT_PERMISSIONS.get(
            environment,
            {AIPermission.VIEW},  # Default to view-only
        )
        return required_permission in allowed_permissions

    def _validate_command(self, command: str) -> bool:
        """Validate command for safety.

        Phase 12 S5: argv[0] must be in the shared ALLOWED_BINARIES whitelist
        (parser.py): only kubectl/helm/argocd pass, never an arbitrary binary.

        Args:
            command: Command to validate

        Returns:
            True if command is safe to execute
        """
        # S5 binary whitelist (argv[0] floor). Malformed input must fail the
        # validation (False), not raise: empty/whitespace command → empty argv;
        # unbalanced quotes → shlex ValueError.
        try:
            argv = shlex.split(command)
        except ValueError:
            logger.warning("Blocked command with unbalanced quoting")
            return False
        if not argv:
            logger.warning("Blocked empty command")
            return False
        if argv[0] not in ALLOWED_BINARIES:
            logger.warning(f"Blocked non-whitelisted binary: {argv[0]!r}")
            return False

        # Basic validation rules
        dangerous_patterns = [
            "rm -rf /",
            "mkfs.",
            "dd if=/dev/zero",
            ":(){ :|:& };:",  # Fork bomb
            "chmod 000",
        ]

        command_lower = command.lower()
        for pattern in dangerous_patterns:
            if pattern in command_lower:
                logger.warning(f"Blocked dangerous command pattern: {pattern}")
                return False

        return True

    def _log_execution(self, result: ExecutionResult) -> None:
        """Log execution result.

        Args:
            result: Execution result to log
        """
        log_level = logging.INFO if result.success else logging.WARNING
        logger.log(
            log_level,
            f"Command executed in {result.environment}: "
            f"success={result.success}, exit_code={result.exit_code}, "
            f"time_ms={(result.duration_seconds or 0) * 1000:.0f}"
        )

    def get_execution_history(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get execution history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of execution results as dictionaries
        """
        history = self._execution_history[-limit:] if limit > 0 else self._execution_history
        return [result.model_dump(mode="json") for result in reversed(history)]

    def get_environment_info(
        self,
        environment: ExecutionEnvironment,
    ) -> dict[str, str]:
        """Get environment configuration information.

        Args:
            environment: Target environment

        Returns:
            Dict with environment info
        """
        return {
            "environment": environment.value,
            "service_account": ServiceAccountConfig.SERVICE_ACCOUNTS.get(environment, "unknown"),
            "kubeconfig": ServiceAccountConfig.KUBECONFIG_PATHS.get(environment, "unknown"),
            "cluster_context": ServiceAccountConfig.CLUSTER_CONTEXTS.get(environment, "unknown"),
            "allowed_permissions": [
                perm.value
                for perm in ENVIRONMENT_PERMISSIONS.get(
                    environment,
                    {AIPermission.VIEW},
                )
            ],
        }

    def rotate_credentials(self, environment: ExecutionEnvironment) -> bool:
        """Rotate service account credentials.

        In production with in-cluster config:
        - Service account tokens are automatically refreshed by Kubernetes
        - This method validates the refresh mechanism

        For local development:
        - Warns about manual token rotation needs
        - Validates kubeconfig file permissions

        Args:
            environment: Target environment

        Returns:
            True if rotation/validation successful
        """
        try:
            if ServiceAccountConfig.detect_in_cluster():
                # In-cluster: Token rotation is automatic
                # Validate the current token is accessible
                token_path = Path(ServiceAccountConfig.IN_CLUSTER_TOKEN_PATH)
                if not token_path.exists():
                    logger.error("In-cluster token not accessible")
                    return False

                # Read token to ensure it's valid
                try:
                    token = token_path.read_text()
                    if len(token) < 10:
                        logger.error("In-cluster token appears invalid")
                        return False

                    logger.info(f"In-cluster credentials validated for {environment.value}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to read in-cluster token: {e}")
                    return False
            else:
                # Local development: Validate kubeconfig permissions
                kubeconfig_path = str(Path(ServiceAccountConfig.KUBECONFIG_PATHS[environment]).expanduser())

                # Set restrictive permissions (owner read-only)
                Path(kubeconfig_path).chmod(0o600)

                logger.warning(
                    f"Local development mode: Manual credential rotation may be needed. "
                    f"Ensure tokens for {environment.value} are current."
                )

                # Log rotation reminder
                self._log_rotation_reminder(environment)
                return True

        except Exception as e:
            logger.error(f"Credential rotation failed for {environment.value}: {e}")
            return False

    def _log_rotation_reminder(self, environment: ExecutionEnvironment) -> None:
        """Log a credential rotation reminder.

        Args:
            environment: Target environment
        """
        rotation_hours = ServiceAccountConfig.TOKEN_ROTATION_INTERVAL_HOURS
        logger.info(
            f"Security Reminder: Service account tokens for {environment.value} "
            f"should be rotated every {rotation_hours} hours. "
            f"Configure automated token rotation in production."
        )


# Singleton instance with thread-safe initialization
_executor_instance: EnvironmentAwareCommandExecutor | None = None
_executor_lock = threading.Lock()


def get_executor(
    environment: ExecutionEnvironment | None = None,
    dry_run: bool = False,
) -> EnvironmentAwareCommandExecutor:
    """Get the executor singleton instance (thread-safe).

    This function implements the double-check locking pattern for thread-safe
    singleton initialization.

    Args:
        environment: Default environment
        dry_run: Dry run mode

    Returns:
        Executor instance
    """
    global _executor_instance

    # Double-check locking pattern for thread safety
    if _executor_instance is None:
        with _executor_lock:
            # Check again inside the lock
            if _executor_instance is None:
                default_env = environment or ExecutionEnvironment.PRODUCTION_READONLY
                _executor_instance = EnvironmentAwareCommandExecutor(
                    default_environment=default_env,
                    dry_run=dry_run,
                )
                logger.info(f"Executor singleton created for {default_env.value}")

    return _executor_instance


def reset_executor() -> None:
    """Reset the executor singleton (for testing/reconfiguration).

    This allows creating a new executor instance. Use with caution in production.
    """
    global _executor_instance

    with _executor_lock:
        if _executor_instance is not None:
            # Flush execution history before resetting
            _executor_instance._execution_history.clear()
            _executor_instance = None
            logger.info("Executor singleton reset")
