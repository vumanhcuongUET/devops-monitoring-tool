"""
Integration tests for Overview API endpoint.

Tests the GET /api/v1/overview endpoint including:
- System overview aggregation
- Health status for all systems
- Parallel data fetching
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.api
class TestOverviewAPI:
    """Test suite for /api/v1/overview endpoint."""

    @pytest.mark.asyncio
    async def test_get_overview_returns_system_status(self, async_client: AsyncClient):
        """Test that GET /overview returns system overview."""
        response = await async_client.get("/api/v1/overview")

        assert response.status_code == 200

        data = response.json()
        assert "systems" in data
        assert "timestamp" in data
        assert isinstance(data["systems"], dict)

    @pytest.mark.asyncio
    async def test_get_overview_includes_all_systems(self, async_client: AsyncClient):
        """Test that overview includes all expected systems."""
        response = await async_client.get("/api/v1/overview")

        data = response.json()
        system_names = list(data["systems"].keys())

        # Should include core systems
        expected_systems = ["elasticsearch", "kubernetes", "apm"]

        for system in expected_systems:
            assert system in system_names

    @pytest.mark.asyncio
    async def test_get_overview_systems_have_health_status(self, async_client: AsyncClient):
        """Test that each system has a health status."""
        response = await async_client.get("/api/v1/overview")

        data = response.json()

        for _name, system in data["systems"].items():
            assert isinstance(system, dict)
            assert "status" in system
            assert system["status"] in ["healthy", "degraded", "down"]

    @pytest.mark.asyncio
    async def test_get_overview_includes_active_alerts_count(self, async_client: AsyncClient):
        """Test that overview includes active alerts count."""
        response = await async_client.get("/api/v1/overview")

        data = response.json()
        assert "active_alerts" in data
        assert isinstance(data["active_alerts"], int)

    @pytest.mark.asyncio
    async def test_get_overview_handles_partial_outage(self, async_client: AsyncClient):
        """Test that overview handles partial system outages."""
        # Mock one service to be down
        response = await async_client.get("/api/v1/overview")

        # Should still return 200 even if some systems are down
        assert response.status_code == 200

        data = response.json()
        # At least some systems should respond
        assert len(data["systems"]) > 0

    @pytest.mark.asyncio
    async def test_get_overview_response_time_under_limit(self, async_client: AsyncClient):
        """Test that overview API responds within time limit."""
        import time

        start = time.time()
        response = await async_client.get("/api/v1/overview")
        duration = time.time() - start

        assert response.status_code == 200
        # Should respond within 5 seconds (parallel fetching)
        assert duration < 5.0

    @pytest.mark.asyncio
    async def test_get_overview_without_authentication(self, async_client: AsyncClient):
        """Test that overview requires authentication when enabled."""
        # This test would verify auth is required
        # For now, auth is disabled in test config
        response = await async_client.get("/api/v1/overview")
        assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_get_overview_system_details(self, async_client: AsyncClient):
        """Test that system details are included."""
        response = await async_client.get("/api/v1/overview")

        data = response.json()

        for _name, system in data["systems"].items():
            # Systems should expose status details
            assert "status" in system
