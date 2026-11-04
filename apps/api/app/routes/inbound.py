from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.routes.whatsapp_webhook import get_inbound_workflow
from app.services.inbound_workflow import InboundWorkflow

router = APIRouter()


@router.post("/inbound/{wa_message_id}/retry")
async def retry_inbound_message(
    wa_message_id: str,
    workflow: Annotated[InboundWorkflow, Depends(get_inbound_workflow)],
):
    result = await workflow.retry_failed_message(wa_message_id)
    if result == "not_found":
        return JSONResponse(status_code=404, content={"error": "inbound_message_not_found"})
    if result == "not_retryable":
        return JSONResponse(status_code=409, content={"error": "inbound_message_not_retryable"})
    if result == "failed":
        return JSONResponse(status_code=503, content={"error": "inbound_retry_failed"})
    return {"status": "processed", "waMessageId": wa_message_id}
