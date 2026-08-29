from fastapi import Request

from app.services.apm_client import ApmClient
from app.services.elasticsearch_client import ElasticsearchClient
from app.services.kubernetes_client import KubernetesClient
from app.services.prometheus_client import PrometheusClient


def get_es_client(request: Request) -> ElasticsearchClient:
    return request.app.state.es_client


def get_prometheus_client(request: Request) -> PrometheusClient:
    return request.app.state.prometheus_client


def get_k8s_client(request: Request) -> KubernetesClient:
    return request.app.state.k8s_client


def get_apm_client(request: Request) -> ApmClient:
    return request.app.state.apm_client
