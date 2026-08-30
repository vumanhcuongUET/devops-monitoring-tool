from fastapi import APIRouter

from app.api.v1 import config as config_router  # Phase 7 Sprint 4
from app.api.v1.actions import router as actions_router  # Phase 2
from app.api.v1.agents import router as agents_router  # Phase 10 Sprint 3
from app.api.v1.alerts import router as alerts_router
from app.api.v1.analyze import router as analyze_router
from app.api.v1.apm import router as apm_router
from app.api.v1.autonomous import router as autonomous_router  # Phase 4
from app.api.v1.governance import router as governance_router  # Phase 3
from app.api.v1.infrastructure import router as infra_router
from app.api.v1.kubernetes import router as k8s_router
from app.api.v1.logs import router as logs_router
from app.api.v1.metrics import router as metrics_router  # Observability
from app.api.v1.overview import router as overview_router
from app.api.v1.skills import router as skills_router  # Phase 3
from app.api.v1.slo import router as slo_router
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
v1_router.include_router(agents_router)  # Phase 10 Sprint 3
v1_router.include_router(actions_router)  # Phase 2
v1_router.include_router(skills_router)  # Phase 3
v1_router.include_router(governance_router)  # Phase 3
v1_router.include_router(metrics_router)  # Observability
v1_router.include_router(autonomous_router)  # Phase 4
v1_router.include_router(config_router.router)  # Phase 7 Sprint 4

api_router = APIRouter()
api_router.include_router(v1_router)
api_router.include_router(approvals_webhook_router)  # Phase 2 - webhook endpoints
