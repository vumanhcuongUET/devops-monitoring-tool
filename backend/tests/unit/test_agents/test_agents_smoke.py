"""Agents subsystem smoke tests."""

import importlib

from app.agents.orchestrator import AgentOrchestrator

AGENT_MODULES = (
    "app.agents.base",
    "app.agents.metrics_agent",
    "app.agents.log_agent",
    "app.agents.k8s_agent",
    "app.agents.performance_agent",
    "app.agents.security_agent",
    "app.agents.cost_agent",
)


def test_all_agent_modules_import():
    """Regression gate: k8s_agent corruption must not kill the agents package."""
    for mod in AGENT_MODULES:
        importlib.import_module(mod)


def test_orchestrator_class_exists():
    assert AgentOrchestrator is not None


def test_base_agent_uses_async_client():
    from app.agents import base

    assert base.AsyncAnthropic is not None
