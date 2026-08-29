"""
Connection Pool Tests

Phase 9 - Sprint 1 - Day 4
Tests for connection pooling in service clients
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestElasticsearchConnectionPooling:
    """Test Elasticsearch client connection pooling."""

    @pytest.mark.asyncio
    async def test_elasticsearch_client_uses_connection_pool(self):
        """Test that Elasticsearch client is initialized with connection pooling."""
        from app.services.elasticsearch_client import ElasticsearchClient

        with patch("app.services.elasticsearch_client.AsyncElasticsearch") as mock_es:
            mock_instance = MagicMock()
            mock_instance.close = AsyncMock()
            mock_es.return_value = mock_instance

            client = ElasticsearchClient()

            # Verify AsyncElasticsearch was called with connection pool settings
            mock_es.assert_called_once()
            call_kwargs = mock_es.call_args[1]

            assert "max_connections" not in call_kwargs  # invalid es-py 8.x kwarg (review N1)
            assert call_kwargs["max_retries"] == 3
            assert call_kwargs["retry_on_timeout"] is True
            assert call_kwargs["http_compress"] is True

    @pytest.mark.asyncio
    async def test_elasticsearch_client_close(self):
        """Test that Elasticsearch client can be closed properly."""
        from app.services.elasticsearch_client import ElasticsearchClient

        with patch("app.services.elasticsearch_client.AsyncElasticsearch") as mock_es:
            mock_instance = MagicMock()
            mock_instance.close = AsyncMock()
            mock_es.return_value = mock_instance

            client = ElasticsearchClient()
            await client.close()

            mock_instance.close.assert_called_once()


class TestPrometheusConnectionPooling:
    """Test Prometheus client connection pooling."""

    @pytest.mark.asyncio
    async def test_prometheus_client_uses_connection_pool(self):
        """Test that Prometheus client uses persistent client with pooling."""
        from app.services.prometheus_client import PrometheusClient

        with patch("app.services.prometheus_client.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get = AsyncMock()
            mock_instance.aclose = AsyncMock()
            mock_client.return_value = mock_instance

            client = PrometheusClient()

            # Verify httpx.AsyncClient was called with connection pool settings
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]

            assert "limits" in call_kwargs
            assert call_kwargs["http2"] is True

    @pytest.mark.asyncio
    async def test_prometheus_client_close(self):
        """Test that Prometheus client can be closed properly."""
        from app.services.prometheus_client import PrometheusClient

        with patch("app.services.prometheus_client.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get = AsyncMock()
            mock_instance.aclose = AsyncMock()
            mock_client.return_value = mock_instance

            client = PrometheusClient()
            await client.close()

            mock_instance.aclose.assert_called_once()


class TestKubernetesConnectionPooling:
    """Test Kubernetes client connection pooling."""

    @pytest.mark.asyncio
    async def test_kubernetes_client_uses_connection_pool(self):
        """Test that Kubernetes client is configured with connection pooling."""
        from app.config import settings
        from app.services.kubernetes_client import KubernetesClient

        with patch("app.services.kubernetes_client.k8s_config") as mock_config:
            with patch("app.services.kubernetes_client.client.CoreV1Api") as mock_core:
                with patch("app.services.kubernetes_client.client.AppsV1Api") as mock_apps:
                    with patch("app.services.kubernetes_client.client.Configuration") as mock_configuration:
                        mock_config.load_kube_config = MagicMock()
                        mock_configuration_obj = MagicMock()
                        mock_configuration.get_default_copy.return_value = mock_configuration_obj

                        client = KubernetesClient()

                        # Verify configuration was set with connection pool size
                        assert mock_configuration_obj.connection_pool_size == getattr(settings, "K8S_MAX_CONNECTIONS", 10)


class TestConnectionPoolConfiguration:
    """Test connection pool configuration from settings."""

    def test_default_pool_sizes(self):
        """Test that default pool sizes are set correctly."""
        from app.config import settings

        # ES_MAX_CONNECTIONS removed with the invalid kwarg (review N1)
        assert hasattr(settings, "PROM_MAX_CONNECTIONS")
        assert hasattr(settings, "K8S_MAX_CONNECTIONS")

        # Verify default values
        assert settings.PROM_MAX_CONNECTIONS == 20
        assert settings.K8S_MAX_CONNECTIONS == 10

    def test_pool_size_values_are_positive(self):
        """Test that pool sizes are positive integers."""
        from app.config import settings

        assert settings.PROM_MAX_CONNECTIONS > 0
        assert settings.K8S_MAX_CONNECTIONS > 0


@pytest.mark.asyncio
async def test_all_service_clients_have_close_method():
    """Test that all service clients have a close method for cleanup."""
    from app.services.elasticsearch_client import ElasticsearchClient
    from app.services.prometheus_client import PrometheusClient

    with patch("app.services.elasticsearch_client.AsyncElasticsearch") as mock_es:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_es.return_value = mock_instance

        es_client = ElasticsearchClient()
        assert hasattr(es_client, "close")
        assert callable(es_client.close)

    with patch("app.services.prometheus_client.httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.aclose = AsyncMock()
        mock_client.return_value = mock_instance

        prom_client = PrometheusClient()
        assert hasattr(prom_client, "close")
        assert callable(prom_client.close)

    # Kubernetes client doesn't have a close method (uses sync APIs)
    # This is expected behavior
