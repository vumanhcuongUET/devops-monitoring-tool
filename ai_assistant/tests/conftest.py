"""
Pytest configuration and shared fixtures for AI Assistant tests.
"""

import pytest


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
