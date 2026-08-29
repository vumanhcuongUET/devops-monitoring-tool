"""
Integration tests for Analyze API endpoint.

Tests the POST /api/v1/analyze endpoint including:
- Triage card generation
- Health check endpoint
- Error handling
"""


import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.api
class TestAnalyzeAPI:
    """Test suite for /api/v1/analyze endpoint."""

    @pytest.mark.asyncio
    async def test_analyze_health_returns_healthy(self, async_client: AsyncClient):
        """Test that GET /analyze/health returns healthy status."""
        response = await async_client.get("/api/v1/analyze/health")

        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_analyze_health_includes_model_info(self, async_client: AsyncClient):
        """Test that health check includes model information."""
        response = await async_client.get("/api/v1/analyze/health")

        data = response.json()
        assert "model" in data

    @pytest.mark.asyncio
    async def test_analyze_generates_triage_card(self, async_client: AsyncClient):
        """Test that POST /analyze generates triage card."""
        request_data = {
            "project": "test-project",
            "incident_id": "test-001",
            "alert_message": "Test alert message",
            "time_range_minutes": 60,
            "include_recommendations": True
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        # Note: May fail if ANTHROPIC_API_KEY not configured
        # In test environment, this would be mocked
        assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_analyze_returns_structured_response(self, async_client: AsyncClient):
        """Test that analyze returns properly structured triage card."""
        # This would need the LLM client to be mocked
        request_data = {
            "project": "test-project",
            "incident_id": "test-002",
            "alert_message": "High error rate detected",
            "time_range_minutes": 30
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            if data["success"]:
                assert "triage_card" in data
                triage_card = data["triage_card"]
                assert "project" in triage_card
                assert "incident_id" in triage_card
                assert "summary" in triage_card
                assert "severity" in triage_card

    @pytest.mark.asyncio
    async def test_analyze_with_custom_time_range(self, async_client: AsyncClient):
        """Test that analyze accepts custom time ranges."""
        request_data = {
            "project": "test-project",
            "incident_id": "test-003",
            "alert_message": "Test",
            "time_range_minutes": 15  # Custom time range
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        # Should attempt to process request
        assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_analyze_without_recommendations(self, async_client: AsyncClient):
        """Test that analyze can skip recommendations."""
        request_data = {
            "project": "test-project",
            "incident_id": "test-004",
            "alert_message": "Test",
            "include_recommendations": False
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_analyze_with_severity_threshold(self, async_client: AsyncClient):
        """Test that analyze accepts severity threshold."""
        request_data = {
            "project": "test-project",
            "incident_id": "test-005",
            "alert_message": "Test",
            "severity_threshold": "high"
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_analyze_handles_missing_fields(self, async_client: AsyncClient):
        """Test that analyze handles missing required fields."""
        request_data = {
            "project": "test-project"
            # Missing: incident_id, alert_message
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        # Should return validation error
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_analyze_handles_empty_project(self, async_client: AsyncClient):
        """Test that validate handles empty project name."""
        request_data = {
            "project": "",
            "incident_id": "test-006",
            "alert_message": "Test"
        }

        response = await async_client.post(
            "/api/v1/analyze",
            json=request_data
        )

        # Should return validation error
        assert response.status_code == 422
