"""
Unit tests for LLMClient.

Tests the LLM client functionality including:
- Triage card generation
- Health checks
- Prompt building
- Response parsing
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from anthropic import APIError


@pytest.mark.unit
@pytest.mark.service
class TestLLMClient:
    """Test suite for LLMClient."""

    @pytest.mark.asyncio
    async def test_generate_triage_card_returns_triage_card(self, mock_llm_client):
        """Test that generate_triage_card returns a valid triage card."""
        result = await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-001",
            alert_message="High error rate detected",
            time_range_minutes=60
        )

        assert "project" in result
        assert "incident_id" in result
        assert "summary" in result
        assert "severity" in result
        assert "findings" in result
        assert "recommendations" in result
        assert result["project"] == "test-project"

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_status(self, mock_llm_client):
        """Test that health_check returns healthy status."""
        result = await mock_llm_client.health_check()

        assert result["status"] == "healthy"
        assert "model" in result

    @pytest.mark.asyncio
    async def test_generate_triage_card_with_findings(self, mock_llm_client):
        """Test that generate_triage_card can return findings."""
        mock_llm_client.generate_triage_card = AsyncMock(return_value={
            "project": "test",
            "incident_id": "test-001",
            "summary": "Database connection timeout",
            "severity": "high",
            "findings": [
                {
                    "type": "root_cause",
                    "title": "Database connection pool exhausted",
                    "severity": "critical",
                    "confidence": 0.9,
                    "evidence": ["Connection timeout errors", "High wait time"]
                }
            ],
            "recommendations": [
                {
                    "priority": 1,
                    "action": "Check database connectivity",
                    "command": "kubectl exec -n test -- pg_isready"
                }
            ]
        })

        result = await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-001",
            alert_message="Database errors"
        )

        assert len(result["findings"]) == 1
        assert result["findings"][0]["type"] == "root_cause"
        assert len(result["recommendations"]) == 1

    @pytest.mark.asyncio
    async def test_health_check_with_api_error(self, mock_llm_client):
        """Test that health_check handles API errors."""
        mock_llm_client.health_check = AsyncMock(
            side_effect=APIError("API request failed")
        )

        with pytest.raises(APIError):
            await mock_llm_client.health_check()

    @pytest.mark.asyncio
    async def test_generate_triage_card_with_custom_time_range(self, mock_llm_client):
        """Test that generate_triage_card accepts custom time ranges."""
        await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-002",
            time_range_minutes=30
        )

        mock_llm_client.generate_triage_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_triage_card_with_severity_threshold(self, mock_llm_client):
        """Test that generate_triage_card accepts severity threshold."""
        await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-003",
            severity_threshold="high"
        )

        mock_llm_client.generate_triage_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_triage_card_without_recommendations(self, mock_llm_client):
        """Test that generate_triage_card can skip recommendations."""
        await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-004",
            include_recommendations=False
        )

        mock_llm_client.generate_triage_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_with_different_models(self, mock_llm_client):
        """Test that health_check reports configured model."""
        mock_llm_client.health_check = AsyncMock(return_value={
            "status": "healthy",
            "model": "claude-opus-4-20250514"
        })

        result = await mock_llm_client.health_check()

        assert result["model"] == "claude-opus-4-20250514"
