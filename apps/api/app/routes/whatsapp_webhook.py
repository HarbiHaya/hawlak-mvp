import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from app.config import SettingsDep
from app.db import SessionDep
from app.services.inbound_workflow import InboundPersistenceError, InboundWorkflow
from app.services.medicine_photos import build_label_reader
from app.services.meta_signature import verify_meta_signature
from app.services.object_storage import ObjectStorage
from app.services.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)
router = APIRouter()


# Only the parts of Meta's payload we use. Everything is optional because the same endpoint
# receives messages, delivery statuses and account updates.
class Image(BaseModel):
    id: str | None = None
    mime_type: str | None = None


class Text(BaseModel):
    body: str | None = None


class ButtonReply(BaseModel):
    id: str | None = None
    title: str | None = None


class Interactive(BaseModel):
    type: str | None = None
    button_reply: ButtonReply | None = None


class Message(BaseModel):
    id: str | None = None
    sender: str = Field("", alias="from")
    type: str | None = None
    image: Image | None = None
    text: Text | None = None
    interactive: Interactive | None = None


class StatusError(BaseModel):
    code: int | None = None
    title: str | None = None


class Status(BaseModel):
    id: str | None = None
    status: str | None = None
    errors: list[StatusError] = []


class ChangeValue(BaseModel):
    messages: list[Message] = []
    statuses: list[Status] = []


class Change(BaseModel):
    value: ChangeValue | None = None


class Entry(BaseModel):
    changes: list[Change] = []


class WebhookPayload(BaseModel):
    entry: list[Entry] = []


def get_inbound_workflow(
    settings: SettingsDep,
    session: SessionDep,
) -> InboundWorkflow:
    whatsapp = WhatsAppClient(
        settings.meta_graph_api_version,
        settings.whatsapp_phone_number_id,
        settings.whatsapp_access_token,
    )
    return InboundWorkflow(session, ObjectStorage(settings), whatsapp, build_label_reader(settings))


@router.get("/webhooks/whatsapp")
async def verify_webhook(
    settings: SettingsDep,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
):
    token_matches = verify_token is not None and hmac.compare_digest(
        verify_token.encode(), settings.whatsapp_verify_token.encode()
    )
    if mode == "subscribe" and token_matches and challenge:
        return PlainTextResponse(challenge)
    return JSONResponse({"error": "webhook_verification_failed"}, status_code=403)


@router.post("/webhooks/whatsapp")
async def receive_webhook(
    request: Request,
    settings: SettingsDep,
    workflow: Annotated[InboundWorkflow, Depends(get_inbound_workflow)],
    x_hub_signature_256: Annotated[str | None, Header()] = None,
):
    # Verify the exact bytes Meta signed before trusting, or even parsing, the body.
    raw_body = await request.body()
    if not verify_meta_signature(raw_body, x_hub_signature_256, settings.meta_app_secret):
        return JSONResponse({"error": "invalid_webhook_signature"}, status_code=401)

    try:
        payload = WebhookPayload.model_validate_json(raw_body)
    except ValidationError:
        return JSONResponse({"error": "invalid_webhook_payload"}, status_code=400)

    for entry in payload.entry:
        for change in entry.changes:
            value = change.value or ChangeValue()
            for message in value.messages:
                button_reply = message.interactive.button_reply if message.interactive else None
                message_type = "button" if button_reply and button_reply.id else message.type
                logger.info(
                    "WhatsApp inbound message accepted wa_message_id=%s sender_suffix=%s "
                    "message_type=%s media_id=%s",
                    message.id,
                    message.sender[-4:],
                    message_type,
                    message.image.id if message.image else None,
                )
                if message.id:
                    try:
                        await workflow.ingest_message(
                            wa_message_id=message.id,
                            sender=message.sender,
                            message_type=message_type or "unknown",
                            media_id=message.image.id if message.image else None,
                            mime_type=message.image.mime_type if message.image else None,
                            text=(
                                button_reply.title
                                if button_reply
                                else message.text.body
                                if message.text
                                else None
                            ),
                            button_payload=button_reply.id if button_reply else None,
                        )
                    except InboundPersistenceError:
                        return JSONResponse(
                            {"error": "inbound_persistence_unavailable"}, status_code=503
                        )
            for status in value.statuses:
                first_error = status.errors[0] if status.errors else StatusError()
                logger.info(
                    "WhatsApp delivery status accepted wa_message_id=%s delivery_status=%s "
                    "error_code=%s error_title=%s",
                    status.id,
                    status.status,
                    first_error.code,
                    first_error.title,
                )
                if status.id:
                    workflow.apply_delivery_status(status.id, status.status)

    return {"received": True}
