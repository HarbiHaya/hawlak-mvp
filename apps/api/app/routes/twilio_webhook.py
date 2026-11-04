import logging
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response

from app.config import SettingsDep
from app.db import SessionDep
from app.services.inbound_workflow import InboundPersistenceError, InboundWorkflow
from app.services.object_storage import ObjectStorage, ObjectStorageError, StorageDep
from app.services.twilio_media import TwilioMediaTokenError, resolve_twilio_media_token
from app.services.twilio_signature import verify_twilio_signature
from app.services.whatsapp_factory import build_whatsapp_client

logger = logging.getLogger(__name__)
router = APIRouter()


def get_twilio_inbound_workflow(
    settings: SettingsDep,
    session: SessionDep,
) -> InboundWorkflow:
    storage = ObjectStorage(settings)
    return InboundWorkflow(session, storage, build_whatsapp_client(settings, storage))


@router.post("/webhooks/twilio")
async def receive_twilio_webhook(
    request: Request,
    settings: SettingsDep,
    workflow: Annotated[InboundWorkflow, Depends(get_twilio_inbound_workflow)],
    x_twilio_signature: Annotated[str | None, Header()] = None,
):
    if settings.whatsapp_provider != "twilio" or settings.twilio_auth_token is None:
        return JSONResponse({"error": "twilio_provider_disabled"}, status_code=404)
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/x-www-form-urlencoded":
        return JSONResponse({"error": "invalid_twilio_content_type"}, status_code=415)
    raw_body = await request.body()
    try:
        parameters = dict(parse_qsl(raw_body.decode(), keep_blank_values=True))
    except UnicodeDecodeError:
        return JSONResponse({"error": "invalid_twilio_payload"}, status_code=400)
    callback_url = f"{settings.public_base_url}{request.url.path}"
    if not verify_twilio_signature(
        callback_url,
        parameters,
        x_twilio_signature,
        settings.twilio_auth_token.get_secret_value(),
    ):
        return JSONResponse({"error": "invalid_twilio_signature"}, status_code=401)

    message_id = parameters.get("MessageSid")
    delivery_status = parameters.get("MessageStatus")
    if message_id and delivery_status:
        logger.info(
            "Twilio delivery status accepted message_sid=%s delivery_status=%s error_code=%s",
            message_id,
            delivery_status,
            parameters.get("ErrorCode"),
        )
        workflow.apply_delivery_status(message_id, delivery_status)
        return Response(status_code=204)

    sender = parameters.get("From", "").removeprefix("whatsapp:")
    if not message_id or not sender:
        return JSONResponse({"error": "invalid_twilio_payload"}, status_code=400)
    mime_type = parameters.get("MediaContentType0")
    media_url = parameters.get("MediaUrl0")
    button_payload = parameters.get("ButtonPayload")
    if button_payload:
        message_type = "button"
    else:
        message_type = "image" if mime_type and mime_type.startswith("image/") else "text"
    logger.info(
        "Twilio inbound message accepted message_sid=%s sender_suffix=%s message_type=%s",
        message_id,
        sender[-4:],
        message_type,
    )
    try:
        await workflow.ingest_message(
            wa_message_id=message_id,
            sender=sender,
            message_type=message_type,
            media_id=media_url,
            mime_type=mime_type,
            text=parameters.get("Body"),
            button_payload=button_payload,
        )
    except InboundPersistenceError:
        return JSONResponse({"error": "inbound_persistence_unavailable"}, status_code=503)
    return Response(status_code=204)


@router.api_route("/webhooks/twilio/media/{token}", methods=["GET", "HEAD"])
@router.api_route(
    "/webhooks/twilio/media/{token}/{filename}",
    methods=["GET", "HEAD"],
)
def fetch_twilio_media(
    token: str,
    request: Request,
    settings: SettingsDep,
    storage: StorageDep,
    filename: str | None = None,
):
    del filename
    if settings.whatsapp_provider != "twilio" or settings.twilio_auth_token is None:
        return JSONResponse({"error": "twilio_provider_disabled"}, status_code=404)
    try:
        media = resolve_twilio_media_token(
            token,
            settings.twilio_auth_token.get_secret_value(),
        )
        content = storage.get_bytes(media.object_key)
    except (TwilioMediaTokenError, ValueError):
        return JSONResponse({"error": "invalid_media_token"}, status_code=404)
    except ObjectStorageError:
        return JSONResponse({"error": "media_unavailable"}, status_code=503)
    response_filename = {
        "audio/ogg": "hawlak-voice.ogg",
        "image/jpeg": "hawlak-photo.jpg",
        "image/png": "hawlak-photo.png",
    }.get(media.content_type, "hawlak-media.bin")
    headers = {
        "Content-Length": str(len(content)),
        "Content-Disposition": f'inline; filename="{response_filename}"',
        "Cache-Control": "private, max-age=60",
    }
    return Response(
        content=b"" if request.method == "HEAD" else content,
        media_type=media.content_type,
        headers=headers,
    )
