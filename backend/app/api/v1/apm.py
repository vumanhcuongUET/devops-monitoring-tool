from fastapi import APIRouter, Depends, Query

from app.api.deps import get_apm_client
from app.models.apm import Transaction, ApmError, ApmSummary
from app.security import validate_identifier
from app.services.apm_client import ApmClient

router = APIRouter(prefix="/apm", tags=["apm"])


@router.get("/transactions", response_model=list[Transaction])
async def get_transactions(
    service: str | None = Query(None, max_length=128),
    start: str | None = Query(None, max_length=32),
    end: str | None = Query(None, max_length=32),
    apm: ApmClient = Depends(get_apm_client),
):
    if service:
        service = validate_identifier(service, "service")
    return await apm.get_transactions(service=service, start=start, end=end)


@router.get("/errors", response_model=list[ApmError])
async def get_errors(
    service: str | None = Query(None, max_length=128),
    start: str | None = Query(None, max_length=32),
    end: str | None = Query(None, max_length=32),
    apm: ApmClient = Depends(get_apm_client),
):
    if service:
        service = validate_identifier(service, "service")
    return await apm.get_errors(service=service, start=start, end=end)


@router.get("/summary", response_model=ApmSummary)
async def get_summary(
    start: str | None = Query(None, max_length=32),
    end: str | None = Query(None, max_length=32),
    apm: ApmClient = Depends(get_apm_client),
):
    return await apm.get_summary(start=start, end=end)
