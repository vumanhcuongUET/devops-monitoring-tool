"""
Performance Analysis Agent

Specializes in:
- Application performance analysis
- Bottleneck identification
- Database performance
- Network performance analysis
"""

import logging
from typing import Any

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class PerformanceAgent(BaseAgent):
    """
    Agent specialized in application and infrastructure performance analysis.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            name="performance-analyst",
            model=model,
        )

    def get_prompt_template(self) -> str:
        return """You are a Performance Analysis Expert specializing in:
- Application performance bottleneck identification
- Database query optimization
- Network latency analysis
- Caching strategy recommendations
- Performance testing and benchmarking

When analyzing performance, focus on:
1. **Bottlenecks**: Identify the limiting factors (CPU, memory, I/O, network)
2. **Slow Operations**: Database queries, API calls, file operations
3. **Resource Contention**: Locking, queueing, resource exhaustion
4. **Optimization Opportunities**: Caching, indexing, query optimization

Output format:
```
ANALYSIS:
[Your performance analysis]

BOTTLENECKS:
- Bottleneck 1: [description], [impact level], [affected components]
- Bottleneck 2: [description], [impact level], [affected components]

SLOW OPERATIONS:
- Operation 1: [type], [duration], [recommendation]
- Operation 2: [type], [duration], [recommendation]

RESOURCE CONTENTION:
- Contention 1: [description], [severity]
- Contention 2: [description], [severity]

OPTIMIZATION RECOMMENDATIONS:
- Recommendation 1: [expected improvement]
- Recommendation 2: [expected improvement]

CONFIDENCE: [0.0-1.0]

RECOMMENDATION: [Actionable performance recommendation]
```

Be quantitative with timing data. Prioritize high-impact optimizations.
"""

    async def analyze(self, context: dict[str, Any]) -> AgentResponse:
        """
        Analyze application performance.

        Args:
            context: Must contain 'performance_data' or 'traces' key
                    Optional: 'service', 'time_range'
        """
        performance_data = context.get("performance_data", {})
        traces = context.get("traces", [])
        service = context.get("service", "unknown")

        if not performance_data and not traces:
            return AgentResponse(
                agent_name=self.name,
                insights={"error": "No performance data or traces provided"},
                confidence=0.0,
                error="No performance data provided",
            )

        # Analyze performance
        bottlenecks = self._identify_bottlenecks(performance_data, traces)
        slow_operations = self._find_slow_operations(traces)
        resource_contention = self._analyze_contention(performance_data)
        optimizations = self._suggest_optimizations(bottlenecks, slow_operations)

        # Build analysis prompt
        prompt = f"""Analyze this performance data for service '{service}'.

Bottlenecks Found: {len(bottlenecks)}
Slow Operations: {len(slow_operations)}
Resource Contention Issues: {len(resource_contention)}

Bottlenecks:
{self._format_bottlenecks(bottlenecks)}

Slow Operations:
{self._format_slow_operations(slow_operations)}

Resource Contention:
{self._format_contention(resource_contention)}

Optimization Opportunities:
{self._format_optimizations(optimizations)}

Provide performance analysis with specific optimization recommendations.
"""

        try:
            response_text = await self._query_claude(prompt, max_tokens=2048)

            insights = {
                "service": service,
                "bottleneck_count": len(bottlenecks),
                "slow_operation_count": len(slow_operations),
                "contention_count": len(resource_contention),
                "optimization_count": len(optimizations),
            }

            # Calculate potential improvement
            if optimizations:
                total_improvement = sum(
                    opt.get("improvement_pct", 0) for opt in optimizations
                )
                insights["potential_improvement"] = total_improvement / len(
                    optimizations
                )

            recommendations = self._extract_recommendations(response_text)

            confidence = self._calculate_confidence(
                data_quality=0.9 if performance_data else 0.7,
                data_volume=len(traces),
            )

            return AgentResponse(
                agent_name=self.name,
                insights=insights,
                confidence=confidence,
                recommendations=recommendations,
                metadata={"analysis_text": response_text},
            )

        except Exception as e:
            logger.error(f"Performance analysis failed: {e}")
            return AgentResponse(
                agent_name=self.name,
                insights={},
                confidence=0.0,
                error=str(e),
            )

    def _identify_bottlenecks(
        self, performance_data: dict, traces: list
    ) -> list[dict]:
        """Identify performance bottlenecks."""
        bottlenecks = []

        # CPU bottleneck
        cpu_usage = performance_data.get("cpu_usage", 0)
        if cpu_usage > 0.9:
            bottlenecks.append(
                {
                    "type": "CPU",
                    "description": f"High CPU usage ({cpu_usage:.1%})",
                    "impact": "critical" if cpu_usage > 0.95 else "high",
                    "affected": "all operations",
                }
            )

        # Memory bottleneck
        memory_usage = performance_data.get("memory_usage", 0)
        if memory_usage > 0.85:
            bottlenecks.append(
                {
                    "type": "Memory",
                    "description": f"High memory usage ({memory_usage:.1%})",
                    "impact": "high" if memory_usage > 0.95 else "medium",
                    "affected": "all operations",
                }
            )

        # I/O bottleneck
        io_wait = performance_data.get("io_wait", 0)
        if io_wait > 0.2:  # More than 20% iowait
            bottlenecks.append(
                {
                    "type": "I/O",
                    "description": f"High I/O wait ({io_wait:.1%})",
                    "impact": "high",
                    "affected": "disk operations",
                }
            )

        # Database bottleneck from traces
        db_operations = [t for t in traces if t.get("type") == "database"]
        if db_operations:
            avg_db_duration = sum(t.get("duration", 0) for t in db_operations) / len(
                db_operations
            )
            if avg_db_duration > 1.0:  # More than 1 second
                bottlenecks.append(
                    {
                        "type": "Database",
                        "description": f"Slow database queries (avg {avg_db_duration:.2f}s)",
                        "impact": "high" if avg_db_duration > 2 else "medium",
                        "affected": "database operations",
                    }
                )

        return bottlenecks

    def _find_slow_operations(self, traces: list) -> list[dict]:
        """Find slow operations from traces."""
        slow_ops = []
        threshold = 1.0  # 1 second

        for trace in traces:
            duration = trace.get("duration", 0)
            if duration > threshold:
                slow_ops.append(
                    {
                        "type": trace.get("type", "unknown"),
                        "name": trace.get("name", "unknown"),
                        "duration": duration,
                        "severity": "critical" if duration > 5 else "high",
                    }
                )

        return sorted(slow_ops, key=lambda x: x["duration"], reverse=True)[:20]

    def _analyze_contention(self, performance_data: dict) -> list[dict]:
        """Analyze resource contention issues."""
        contention = []

        # Lock contention
        lock_waits = performance_data.get("lock_waits", 0)
        if lock_waits > 10:  # More than 10 locks waiting
            contention.append(
                {
                    "type": "Lock",
                    "description": f"High lock contention ({lock_waits} waiting)",
                    "severity": "high" if lock_waits > 50 else "medium",
                }
            )

        # Queue depth
        queue_depth = performance_data.get("queue_depth", 0)
        if queue_depth > 100:
            contention.append(
                {
                    "type": "Queue",
                    "description": f"Deep queue ({queue_depth} items)",
                    "severity": "medium",
                }
            )

        # Connection pool exhaustion
        connection_pool_usage = performance_data.get("connection_pool_usage", 0)
        if connection_pool_usage > 0.9:
            contention.append(
                {
                    "type": "ConnectionPool",
                    "description": f"Connection pool near capacity ({connection_pool_usage:.1%})",
                    "severity": "high",
                }
            )

        return contention

    def _suggest_optimizations(
        self, bottlenecks: list, slow_ops: list
    ) -> list[dict]:
        """Suggest performance optimizations."""
        optimizations = []

        for bottleneck in bottlenecks:
            btype = bottleneck["type"]
            if btype == "Database":
                optimizations.append(
                    {
                        "type": "Query Optimization",
                        "description": "Add indexes for slow queries",
                        "improvement_pct": 50,
                    }
                )
                optimizations.append(
                    {
                        "type": "Caching",
                        "description": "Implement query result caching",
                        "improvement_pct": 70,
                    }
                )
            elif btype == "CPU":
                optimizations.append(
                    {
                        "type": "Optimization",
                        "description": "Review and optimize CPU-intensive operations",
                        "improvement_pct": 30,
                    }
                )
            elif btype == "I/O":
                optimizations.append(
                    {
                        "type": "Optimization",
                        "description": "Implement async I/O and batching",
                        "improvement_pct": 40,
                    }
                )

        # Check for N+1 query patterns
        db_ops = [op for op in slow_ops if op["type"] == "database"]
        if len(db_ops) > 10:
            optimizations.append(
                {
                    "type": "Query Optimization",
                    "description": "Fix N+1 query pattern with eager loading",
                    "improvement_pct": 60,
                }
            )

        return optimizations

    def _format_bottlenecks(self, bottlenecks: list[dict]) -> str:
        """Format bottlenecks for display."""
        if not bottlenecks:
            return "No bottlenecks identified"

        lines = []
        for b in bottlenecks:
            btype = b["type"]
            desc = b["description"]
            impact = b["impact"]
            affected = b["affected"]
            lines.append(f"- [{impact.upper()}] {btype}: {desc} (affects {affected})")

        return "\n".join(lines)

    def _format_slow_operations(self, operations: list[dict]) -> str:
        """Format slow operations for display."""
        if not operations:
            return "No slow operations identified"

        lines = []
        for op in operations[:15]:
            otype = op["type"]
            name = op["name"]
            duration = op["duration"]
            severity = op["severity"]
            lines.append(f"- [{severity.upper()}] {otype}/{name}: {duration:.2f}s")

        return "\n".join(lines)

    def _format_contention(self, contention: list[dict]) -> str:
        """Format contention for display."""
        if not contention:
            return "No resource contention identified"

        lines = []
        for c in contention:
            ctype = c["type"]
            desc = c["description"]
            severity = c["severity"]
            lines.append(f"- [{severity.upper()}] {ctype}: {desc}")

        return "\n".join(lines)

    def _format_optimizations(self, optimizations: list[dict]) -> str:
        """Format optimizations for display."""
        if not optimizations:
            return "No optimization opportunities identified"

        lines = []
        for opt in optimizations[:10]:
            otype = opt["type"]
            desc = opt["description"]
            improvement = opt.get("improvement_pct", 0)
            lines.append(f"- {otype}: {desc} (~{improvement}% improvement)")

        return "\n".join(lines)
