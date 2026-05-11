from fastapi import APIRouter, Depends, Query

from app.api.deps import get_k8s_client
from app.models.kubernetes import PodStatus, DeploymentStatus, K8sEvent
from app.security import validate_identifier
from app.services.kubernetes_client import KubernetesClient

router = APIRouter(prefix="/kubernetes", tags=["kubernetes"])


@router.get("/pods", response_model=list[PodStatus])
async def get_pods(
    namespace: str | None = Query(None, max_length=128),
    k8s: KubernetesClient = Depends(get_k8s_client),
):
    if namespace:
        namespace = validate_identifier(namespace, "namespace")
    return await k8s.list_pods(namespace=namespace)


@router.get("/deployments", response_model=list[DeploymentStatus])
async def get_deployments(
    namespace: str | None = Query(None, max_length=128),
    k8s: KubernetesClient = Depends(get_k8s_client),
):
    if namespace:
        namespace = validate_identifier(namespace, "namespace")
    return await k8s.list_deployments(namespace=namespace)


@router.get("/events", response_model=list[K8sEvent])
async def get_events(
    namespace: str | None = Query(None, max_length=128),
    k8s: KubernetesClient = Depends(get_k8s_client),
):
    if namespace:
        namespace = validate_identifier(namespace, "namespace")
    return await k8s.get_events(namespace=namespace)
