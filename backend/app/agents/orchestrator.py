"""
Agent Orchestrator

Coordinates multiple specialized agents to provide comprehensive analysis.
Implements consensus voting and result aggregation.
"""

import asyncio
import inspect
import time
import logging
from datetime import datetime
from typing import Any

from .base import AgentResponse, BaseAgent
from .cost_agent import CostOptimizationAgent
from .k8s_agent import KubernetesAgent
from .log_agent import LogAnalysisAgent
from .metrics_agent import MetricsAgent
from .model_selector import ModelSelector
from .performance_agent import PerformanceAgent
from .security_agent import SecurityAgent

logger = logging.getLogger(__name__)

# Which context keys each agent actually consumes — used to score that
# agent's input complexity independently (log volume says nothing about
# the security agent's workload).
_AGENT_CONTEXT_KEYS: dict[str, tuple[str, ...]] = {
    "log": ("logs", "log_entries"),
    "metrics": ("metrics", "prometheus_data"),
    "k8s": ("k8s_state", "cluster_state"),
    "cost": ("resources", "cost_data"),
    "security": ("security_data", "vulnerabilities"),
    "performance": ("performance_data", "traces"),
}

# Request-level flags the selector's complexity scoring reacts to.
_COMPLEXITY_FLAGS = (
    "requires_deep_analysis",
    "multi_hop_reasoning",
    "complex_correlation",
    "cost_critical",
)


class AgentOrchestrator:
    """
    Coordinates multiple specialized AI agents for comprehensive analysis.

    Features:
    - Automatic agent selection based on context
    - Parallel agent execution
    - Consensus voting for critical decisions
    - Result aggregation and prioritization
    - Fallback to simpler agents if complex ones fail
    """

    def __init__(self, model_selector: ModelSelector | None = None):
        """Initialize the orchestrator with all available agents."""
        self.agents: dict[str, BaseAgent] = {
            "log": LogAnalysisAgent(),
            "metrics": MetricsAgent(),
            "k8s": KubernetesAgent(),
            "cost": CostOptimizationAgent(),
            "security": SecurityAgent(),
            "performance": PerformanceAgent(),
        }
        self.model_selector = model_selector
        self._execution_history: list[dict] = []

    async def analyze(
        self,
        context: dict[str, Any],
        agents: list[str] | None = None,
        consensus_threshold: float = 0.6,
    ) -> dict[str, Any]:
        """
        Run analysis with relevant agents.

        Args:
            context: Analysis context containing logs, metrics, k8s state, etc.
            agents: Specific agents to run (None = auto-select)
            consensus_threshold: Minimum agreement ratio for consensus

        Returns:
            Aggregated analysis results with consensus information
        """
        start_time = datetime.utcnow()

        # Determine which agents to run
        if agents is None:
            agents = self._determine_agents(context)

        if not agents:
            logger.warning("No agents selected for analysis")
            return {
                "error": "No relevant agents for provided context",
                "agents_used": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

        logger.info(f"Running analysis with agents: {agents}")

        # Run agents in parallel
        agent_results, agent_models = await self._run_agents_parallel(agents, context)

        # Aggregate results
        aggregated = self._aggregate_results(agent_results)

        # Check if consensus is needed
        if self._needs_consensus(aggregated, consensus_threshold):
            consensus = self._vote_on_results(agent_results)
            aggregated["consensus"] = consensus

        # Add metadata
        aggregated.update(
            {
                "agents_used": agents,
                "agents_successful": sum(
                    1 for r in agent_results if r.is_successful()
                ),
                "total_agents": len(agents),
                "execution_time": (datetime.utcnow() - start_time).total_seconds(),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        if self.model_selector:
            aggregated["models"] = agent_models

        # Track execution
        self._execution_history.append(
            {
                "context_keys": list(context.keys()),
                "agents": agents,
                "success_count": aggregated["agents_successful"],
                "models": agent_models if self.model_selector else None,
                "timestamp": start_time.isoformat(),
            }
        )

        return aggregated

    def _determine_agents(self, context: dict[str, Any]) -> list[str]:
        """Determine which agents are relevant for the given context."""
        selected = []

        # Log agent: check for log data
        if context.get("logs") or context.get("log_entries"):
            selected.append("log")

        # Metrics agent: check for metrics data
        if context.get("metrics") or context.get("prometheus_data"):
            selected.append("metrics")

        # Kubernetes agent: check for k8s state
        if context.get("k8s_state") or context.get("cluster_state"):
            selected.append("k8s")

        # Cost agent: check for resources or cost data
        if context.get("resources") or context.get("cost_data"):
            selected.append("cost")

        # Security agent: check for security data or resources
        if context.get("security_data") or context.get("vulnerabilities"):
            selected.append("security")

        # Performance agent: check for performance data or traces
        if context.get("performance_data") or context.get("traces"):
            selected.append("performance")

        return selected

    def _select_model_for(self, agent_name: str, context: dict[str, Any]) -> str | None:
        """
        Pick the model tier for one agent from that agent's own input.

        Complexity is scored on the sub-context the agent actually reads
        (log volume, metric series count, data sources), so a huge log
        batch doesn't push the security agent onto Opus. Returns None when
        no selector is attached — agents then keep their configured model.
        """
        if self.model_selector is None:
            return None

        keys = _AGENT_CONTEXT_KEYS.get(agent_name)
        sub_context = {k: context[k] for k in keys if k in context} if keys else {}
        if not sub_context:
            sub_context = dict(context)
        else:
            # Request-level complexity flags apply to every agent's scoring.
            for flag in _COMPLEXITY_FLAGS:
                if flag in context:
                    sub_context[flag] = context[flag]

        try:
            return self.model_selector.select_model(sub_context)
        except Exception as e:
            logger.warning(f"Model selection failed for {agent_name}: {e}")
            return None

    @staticmethod
    def _accepts_model_override(agent: BaseAgent) -> bool:
        """True if agent.analyze() takes a `model` parameter (or **kwargs)."""
        try:
            params = inspect.signature(agent.analyze).parameters
        except (TypeError, ValueError):
            return False
        if "model" in params:
            return True
        return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    async def _run_agents_parallel(
        self, agent_names: list[str], context: dict[str, Any]
    ) -> tuple[list[AgentResponse], dict[str, str | None]]:
        """Run multiple agents in parallel, each on its selected model tier."""
        tasks = []
        models: dict[str, str | None] = {}

        for name in agent_names:
            agent = self.agents.get(name)
            if agent:
                model = self._select_model_for(name, context)
                models[name] = model
                tasks.append(self._run_agent_safely(agent, context, model))
            else:
                logger.warning(f"Agent not found: {name}")

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, converting exceptions to error responses
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Agent {agent_names[i]} failed: {result}")
                processed_results.append(
                    AgentResponse(
                        agent_name=agent_names[i],
                        insights={},
                        confidence=0.0,
                        error=str(result),
                    )
                )
            elif isinstance(result, AgentResponse):
                processed_results.append(result)
            else:
                logger.error(f"Unexpected result from agent {agent_names[i]}: {type(result)}")
                processed_results.append(
                    AgentResponse(
                        agent_name=agent_names[i],
                        insights={},
                        confidence=0.0,
                        error="Unexpected response type",
                    )
                )

        return processed_results, models

    async def _run_agent_safely(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        model: str | None = None,
    ) -> AgentResponse:
        """Run a single agent with timeout and error handling."""
        from app.metrics import AGENT_DURATION, AGENT_INVOCATIONS, AGENT_TIMEOUTS

        if model is not None and self._accepts_model_override(agent):
            invocation = agent.analyze(context, model=model)
        else:
            invocation = agent.analyze(context)

        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                invocation,
                timeout=agent.timeout,
            )
        except asyncio.TimeoutError:
            logger.error(f"Agent {agent.name} timed out")
            AGENT_INVOCATIONS.labels(agent.name, "timeout").inc()
            AGENT_TIMEOUTS.labels(agent.name).inc()
            return AgentResponse(
                agent_name=agent.name,
                insights={},
                confidence=0.0,
                error="Analysis timed out",
            )
        except Exception as e:
            AGENT_INVOCATIONS.labels(agent.name, "error").inc()
            logger.error(f"Agent {agent.name} failed: {e}")
            raise
        AGENT_DURATION.labels(agent.name).observe(time.monotonic() - started)
        AGENT_INVOCATIONS.labels(agent.name, "success").inc()
        return result

    def _aggregate_results(
        self, agent_results: list[AgentResponse]
    ) -> dict[str, Any]:
        """Aggregate results from multiple agents."""
        aggregated = {
            "agents": {},
            "insights": {},
            "recommendations": [],
            "confidence": 0.0,
            "errors": [],
        }

        # Collect individual agent results
        for result in agent_results:
            agent_name = result.agent_name
            aggregated["agents"][agent_name] = result.to_dict()

            if result.is_successful():
                # Merge insights
                aggregated["insights"][agent_name] = result.insights

                # Collect recommendations
                aggregated["recommendations"].extend(result.recommendations)
            else:
                aggregated["errors"].append(
                    {"agent": agent_name, "error": result.error}
                )

        # Calculate overall confidence (average of successful agents)
        successful_confidences = [
            r.confidence
            for r in agent_results
            if r.is_successful() and r.confidence > 0
        ]
        if successful_confidences:
            aggregated["confidence"] = sum(successful_confidences) / len(
                successful_confidences
            )

        # Deduplicate and prioritize recommendations
        aggregated["recommendations"] = self._deduplicate_recommendations(
            aggregated["recommendations"]
        )

        return aggregated

    def _needs_consensus(
        self, aggregated: dict[str, Any], threshold: float
    ) -> bool:
        """
        Determine if consensus voting is needed.

        Consensus is needed when:
        - Low overall confidence
        - Conflicting recommendations from agents
        - Critical findings with low confidence
        """
        # Low confidence threshold
        if aggregated["confidence"] < threshold:
            return True

        # Check for conflicting recommendations
        recommendations = aggregated["recommendations"]
        if len(recommendations) > 5:  # Many different recommendations
            return True

        # Check for critical findings with low confidence
        for _agent_name, agent_data in aggregated["agents"].items():
            if (
                agent_data.get("confidence", 0) < 0.7
                and agent_data.get("insights", {}).get("overall_risk") == "critical"
            ):
                return True

        return False

    def _vote_on_results(self, agent_results: list[AgentResponse]) -> dict[str, Any]:
        """
        Implement consensus voting among agents.

        Uses majority voting for recommendations and weighted voting for findings.
        """
        consensus = {
            "recommendations": {},
            "findings": {},
            "agreement_level": 0.0,
        }

        # Vote on recommendations
        recommendation_votes: dict[str, int] = {}
        for result in agent_results:
            if result.is_successful():
                for rec in result.recommendations:
                    recommendation_votes[rec] = (
                        recommendation_votes.get(rec, 0) + 1
                    )

        # Find recommendations with majority agreement
        total_agents = len(agent_results)
        majority = total_agents // 2 + 1

        for rec, votes in recommendation_votes.items():
            if votes >= majority:
                consensus["recommendations"][rec] = {
                    "votes": votes,
                    "agreement": votes / total_agents,
                }

        # Calculate overall agreement level
        if recommendation_votes:
            max_votes = max(recommendation_votes.values())
            consensus["agreement_level"] = max_votes / total_agents

        return consensus

    def _deduplicate_recommendations(
        self, recommendations: list[str]
    ) -> list[str]:
        """Deduplicate and prioritize recommendations."""
        # Simple deduplication
        seen = set()
        unique = []
        for rec in recommendations:
            # Normalize for comparison
            normalized = rec.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(rec)

        # Prioritize by keyword
        priority_keywords = ["critical", "urgent", "immediate", "security"]
        prioritized = []

        # Add high-priority first
        for rec in unique:
            if any(keyword in rec.lower() for keyword in priority_keywords):
                prioritized.append(rec)

        # Add remaining
        for rec in unique:
            if rec not in prioritized:
                prioritized.append(rec)

        return prioritized

    async def health_check(self) -> dict[str, Any]:
        """Check health of all agents."""
        health = {}

        for name, agent in self.agents.items():
            try:
                agent_health = await agent.health_check()
                health[name] = agent_health
            except Exception as e:
                health[name] = {
                    "agent": name,
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }

        return {
            "orchestrator": "healthy",
            "agents": health,
            "total_agents": len(self.agents),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_execution_history(self) -> list[dict]:
        """Get recent execution history."""
        return self._execution_history[-100:]  # Last 100 executions
