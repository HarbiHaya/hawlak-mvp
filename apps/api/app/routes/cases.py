from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.db import SessionDep
from app.schemas.approved_plan import (
    CaseResponse,
    CaseTimelineResponse,
    CreateCaseRequest,
)
from app.services.case_service import CaseConflictError, CaseNotFoundError, CaseService

router = APIRouter()


@router.post("/cases", response_model=CaseResponse, status_code=201)
def create_case(body: CreateCaseRequest, response: Response, session: SessionDep):
    try:
        result = CaseService(session).create_case(body, body.demo_recipient)
    except CaseConflictError:
        return JSONResponse(status_code=409, content={"error": "case_conflict"})
    if not result.created:
        response.status_code = 200
    return CaseResponse(
        case_id=result.case.id,
        plan_id=result.plan.id,
        version=result.plan.version,
        status=result.case.status,
    )


@router.get("/cases/{case_id}/timeline", response_model=CaseTimelineResponse)
def case_timeline(case_id: str, session: SessionDep):
    try:
        entries = CaseService(session).get_timeline(case_id)
    except CaseNotFoundError:
        return JSONResponse(status_code=404, content={"error": "case_not_found"})
    return {"case_id": case_id, "data": entries}
