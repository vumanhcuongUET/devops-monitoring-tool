"""
Pytest configuration and shared fixtures for AI Assistant tests.

Follows backend testing patterns with AsyncMock for async methods.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path


# ----------------------------------------------------------------------
# Mock Service Clients
# ----------------------------------------------------------------------

@pytest.fixture
def mock_elasticsearch_client():
    """Mock ElasticsearchClient with common methods."""
    mock = MagicMock()
    mock.client = MagicMock()

    # Mock async methods with AsyncMock
    mock.client.search = AsyncMock(return_value={
        "hits": {
            "total": {"value": 5},
            "hits": [
                {"_source": {"message": "Error in connection"}},
                {"_source": {"message": "Database timeout"}},
            ]
        }
    })
    mock.client.count = AsyncMock(return_value={"count": 5})

    mock.get_cluster_health = AsyncMock(return_value={
        "cluster_name": "test-cluster",
        "status": "green",
        "number_of_nodes": 1
    })

    return mock


@pytest.fixture
def mock_prometheus_client():
    """Mock PrometheusClient with query methods."""
    mock = MagicMock()

    # Mock async query methods
    mock._query = AsyncMock(return_value={
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "up", "job": "prometheus"},
                    "value": [1234567890, "1"]
                }
            ]
        }
    })

    mock._query_range = AsyncMock(return_value={
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"__name__": "up"},
                    "values": [[1234567890, "1"], [1234567900, "1"]]
                }
            ]
        }
    })

    mock.get_alerts = AsyncMock(return_value=[
        {
            "alert": {"alertname": "HighErrorRate", "severity": "warning"},
            "state": "firing"
        }
    ])

    return mock


@pytest.fixture
def mock_apm_client():
    """Mock ApmClient with transaction and error methods."""
    mock = MagicMock()

    mock.get_transactions = AsyncMock(return_value={
        "transactions": [
            {"name": "/api/users", "duration": 150},
            {"name": "/api/orders", "duration": 320}
        ]
    })

    mock.get_errors = AsyncMock(return_value=[
        {"error": {"type": "ConnectionError", "count": 15}},
        {"error": {"type": "Timeout", "count": 8}}
    ])

    mock.get_summary = AsyncMock(return_value={
        "latency_p50": 45,
        "latency_p95": 150,
        "latency_p99": 320,
        "error_rate_percent": 2.5,
        "throughput": 1200
    })

    return mock


@pytest.fixture
def mock_k8s_client():
    """Mock KubernetesClient with cluster methods."""
    mock = MagicMock()

    mock.list_pods = AsyncMock(return_value=[
        {
            "name": "pod-1",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1"
        },
        {
            "name": "pod-2",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1"
        }
    ])

    mock.list_deployments = AsyncMock(return_value=[
        {
            "name": "app-deployment",
            "namespace": "default",
            "ready": "3/3",
            "available": 3,
            "replicas": 3
        }
    ])

    mock.list_nodes = AsyncMock(return_value=[
        {
            "name": "node-1",
            "status": "Ready",
            "roles": ["control-plane", "worker"]
        }
    ])

    return mock


# ----------------------------------------------------------------------
# Sample Data
# ----------------------------------------------------------------------

@pytest.fixture
def sample_elk_response():
    """Sample Elasticsearch query response."""
    return {
        "hits": {
            "total": {"value": 100},
            "hits": [
                {"_source": {"message": "Error 1", "level": "ERROR"}},
                {"_source": {"message": "Error 2", "level": "ERROR"}},
                {"_source": {"message": "Error 3", "level": "ERROR"}}
            ]
        }
    }


@pytest.fixture
def sample_prometheus_response():
    """Sample Prometheus query response."""
    return {
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"__name__": "cpu"}, "value": [1234567890, "45.5"]},
                {"metric": {"__name__": "memory"}, "value": [1234567890, "62.3"]}
            ]
        }
    }


@pytest.fixture
def sample_config():
    """Sample merged configuration."""
    return {
        "project": "meinvoice",
        "namespace": "meinvoice",
        "node_job": "node-exporter",
        "query_vars": {
            "time_range": "now-1h",
            "max_results": 10,
            "timeout_seconds": 10,
            "project_filter": 'app.keyword:"meinvoice"',
            "apm_filter": 'app.keyword:"meinvoice"'
        },
        "sources": {
            "elk_error": [
                {
                    "name": "ELK-Production",
                    "url": "http://localhost:9200",
                    "index": "logs-*-error-*",
                    "auth_env": "ELK_AUTH"
                }
            ],
            "prometheus_k8s": [
                {
                    "name": "Prometheus-K8s",
                    "url": "http://localhost:9090",
                    "auth_env": "PROM_AUTH"
                }
            ]
        },
        "skip_sections": []
    }


# ----------------------------------------------------------------------
# Test Configuration
# ----------------------------------------------------------------------

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (no external services)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (requires external services)"
    )
