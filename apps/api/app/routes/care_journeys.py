from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import SessionDep
from app.models import CareJourney
from app.schemas.care_journey import (
    ApprovalRequest,
    CallOutcomeRequest,
    CareJourneyContent,
    CareJourneyCreate,
    DeliveryRunUpdate,
    EligibilityRequest,
)
from app.services.care_journey_service import (
    DEFAULT_CALL_PLAN,
    CareJourneyService,
    JourneyConflict,
    JourneyNotFound,
    drafted_content,
)
from app.services.discharge_parser import draft_medications, parse_discharge_pdf
from app.services.journey_drafter import build_journey_drafter
from app.services.object_storage import ObjectStorageError, StorageDep

router = APIRouter()
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_MEDICATION_IMAGE_BYTES = 10 * 1024 * 1024
MEDICATION_IMAGE_TYPES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
FILE_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}
FILE_TYPES |= {".jpeg": "image/jpeg", ".webp": "image/webp"}


def get_journey_drafter():
    return build_journey_drafter(get_settings())


DrafterDep = Annotated[object, Depends(get_journey_drafter)]


def error_response(exc: RuntimeError):
    if isinstance(exc, JourneyNotFound):
        return JSONResponse(status_code=404, content={"error": "case_not_found"})
    return JSONResponse(status_code=409, content={"error": str(exc)})


@router.post("/workspace/documents", status_code=201)
async def upload_discharge_document(
    request: Request,
    storage: StorageDep,
    case_id: Annotated[
        str, Header(alias="X-Case-Id", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    ],
    filename: Annotated[str, Header(alias="X-Filename", min_length=5, max_length=255)],
):
    """Store a PDF body without parsing its clinical content at the web edge."""
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/pdf":
        return JSONResponse(status_code=415, content={"error": "pdf_required"})
    if not filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=422, content={"error": "pdf_filename_required"})
    content = await request.body()
    if not content.startswith(b"%PDF-"):
        return JSONResponse(status_code=422, content={"error": "invalid_pdf"})
    if len(content) > MAX_DOCUMENT_BYTES:
        return JSONResponse(status_code=413, content={"error": "document_too_large"})
    try:
        stored = storage.store_case_media(
            case_id=case_id,
            content=content,
            content_type="application/pdf",
            source_media_id=filename,
        )
    except ObjectStorageError:
        return JSONResponse(status_code=503, content={"error": "storage_unavailable"})
    return {"objectKey": stored.key, "filename": filename}


@router.post("/workspace/cases/{case_id}/medication-images", status_code=201)
async def upload_medication_image(
    case_id: str,
    request: Request,
    storage: StorageDep,
    session: SessionDep,
    filename: Annotated[str, Header(alias="X-Filename", min_length=3, max_length=255)],
):
    if session.get(CareJourney, case_id) is None:
        return JSONResponse(status_code=404, content={"error": "case_not_found"})
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    signatures = MEDICATION_IMAGE_TYPES.get(content_type)
    if signatures is None:
        return JSONResponse(status_code=415, content={"error": "image_required"})
    content = await request.body()
    if not content or len(content) > MAX_MEDICATION_IMAGE_BYTES:
        return JSONResponse(status_code=413, content={"error": "image_size_invalid"})
    if content_type == "image/webp":
        valid_signature = content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    else:
        valid_signature = any(content.startswith(signature) for signature in signatures)
    if not valid_signature:
        return JSONResponse(status_code=422, content={"error": "invalid_image"})
    try:
        stored = storage.store_case_media(
            case_id=case_id,
            content=content,
            content_type=content_type,
            source_media_id=filename,
        )
    except ObjectStorageError:
        return JSONResponse(status_code=503, content={"error": "storage_unavailable"})
    return {
        "objectKey": stored.key,
        "filename": filename,
        "contentType": content_type,
    }


@router.post("/workspace/cases", status_code=201)
def create_workspace_case(
    body: CareJourneyCreate,
    response: Response,
    session: SessionDep,
    storage: StorageDep,
    drafter: DrafterDep,
):
    content = generated = None
    is_new = session.get(CareJourney, body.case_id) is None
    if is_new and body.medications is None and body.discharge_voice_note is None:
        # Draft the insurer's review from the hospital PDF. Approval still gates every word.
        pdf = _case_bytes(body.case_id, body.source_document.object_key, storage)
        extraction = parse_discharge_pdf(pdf) if pdf else None
        if extraction is not None and extraction.status == "parsed":
            drafted, generated = drafted_content(
                extraction,
                drafter,
                medications=draft_medications(extraction),
                call_plan=DEFAULT_CALL_PLAN,
                label=body.preferred_form_of_address or body.patient_name,
                language=body.language_code,
                dialect=body.dialect_code,
            )
            content = CareJourneyContent.model_validate(drafted)
    try:
        result = CareJourneyService(session).intake(body, content, generated)
    except JourneyConflict as exc:
        return error_response(exc)
    if not result.created:
        response.status_code = 200
    return {"caseId": result.journey.case_id, "reviewStatus": result.journey.review_status}


@router.get("/workspace/cases")
def list_workspace_cases(session: SessionDep):
    return {"data": CareJourneyService(session).list_cases()}


@router.get("/workspace/cases/{case_id}")
def workspace_case_detail(case_id: str, session: SessionDep):
    try:
        return _detail(CareJourneyService(session), case_id)
    except JourneyNotFound as exc:
        return error_response(exc)


@router.get("/workspace/cases/{case_id}/files")
def case_file(case_id: str, key: str, session: SessionDep, storage: StorageDep):
    """Stream a stored discharge PDF or medication image so the reviewer can see it."""
    content = _case_bytes(case_id, key, storage) if session.get(CareJourney, case_id) else None
    if content is None:
        return JSONResponse(status_code=404, content={"error": "file_not_found"})
    media_type = FILE_TYPES.get(PurePosixPath(key).suffix.lower(), "application/octet-stream")
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/workspace/cases/{case_id}/draft")
def regenerate_draft(case_id: str, session: SessionDep, storage: StorageDep, drafter: DrafterDep):
    """Redraft the voice note, reminders and call scripts from the PDF and current medicines."""
    journey = session.get(CareJourney, case_id)
    pdf = _case_bytes(case_id, journey.source_document["objectKey"], storage) if journey else None
    if journey is None:
        return error_response(JourneyNotFound(case_id))
    extraction = parse_discharge_pdf(pdf) if pdf else None
    if extraction is None or extraction.status != "parsed":
        return JSONResponse(status_code=409, content={"error": "document_not_readable"})
    service = CareJourneyService(session)
    try:
        service.regenerate(case_id, extraction, drafter)
        return _detail(service, case_id)
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)


@router.post("/workspace/cases/{case_id}/eligibility")
def check_eligibility(case_id: str, body: EligibilityRequest, session: SessionDep):
    service = CareJourneyService(session)
    try:
        service.check_eligibility(case_id, body.member_id)
        return _detail(service, case_id)
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)


@router.get("/workspace/cases/{case_id}/extraction")
def case_extraction(case_id: str, session: SessionDep, storage: StorageDep):
    """Show the insurer what was read from the discharge PDF, next to the draft."""
    journey = session.get(CareJourney, case_id)
    key = journey.source_document["objectKey"] if journey else ""
    content = _case_bytes(case_id, key, storage) if journey else None
    if content is None:
        return JSONResponse(status_code=404, content={"error": "file_not_found"})
    return parse_discharge_pdf(content).to_api()


def _detail(service: CareJourneyService, case_id: str) -> dict:
    # In mock mode the worker marks runs sent without contacting WhatsApp or the caller.
    return {**service.detail(case_id), "deliveryMode": get_settings().demo_provider_mode}


def _case_bytes(case_id: str, key: str, storage) -> bytes | None:
    """Read a stored object only when it belongs to this case."""
    path = PurePosixPath(key)
    if not key.startswith(f"cases/{case_id}/") or ".." in path.parts:
        return None
    try:
        return storage.get_bytes(key)
    except ObjectStorageError:
        return None


@router.patch("/workspace/cases/{case_id}/content")
def replace_workspace_case_content(case_id: str, body: CareJourneyContent, session: SessionDep):
    try:
        journey = CareJourneyService(session).replace_content(case_id, body)
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)
    return {"caseId": journey.case_id, "reviewStatus": journey.review_status}


@router.post("/workspace/cases/{case_id}/approve")
def approve_workspace_case(
    case_id: str,
    body: ApprovalRequest,
    session: SessionDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    service = CareJourneyService(session)
    try:
        runs = service.approve(case_id, body.approved_by, idempotency_key)
        journey = service.detail(case_id)
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)
    return {
        "caseId": case_id,
        "reviewStatus": journey["reviewStatus"],
        "insurance": journey["insurance"],
        "deliveryRuns": [service.run_view(run) for run in runs],
    }


@router.get("/workspace/alerts")
def workspace_alerts(session: SessionDep):
    return {"data": CareJourneyService(session).alerts()}


@router.post("/workspace/alerts/{alert_id}/resolve")
def resolve_workspace_alert(alert_id: str, session: SessionDep):
    try:
        alert = CareJourneyService(session).resolve_alert(alert_id)
    except JourneyNotFound:
        return JSONResponse(status_code=404, content={"error": "alert_not_found"})
    return {"id": alert.id, "status": alert.status}


@router.get("/caregiver/cases/{case_id}")
def caregiver_case(case_id: str, session: SessionDep):
    try:
        return CareJourneyService(session).caregiver(case_id)
    except JourneyNotFound as exc:
        return error_response(exc)


@router.get("/call-plans/{plan_or_case_id}")
def approved_call_plan(plan_or_case_id: str, session: SessionDep):
    try:
        return CareJourneyService(session).call_plan(plan_or_case_id)
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)


@router.get("/delivery-runs")
def pending_delivery_runs(session: SessionDep, kind: str | None = None):
    service = CareJourneyService(session)
    return {"data": [service.run_view(run) for run in service.pending_runs(kind)]}


@router.post("/delivery-runs/{run_id}/claim")
def claim_delivery_run(
    run_id: str,
    session: SessionDep,
    _: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    service = CareJourneyService(session)
    try:
        return service.run_view(service.claim_run(run_id))
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)


@router.patch("/delivery-runs/{run_id}")
def update_delivery_run(run_id: str, body: DeliveryRunUpdate, session: SessionDep):
    service = CareJourneyService(session)
    try:
        return service.run_view(service.update_run(run_id, body.status, body.provider_ref))
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)


@router.post("/delivery-runs/{run_id}/call-outcome")
def record_call_outcome(
    run_id: str,
    body: CallOutcomeRequest,
    session: SessionDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=256)],
):
    service = CareJourneyService(session)
    escalation = body.escalation.model_dump(mode="json", by_alias=True) if body.escalation else None
    try:
        run = service.record_call_outcome(
            run_id,
            idempotency_key,
            body.status,
            body.provider_ref,
            escalation,
        )
    except (JourneyNotFound, JourneyConflict) as exc:
        return error_response(exc)
    return service.run_view(run)
