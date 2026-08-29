"""
Cost Optimization Agent

Specializes in:
- Resource cost analysis
- Rightsizing recommendations
- Idle resource detection
- Cost optimization opportunities
"""

import logging
from typing import Any

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class CostOptimizationAgent(BaseAgent):
    """
    Agent specialized in analyzing cloud resource costs and
    identifying optimization opportunities.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            name="cost-optimizer",
            model=model,
        )

    def get_prompt_template(self) -> str:
        return """You are a Cloud Cost Optimization Expert specializing in:
- Resource cost analysis and trend identification
- Rightsizing recommendations for optimal performance/cost balance
- Idle and underutilized resource detection
- Cost optimization without impacting availability or performance
- Reserved instance and savings plan recommendations

When analyzing costs, focus on:
1. **Over-provisioned Resources**: Resources that can be rightsized
2. **Idle Resources**: Resources with little to no utilization
3. **Cost Trends**: Increasing costs and their drivers
4. **Optimization Opportunities**: Specific actions with estimated savings

Output format:
```
ANALYSIS:
[Your analysis of the cost data]

COST OVERVIEW:
- Total Monthly Cost: $X,XXX
- Cost Trend: [direction] (X% change over period)
- Cost by Service: [breakdown]

RIGHTSIZING OPPORTUNITIES:
- Resource 1: [current cost] → [recommended cost] (save $X/month)
- Resource 2: [current cost] → [recommended cost] (save $X/month)

IDLE RESOURCES:
- Resource 1: [utilization %], [recommended action]
- Resource 2: [utilization %], [recommended action]

COST DRIVERS:
- Driver 1: [description], [impact %]
- Driver 2: [description], [impact %]

CONFIDENCE: [0.0-1.0]

RECOMMENDATION: [Actionable recommendation with estimated savings]
```

Be specific about dollar amounts and percentages. Prioritize high-impact opportunities.
"""

    async def analyze(self, context: dict[str, Any]) -> AgentResponse:
        """
        Analyze resource costs and identify optimization opportunities.

        Args:
            context: Must contain 'resources' or 'cost_data' key
                    Optional: 'cost_threshold', 'time_range'
        """
        resources = context.get("resources", [])
        cost_data = context.get("cost_data", {})
        time_range = context.get("time_range", "30 days")

        if not resources and not cost_data:
            return AgentResponse(
                agent_name=self.name,
                insights={"error": "No resource or cost data provided"},
                confidence=0.0,
                error="No resource or cost data provided",
            )

        # Analyze resources
        idle_resources = self._find_idle_resources(resources)
        overprovisioned = self._find_overprovisioned(resources)
        cost_opportunities = self._analyze_cost_opportunities(resources, cost_data)

        # Build analysis prompt
        prompt = f"""Analyze these cloud resources for cost optimization over {time_range}.

Resources Analyzed: {len(resources)}
Idle Resources Found: {len(idle_resources)}
Over-provisioned Resources: {len(overprovisioned)}

Idle Resources:
{self._format_idle_resources(idle_resources)}

Over-provisioned Resources:
{self._format_overprovisioned(overprovisioned)}

Cost Opportunities:
{self._format_cost_opportunities(cost_opportunities)}

Provide analysis with specific recommendations and estimated savings.
"""

        try:
            response_text = await self._query_claude(prompt, max_tokens=2048)

            insights = {
                "total_resources": len(resources),
                "idle_count": len(idle_resources),
                "overprovisioned_count": len(overprovisioned),
                "potential_savings_count": len(cost_opportunities),
                "estimated_monthly_savings": sum(
                    opp.get("estimated_savings", 0) for opp in cost_opportunities
                ),
            }

            recommendations = self._extract_recommendations(response_text)

            confidence = self._calculate_confidence(
                data_quality=0.85 if resources else 0.6,
                data_volume=len(resources),
            )

            return AgentResponse(
                agent_name=self.name,
                insights=insights,
                confidence=confidence,
                recommendations=recommendations,
                metadata={"analysis_text": response_text},
            )

        except Exception as e:
            logger.error(f"Cost analysis failed: {e}")
            return AgentResponse(
                agent_name=self.name,
                insights={},
                confidence=0.0,
                error=str(e),
            )

    def _find_idle_resources(self, resources: list[dict]) -> list[dict]:
        """Find idle or underutilized resources."""
        idle = []

        for resource in resources:
            resource_type = resource.get("type", "unknown")
            utilization = resource.get("utilization", {})

            # Check CPU utilization
            cpu_util = utilization.get("cpu", 1.0)  # Default to 100%

            # Check memory utilization
            mem_util = utilization.get("memory", 1.0)

            # Resource is idle if both CPU and memory are below 10%
            if cpu_util < 0.1 and mem_util < 0.1:
                idle.append(
                    {
                        "name": resource.get("name", "unknown"),
                        "type": resource_type,
                        "cpu_util": cpu_util,
                        "mem_util": mem_util,
                        "recommendation": "Consider deleting or scaling down",
                    }
                )

        return idle

    def _find_overprovisioned(self, resources: list[dict]) -> list[dict]:
        """Find over-provisioned resources."""
        overprovisioned = []

        for resource in resources:
            name = resource.get("name", "unknown")
            resource_type = resource.get("type", "unknown")

            # Get current specs
            cpu_request = resource.get("spec", {}).get("cpu_request", 0)
            cpu_limit = resource.get("spec", {}).get("cpu_limit", 0)
            mem_request = resource.get("spec", {}).get("memory_request", 0)
            mem_limit = resource.get("spec", {}).get("memory_limit", 0)

            # Get actual usage
            utilization = resource.get("utilization", {})
            cpu_usage = utilization.get("cpu", 0)
            mem_usage = utilization.get("memory", 0)

            # Calculate headroom
            if cpu_limit > 0:
                cpu_headroom = (cpu_limit - cpu_usage) / cpu_limit
            else:
                cpu_headroom = 0

            if mem_limit > 0:
                mem_headroom = (mem_limit - mem_usage) / mem_limit
            else:
                mem_headroom = 0

            # Resource is overprovisioned if >50% headroom
            if cpu_headroom > 0.5 or mem_headroom > 0.5:
                recommended_cpu = cpu_usage * 1.5  # 50% headroom
                recommended_mem = mem_usage * 1.5

                overprovisioned.append(
                    {
                        "name": name,
                        "type": resource_type,
                        "current_cpu": cpu_limit,
                        "recommended_cpu": recommended_cpu,
                        "current_memory": mem_limit,
                        "recommended_memory": recommended_mem,
                        "cpu_headroom": cpu_headroom,
                        "mem_headroom": mem_headroom,
                    }
                )

        return overprovisioned

    def _analyze_cost_opportunities(
        self, resources: list[dict], cost_data: dict
    ) -> list[dict]:
        """Analyze cost optimization opportunities."""
        opportunities = []

        # Cost per resource type
        cost_by_type = {}
        for resource in resources:
            resource_type = resource.get("type", "unknown")
            monthly_cost = resource.get("monthly_cost", 0)

            if resource_type not in cost_by_type:
                cost_by_type[resource_type] = 0
            cost_by_type[resource_type] += monthly_cost

        # Find expensive resource types
        for resource_type, total_cost in cost_by_type.items():
            if total_cost > 1000:  # More than $1000/month
                opportunities.append(
                    {
                        "type": resource_type,
                        "current_cost": total_cost,
                        "potential_savings": total_cost * 0.3,  # Assume 30% savings
                        "opportunity": f"Rightsizing and consolidation of {resource_type}",
                    }
                )

        # Check for unused volumes
        for resource in resources:
            if resource.get("type") == "volume" and resource.get("state") == "available":
                opportunities.append(
                    {
                        "name": resource.get("name", "unknown"),
                        "type": "volume",
                        "current_cost": resource.get("monthly_cost", 0),
                        "potential_savings": resource.get("monthly_cost", 0),
                        "opportunity": "Delete unused EBS volume",
                    }
                )

        return opportunities

    def _format_idle_resources(self, resources: list[dict]) -> str:
        """Format idle resources for display."""
        if not resources:
            return "No idle resources found"

        lines = []
        for resource in resources[:10]:
            name = resource.get("name", "unknown")
            rtype = resource.get("type", "unknown")
            cpu = resource.get("cpu_util", 0) * 100
            mem = resource.get("mem_util", 0) * 100
            lines.append(f"- {name} ({rtype}): {cpu:.1f}% CPU, {mem:.1f}% memory")

        return "\n".join(lines)

    def _format_overprovisioned(self, resources: list[dict]) -> str:
        """Format over-provisioned resources for display."""
        if not resources:
            return "No over-provisioned resources found"

        lines = []
        for resource in resources[:10]:
            name = resource.get("name", "unknown")
            rtype = resource.get("type", "unknown")
            current_cpu = resource.get("current_cpu", 0)
            recommended_cpu = resource.get("recommended_cpu", 0)
            lines.append(
                f"- {name} ({rtype}): {current_cpu:.2f} → {recommended_cpu:.2f} CPU cores"
            )

        return "\n".join(lines)

    def _format_cost_opportunities(self, opportunities: list[dict]) -> str:
        """Format cost opportunities for display."""
        if not opportunities:
            return "No cost opportunities found"

        lines = []
        for opp in opportunities[:10]:
            name = opp.get("name", opp.get("type", "unknown"))
            current_cost = opp.get("current_cost", 0)
            savings = opp.get("potential_savings", 0)
            opportunity = opp.get("opportunity", "Optimization available")
            lines.append(
                f"- {name}: ${current_cost:.2f}/month → Save ${savings:.2f}/month ({opportunity})"
            )

        return "\n".join(lines)
