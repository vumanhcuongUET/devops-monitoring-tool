"""
Output Optimization for AI Assistant.

Intelligent truncation and summarization to minimize token usage
while preserving critical information.
"""

import json
from typing import Any, Dict, List, Optional

# Lazy imports
def _get_logger():
    from core.logging_config import get_logger
    return get_logger(__name__)


def _get_metrics():
    from core.logging_config import get_metrics
    return get_metrics()


class OutputOptimizer:
    """
    Optimizes query output size for minimal token usage.

    Strategies:
    - Truncate large arrays to top N items
    - Remove redundant fields
    - Compact formatting
    - Preserve critical data (alerts, errors)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize optimizer with configuration.

        Args:
            config: Configuration dictionary with optimization settings
        """
        self.max_results = config.get("max_results_per_source", 10)
        self.truncate_enabled = config.get("truncate_results", True)
        self.preserve_critical = True  # Always preserve critical alerts/errors

    def optimize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize a single query result.

        Args:
            result: Single query result dict

        Returns:
            Optimized result dict
        """
        if not self.truncate_enabled:
            return result

        optimized = result.copy()

        # Don't optimize error results (only skip if status is an error type)
        status = result.get("status")
        if status and status not in ("ok", "unreachable", "timeout"):
            return result

        # Optimize data field if present
        if "data" in optimized and optimized["data"]:
            optimized["data"] = self._optimize_data(optimized["data"])

        # Handle sub_queries (Prometheus multi-query format)
        if "sub_queries" in optimized and optimized["sub_queries"]:
            optimized["sub_queries"] = [
                self.optimize_result(sq) for sq in optimized["sub_queries"]
            ]

        return optimized

    def optimize_section(self, section_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize entire section result.

        Args:
            section_result: Full section result with results array

        Returns:
            Optimized section result
        """
        if not self.truncate_enabled:
            return section_result

        optimized = section_result.copy()

        # Optimize each result in the section
        if "results" in optimized:
            optimized_results = []
            for result in optimized["results"]:
                optimized_results.append(self.optimize_result(result))
            optimized["results"] = optimized_results

            # Track optimization
            _get_metrics().increment("section_result_count", labels={"count": str(len(optimized_results))})
            _get_metrics().increment("section_optimization_total")

        return optimized

    def _optimize_data(self, data: Any) -> Any:
        """
        Optimize data from query response.

        Args:
            data: Raw data from ELK/Prometheus response (dict or list)

        Returns:
            Optimized data
        """
        # Handle list data directly
        if isinstance(data, list):
            if len(data) > self.max_results:
                truncated = data[:self.max_results]
                _get_logger().debug("Truncated list data",
                                     original_len=len(data),
                                     truncated_len=len(truncated))
                _get_metrics().increment("list_data_truncated_total",
                                        labels={"original": str(len(data)),
                                               "truncated": str(len(truncated))})
                return truncated
            return data

        if not isinstance(data, dict):
            return data

        optimized = {}

        # Handle Elasticsearch response format
        if "hits" in data:
            hits = data["hits"]
            if isinstance(hits, dict) and "hits" in hits:
                hit_list = hits["hits"]
                # Truncate to max_results
                if len(hit_list) > self.max_results:
                    truncated_count = len(hit_list) - self.max_results
                    hit_list = hit_list[:self.max_results]
                    _get_logger().debug("Truncated ELK results",
                                         count=len(hit_list),
                                         truncated=truncated_count)
                    _get_metrics().increment("elk_results_truncated_total",
                                            labels={"truncated": str(truncated_count)})

                optimized["hits"] = {"hits": hit_list, "total": {"value": len(hit_list)}}

                # Preserve aggregations if present
                if "aggregations" in data:
                    optimized["aggregations"] = self._optimize_aggregations(
                        data["aggregations"]
                    )

        # Handle Prometheus response format
        elif "data" in data and "result" in data["data"]:
            result_list = data["data"]["result"]
            if len(result_list) > self.max_results:
                result_list = result_list[:self.max_results]
                _get_logger().debug("Truncated Prometheus results",
                                     count=len(result_list))
                _get_metrics().increment("prometheus_results_truncated_total")

            optimized["data"] = {"result": result_list}

        # Generic truncation for arrays
        else:
            for key, value in data.items():
                if isinstance(value, list) and len(value) > self.max_results:
                    truncated = value[:self.max_results]
                    optimized[key] = truncated
                    _get_logger().debug("Truncated array field",
                                         field=key,
                                         original_len=len(value),
                                         truncated_len=len(truncated))
                    _get_metrics().increment("array_field_truncated_total",
                                            labels={"field": key})
                else:
                    optimized[key] = value

        return optimized

    def _optimize_aggregations(self, aggs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize aggregation results.

        Preserves aggregation structure but truncates buckets.

        Args:
            aggs: Aggregations dict

        Returns:
            Optimized aggregations
        """
        if not isinstance(aggs, dict):
            return aggs

        optimized = {}

        for agg_name, agg_value in aggs.items():
            if isinstance(agg_value, dict) and "buckets" in agg_value:
                buckets = agg_value["buckets"]
                if len(buckets) > self.max_results:
                    buckets = buckets[:self.max_results]
                    _get_logger().debug("Truncated aggregation buckets",
                                         agg_name=agg_name,
                                         count=len(buckets))

                optimized[agg_name] = {"buckets": buckets}
            else:
                optimized[agg_name] = agg_value

        return optimized

    def estimate_tokens(self, data: Dict[str, Any]) -> int:
        """
        Estimate token count for data.

        Rough estimation: 4 characters ≈ 1 token.

        Args:
            data: Data dictionary

        Returns:
            Estimated token count
        """
        json_str = json.dumps(data, ensure_ascii=False)
        return len(json_str) // 4


# Global optimizer instance
_global_optimizer: Optional[OutputOptimizer] = None


def get_output_optimizer(config: Optional[Dict[str, Any]] = None) -> OutputOptimizer:
    """
    Get or create global output optimizer instance.

    Args:
        config: Optional configuration for optimizer

    Returns:
        OutputOptimizer instance
    """
    global _global_optimizer

    if _global_optimizer is None or config is not None:
        if config is None:
            from core.config_loader import get_feature_flags
            flags = get_feature_flags()
            config = flags.get("output", {})

        _global_optimizer = OutputOptimizer(config)

    return _global_optimizer
