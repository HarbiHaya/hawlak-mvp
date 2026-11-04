from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.config import SettingsDep
from app.db import SessionDep
from app.models import InboundMedia, MessageLog, PatientCase
from app.schemas.voice import ApprovedVoiceScript
from app.services.object_storage import ObjectStorage
from app.services.twilio_client import TwilioWhatsAppClient
from app.services.voice_renderer import build_voice_renderer, checksum_script
from app.services.whatsapp_factory import build_whatsapp_client

router = APIRouter()

REMINDER_INSTRUCTION_AR = (
    "هذا تذكير بدواك. شوفي صورة الدواء. اضغطي واحد إذا أخذتي الجرعة، أو اثنين إذا ما أخذتيها."
)


class ReminderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    media_id: str = Field(alias="mediaId", min_length=1)
    reminder_id: str = Field(
        default="default",
        alias="reminderId",
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
    )


@router.post("/cases/{case_id}/send-photo-reminder")
async def send_photo_reminder(
    case_id: str,
    body: ReminderRequest,
    settings: SettingsDep,
    session: SessionDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    patient_case = session.get(PatientCase, case_id)
    media = session.scalar(
        select(InboundMedia).where(
            InboundMedia.id == body.media_id,
            InboundMedia.case_id == case_id,
            InboundMedia.processing_status == "stored",
        )
    )
    if patient_case is None or media is None or not media.object_key:
        return JSONResponse(status_code=404, content={"error": "stored_photo_not_found"})
    occurrence = (
        media.id
        if body.reminder_id == "default"
        else sha256(f"{media.id}:{body.reminder_id}".encode()).hexdigest()[:24]
    )
    audio_step = f"medication_audio:{occurrence}"
    poll_step = f"medication_reminder:{occurrence}"
    existing_audio = session.scalar(
        select(MessageLog).where(
            MessageLog.case_id == case_id,
            MessageLog.outbound_step == audio_step,
        )
    )
    existing_poll = session.scalar(
        select(MessageLog).where(
            MessageLog.case_id == case_id,
            MessageLog.outbound_step == poll_step,
        )
    )
    if existing_poll is not None and existing_poll.wa_message_id:
        return {
            "voiceMessageId": existing_audio.wa_message_id if existing_audio else None,
            "messageId": existing_poll.wa_message_id,
            "mediaId": media.id,
        }

    storage = ObjectStorage(settings)
    whatsapp = build_whatsapp_client(settings, storage)
    if not isinstance(whatsapp, TwilioWhatsAppClient):
        return JSONResponse(status_code=409, content={"error": "reminder_requires_twilio"})

    voice_message_id = existing_audio.wa_message_id if existing_audio else None
    if not voice_message_id:
        script_checksum = checksum_script(REMINDER_INSTRUCTION_AR)
        renderer = build_voice_renderer(settings)
        rendered = await renderer.render(
            ApprovedVoiceScript(
                artifactId=f"medication-reminder:{occurrence}",
                caseId=case_id,
                synthetic=True,
                spokenTextAr=REMINDER_INSTRUCTION_AR,
                scriptChecksum=script_checksum,
                approved=True,
                approvedBy="prototype-flow-v1",
            )
        )
        audio_url = await whatsapp.upload_audio(
            rendered.audio,
            f"hawlak-reminder-{occurrence}.ogg",
        )
        voice_message_id = await whatsapp.send_audio(patient_case.phone_e164, audio_url)
        audio_log = existing_audio or MessageLog(
            case_id=case_id,
            direction="outbound",
            message_type="audio",
            processing_status="sent",
            normalized_payload={},
            outbound_step=audio_step,
            idempotency_key=f"{idempotency_key}:audio",
        )
        audio_log.wa_message_id = voice_message_id
        audio_log.delivery_status = None
        audio_log.normalized_payload = {
            "reminderId": body.reminder_id,
            "scriptChecksum": script_checksum,
            "audioChecksum": rendered.audio_checksum,
            "choiceMap": {"١": "taken", "٢": "not_yet"},
        }
        if existing_audio is None:
            session.add(audio_log)
        session.commit()

    message_id = await whatsapp.send_photo_reminder(
        patient_case.phone_e164,
        object_key=media.object_key,
        content_type=media.mime_type,
    )
    log = existing_poll or MessageLog(
        case_id=case_id,
        direction="outbound",
        message_type="interactive",
        processing_status="sent",
        normalized_payload={},
        outbound_step=poll_step,
        idempotency_key=f"{idempotency_key}:reminder",
    )
    log.wa_message_id = message_id
    log.delivery_status = None
    log.normalized_payload = {
        "mediaId": media.id,
        "reminderId": body.reminder_id,
        "poll": {"١": "taken", "٢": "not_yet"},
    }
    if existing_poll is None:
        session.add(log)
    session.commit()
    return {
        "voiceMessageId": voice_message_id,
        "messageId": message_id,
        "mediaId": media.id,
    }
