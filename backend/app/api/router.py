from fastapi import APIRouter

from app.api.v1.overview import router as overview_router
from app.api.v1.logs import router as logs_router
from app.api.v1.apm import router as apm_router
from app.api.v1.infrastructure import router as infra_router
from app.api.v1.kubernetes import router as k8s_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.slo import router as slo_router
from app.api.v1.analyze import router as analyze_router
from app.api.v1.actions import router as actions_router  # Phase 2
from app.approvals.webhook import router as approvals_webhook_router  # Phase 2

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(overview_router)
v1_router.include_router(logs_router)
v1_router.include_router(apm_router)
v1_router.include_router(infra_router)
v1_router.include_router(k8s_router)
v1_router.include_router(alerts_router)
v1_router.include_router(slo_router)
v1_router.include_router(analyze_router)
v1_router.include_router(actions_router)  # Phase 2

api_router = APIRouter()
api_router.include_router(v1_router)
api_router.include_router(approvals_webhook_router)  # Phase 2 - webhook endpoints
