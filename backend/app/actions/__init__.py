"""Actions package for Phase 2: Human-in-the-loop & Action Proposer."""

from app.actions.autonomous_executor import (
    AutonomousExecutor,
    RateLimiter,
    SafetyChecker,
    get_autonomous_executor,
)
from app.actions.engine import get_action_engine
from app.actions.environment_executor import (
    EnvironmentAwareCommandExecutor,
    ExecutionEnvironment,
    ExecutionResult,
    get_executor,
)
from app.actions.executor import get_command_executor
from app.actions.parser import get_command_parser

# Phase 4: Autonomous Reliability
from app.actions.remediation_actions import (
    DeleteCrashLoopPodAction,
    RemediationAction,
    RemediationActionFactory,
    RemediationActionType,
    RestartDeploymentAction,
    RollbackDeploymentAction,
    ScaleDeploymentAction,
)
from app.actions.validator import get_command_validator

__all__ = [
    # Phase 2
    "get_action_engine",
    "get_command_parser",
    "get_command_validator",
    "get_command_executor",
    "EnvironmentAwareCommandExecutor",
    "ExecutionEnvironment",
    "ExecutionResult",
    "get_executor",
    # Phase 4
    "RemediationAction",
    "DeleteCrashLoopPodAction",
    "ScaleDeploymentAction",
    "RollbackDeploymentAction",
    "RestartDeploymentAction",
    "RemediationActionType",
    "RemediationActionFactory",
    "AutonomousExecutor",
    "get_autonomous_executor",
    "RateLimiter",
    "SafetyChecker",
]
