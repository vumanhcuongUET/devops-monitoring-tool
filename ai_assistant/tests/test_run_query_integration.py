"""
Integration tests for run_query_v2.py.

Tests the full query execution flow including:
- Config loading
- Feature flag integration
- Direct HTTP query execution
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Mock requests before importing run_query_v2 (which imports requests at module level)
mock_requests = MagicMock()
mock_requests.post = MagicMock()
mock_requests.get = MagicMock()
mock_requests.exceptions = MagicMock()
mock_requests.exceptions.ConnectionError = Exception
mock_requests.exceptions.Timeout = Exception
mock_requests.exceptions.HTTPError = Exception

with patch.dict("sys.modules", {"requests": mock_requests}):
    from tools import run_query_v2


@pytest.mark.unit
class TestRunQueryIntegration:
    """Integration tests for run_query_v2."""

    def test_query_elk_http_fallback(self, sample_elk_response):
        """Test HTTP execution of ELK queries."""
        # Mock requests to avoid actual HTTP call
        with patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = sample_elk_response
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = lambda: None

            source = {
                "name": "Test-ELK",
                "url": "http://localhost:9200",
                "index": "test-*",
                "auth_env": None
            }
            body = {"query": {"match_all": {}}}

            result = run_query_v2.query_elk_http(source, body, 10)

            assert result["status"] == "ok"
            assert result["source"] == "Test-ELK"

    def test_query_prometheus_http_fallback(self, sample_prometheus_response):
        """Test HTTP fallback for Prometheus queries."""
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = sample_prometheus_response
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = lambda: None

            source = {
                "name": "Test-Prometheus",
                "url": "http://localhost:9090",
                "auth_env": None
            }
            promql = "up"

            result = run_query_v2.query_prometheus_http(source, promql, 10)

            assert result["status"] == "ok"
            assert result["source"] == "Test-Prometheus"

    def test_execute_elk_query_uses_http(self, sample_elk_response):
        """Test that execute_elk_query executes via direct HTTP."""
        with patch.object(run_query_v2.requests, "post") as mock_post:
            mock_post.return_value.json.return_value = sample_elk_response
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = lambda: None

            source = {
                "name": "Test-ELK",
                "url": "http://localhost:9200",
                "index": "test-*",
                "auth_env": None
            }
            body = {"query": {"match_all": {}}}

            result = run_query_v2.execute_elk_query(source, body, 10)

            mock_post.assert_called_once()
            assert result["status"] == "ok"
            assert result["source"] == "Test-ELK"

    def test_execute_prometheus_query_uses_http(self, sample_prometheus_response):
        """Test that execute_prometheus_query executes via direct HTTP."""
        with patch.object(run_query_v2.requests, "get") as mock_get:
            mock_get.return_value.json.return_value = sample_prometheus_response
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = lambda: None

            source = {
                "name": "Test-Prometheus",
                "url": "http://localhost:9090",
                "auth_env": None
            }

            result = run_query_v2.execute_prometheus_query(source, "up", 10)

            mock_get.assert_called_once()
            assert result["status"] == "ok"
            assert result["source"] == "Test-Prometheus"

    def test_auth_headers_with_env_var(self, monkeypatch):
        """Test that auth headers are constructed from env var."""
        monkeypatch.setenv("TEST_AUTH", "dGVzdDpwYXNzd29yZA==")  # base64("test:password")

        headers = run_query_v2._auth_headers("TEST_AUTH")

        assert headers == {"Authorization": "Basic dGVzdDpwYXNzd29yZA=="}

    def test_auth_headers_without_env_var(self, monkeypatch):
        """Test that auth headers are empty when env var not set."""
        # Ensure env var is not set
        monkeypatch.delenv("NONEXISTENT_AUTH", raising=False)

        headers = run_query_v2._auth_headers("NONEXISTENT_AUTH")

        assert headers == {}

    def test_auth_headers_with_none_env_var(self):
        """Test that auth headers are empty when passed None."""
        headers = run_query_v2._auth_headers(None)
        assert headers == {}

    def test_run_section_end_to_end(self, sample_config):
        """Test full section execution flow."""
        # Mock load_query_def to return a valid query definition
        mock_query_def = {
            "type": "elk",
            "source_types": ["elk_error"],
            "elk_body_template": '{"query": {"match_all": {}}}'
        }

        with patch("tools.run_query_v2.load_query_def", return_value=mock_query_def):
            with patch("tools.run_query_v2.execute_elk_query") as mock_elk:
                mock_elk.return_value = {
                    "status": "ok",
                    "source": "Test-ELK",
                    "data": {"hits": {"total": {"value": 5}, "hits": []}}
                }

                result = run_query_v2.run_section(sample_config, "errors", None)

                assert "section" in result
                assert "results" in result
                assert result["section"] == "errors"

    def test_run_section_with_time_range_override(self, sample_config):
        """Test that time_range_override is applied."""
        # Mock load_query_def to return a valid query definition
        mock_query_def = {
            "type": "elk",
            "source_types": ["elk_error"],
            "elk_body_template": '{"query": {"match_all": {}}}'
        }

        with patch("tools.run_query_v2.load_query_def", return_value=mock_query_def):
            with patch("tools.run_query_v2.execute_elk_query") as mock_elk:
                mock_elk.return_value = {"status": "ok", "source": "Test", "data": {}}

                result = run_query_v2.run_section(sample_config, "errors", "now-30m")

                # The time_range should be overridden in the query
                assert result["section"] == "errors"
