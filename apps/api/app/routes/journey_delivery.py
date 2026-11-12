from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from app.config import SettingsDep
from app.db import SessionDep
from app.services.care_journey_service import CareJourneyService
from app.services.journey_delivery import (
    JourneyDeliveryError,
    JourneyDeliveryOrchestrator,
    build_journey_delivery_adapter,
)

router = APIRouter()


@router.post("/workspace/cases/{case_id}/dispatch")
async def dispatch_workspace_case(
    case_id: str,
    settings: SettingsDep,
    session: SessionDep,
    _: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
):
    orchestrator = JourneyDeliveryOrchestrator(
        session,
        build_journey_delivery_adapter(settings),
    )
    try:
        runs = await orchestrator.dispatch_due(case_id)
    except JourneyDeliveryError as exc:
        status = 404 if str(exc) == "case_not_found" else 409
        return JSONResponse(status_code=status, content={"error": str(exc)})
    return {"data": [CareJourneyService.run_view(run) for run in runs]}
