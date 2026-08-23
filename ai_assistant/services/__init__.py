"""
Backend service adapters for AI Assistant.

Provides sync wrappers around async backend service clients.
"""

from .elasticsearch_adapter import ElasticsearchAdapter
from .prometheus_adapter import PrometheusAdapter
from .apm_adapter import ApmAdapter
from .k8s_adapter import KubernetesAdapter
from .optimizer_adapter import OptimizerAdapter

__all__ = [
    "ElasticsearchAdapter",
    "PrometheusAdapter",
    "ApmAdapter",
    "KubernetesAdapter",
    "OptimizerAdapter",
]
