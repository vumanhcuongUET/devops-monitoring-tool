"""
Shared pytest fixtures for DevOps AI Agentics 2026 backend tests.

This module provides common fixtures used across all test suites including:
- Mock service clients (ES, Prometheus, K8s, APM, SLO, LLM)
- Test FastAPI application
- Async HTTP client for API testing
- Sample test data
"""

import asyncio
from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings

# Import app modules
from app.services.apm_client import ApmClient
from app.services.elasticsearch_client import ElasticsearchClient
from app.services.kubernetes_client import KubernetesClient
from app.services.llm_client import LLMClient
from app.services.prometheus_client import PrometheusClient
from app.services.slo_client import SloClient

# ============================================================================
# Test Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_settings() -> Settings:
    """Test settings with minimal configuration."""
    return Settings(
        elasticsearch_url="http://test-elk:9200",
        elasticsearch_username="elastic",
        elasticsearch_password="test_password",
        elasticsearch_index_pattern="logs-*",
        apm_index_pattern="apm-*",
        prometheus_url="http://test-prometheus:9090",
        kubeconfig_path="",  # Empty for testing
        k8s_namespaces=["default", "test"],
        auth_enabled=False,
        cors_origins=["http://localhost:3000"],
        alert_check_interval_seconds=60,
        slo_report_enabled=False,
    )


# ============================================================================
# Mock Service Client Fixtures
# ============================================================================

@pytest.fixture
def mock_elasticsearch_client() -> MagicMock:
    """Mock ElasticsearchClient with common methods."""
    mock = MagicMock(spec=ElasticsearchClient)

    # Mock async methods
    mock.search_logs = AsyncMock(return_value={
        "hits": {"total": {"value": 0}, "hits": []}
    })
    mock.get_error_count = AsyncMock(return_value=0)
    mock.get_cluster_health = AsyncMock(return_value={
        "cluster_name": "test",
        "status": "green",
        "number_of_nodes": 1
    })

    return mock


@pytest.fixture
def mock_apm_client() -> MagicMock:
    """Mock ApmClient with common methods."""
    mock = MagicMock(spec=ApmClient)

    mock.get_summary = AsyncMock(return_value={
        "transactions": 100,
        "errors": 5,
        "avg_response_time": 150.0
    })
    mock.get_transactions = AsyncMock(return_value=[])
    mock.get_errors = AsyncMock(return_value=[])

    return mock


@pytest.fixture
def mock_prometheus_client() -> MagicMock:
    """Mock PrometheusClient with common methods."""
    mock = MagicMock(spec=PrometheusClient)

    mock.get_cpu_percent = AsyncMock(return_value=45.0)
    mock.get_memory_percent = AsyncMock(return_value=60.0)
    mock.get_node_metrics = AsyncMock(return_value=[])
    mock.get_alerts = AsyncMock(return_value={
        "data": {"alerts": []}
    })
    mock.get_alerts_stats = AsyncMock(return_value={
        "default": {
            "total": 0,
            "firing": 0,
            "pending": 0,
            "by_severity": {},
            "alerts": [],
        }
    })

    return mock


@pytest.fixture
def mock_kubernetes_client() -> MagicMock:
    """Mock KubernetesClient with common methods."""
    mock = MagicMock(spec=KubernetesClient)

    mock.list_pods = AsyncMock(return_value=[])
    mock.list_deployments = AsyncMock(return_value=[])
    mock.list_nodes = AsyncMock(return_value=[])
    mock.get_events = AsyncMock(return_value=[])

    return mock


@pytest.fixture
def mock_slo_client() -> MagicMock:
    """Mock SloClient with common methods."""
    mock = MagicMock(spec=SloClient)

    mock.calculate_slo = AsyncMock(return_value={
        "slo_name": "test-slo",
        "slo_type": "availability",
        "target_percentage": 99.9,
        "actual_percentage": 99.95,
        "error_budget_remaining": 50.0,
        "status": "healthy"
    })
    mock.get_slow_apis = AsyncMock(return_value=[])

    return mock


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient for Claude API."""
    mock = MagicMock(spec=LLMClient)

    mock.generate_triage_card = AsyncMock(return_value={
        "project": "test",
        "incident_id": "test-001",
        "summary": "Test incident summary",
        "severity": "medium",
        "findings": [],
        "recommendations": []
    })
    mock.health_check = AsyncMock(return_value={
        "status": "healthy",
        "model": "claude-sonnet-4-20250514"
    })

    return mock


# ============================================================================
# Test Application Fixture
# ============================================================================

@pytest.fixture
async def test_app(
    mock_elasticsearch_client: MagicMock,
    mock_apm_client: MagicMock,
    mock_prometheus_client: MagicMock,
    mock_kubernetes_client: MagicMock,
    mock_slo_client: MagicMock,
    mock_llm_client: MagicMock,
) -> FastAPI:
    """Create a test FastAPI app with mocked service clients."""

    # Create a new app instance for testing
    test_app_instance = FastAPI(title="DevOps AI Agentics 2026 - Test")

    # Mount the real routes -- without the api_router every request 404s
    from app.api.router import api_router

    test_app_instance.include_router(api_router)

    # Store mock clients in app.state
    test_app_instance.state.es_client = mock_elasticsearch_client
    test_app_instance.state.apm_client = mock_apm_client
    test_app_instance.state.prometheus_client = mock_prometheus_client
    test_app_instance.state.k8s_client = mock_kubernetes_client
    test_app_instance.state.slo_client = mock_slo_client
    test_app_instance.state.llm_client = mock_llm_client

    return test_app_instance


# ============================================================================
# Async HTTP Client Fixture
# ============================================================================

@pytest.fixture
async def async_client(test_app: FastAPI) -> AsyncClient:
    """Create an async HTTP client for API testing."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        yield client


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_alert_rule() -> dict:
    """Sample alert rule for testing."""
    return {
        "id": "test-rule-001",
        "name": "Test High Error Rate",
        "description": "Test alert for high error rate",
        "enabled": True,
        "source": "elasticsearch",
        "conditions": [
            {
                "type": "error_count",
                "field": "log_level",
                "operator": "eq",
                "threshold": "ERROR"
            }
        ],
        "actions": [
            {
                "type": "slack",
                "config": {"webhook": "https://hooks.slack.com/test"}
            }
        ],
        "severity": "warning",
        "cooldown_seconds": 300
    }


@pytest.fixture
def sample_slo_config() -> dict:
    """Sample SLO config for testing."""
    return {
        "id": "test-slo-001",
        "service_name": "test-service",
        "name": "Test Availability SLO",
        "description": "Test SLO for availability",
        "type": "availability",
        "target_percentage": 99.9,
        "window_days": 7,
        "enabled": True
    }


@pytest.fixture
def sample_overview_data() -> dict:
    """Sample overview data for testing."""
    return {
        "timestamp": datetime.now().isoformat(),
        "systems": [
            {
                "name": "elasticsearch",
                "status": "healthy",
                "details": {"cluster_status": "green"}
            },
            {
                "name": "prometheus",
                "status": "healthy",
                "details": {"targets_total": 100, "targets_up": 98}
            },
            {
                "name": "kubernetes",
                "status": "degraded",
                "details": {"pods_total": 50, "pods_running": 45, "pods_pending": 5}
            }
        ],
        "active_alerts": 2
    }


# ============================================================================
# Event Loop Fixture
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
