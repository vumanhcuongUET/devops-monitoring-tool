from pydantic import BaseModel


class PodStatus(BaseModel):
    name: str = ""
    namespace: str = ""
    status: str = ""
    restarts: int = 0
    age: str = ""
    node: str = ""


class DeploymentStatus(BaseModel):
    name: str = ""
    namespace: str = ""
    replicas: int = 0
    available: int = 0
    updated: int = 0
    image: str = ""


class K8sEvent(BaseModel):
    timestamp: str = ""
    type: str = ""
    reason: str = ""
    message: str = ""
    object: str = ""
