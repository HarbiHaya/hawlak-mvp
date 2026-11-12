from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CareJourney, DeliveryRun, PatientCase, utc_now
from app.schemas.voice import ApprovedVoiceScript
from app.services.object_storage import ObjectStorage
from app.services.voice_renderer import build_voice_renderer, checksum_script
from app.services.whatsapp_client import WhatsAppClient
from app.services.whatsapp_factory import build_whatsapp_client


class JourneyDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JourneyDeliveryPayload:
    run_id: str
    case_id: str
    kind: str
    content_ref: str
    scheduled_at: datetime
    phone_e164: str
    approved_by: str
    voice_script: str | None = None
    image_object_key: str | None = None
    image_content_type: str | None = None


class JourneyDeliveryAdapter(Protocol):
    async def deliver(self, payload: JourneyDeliveryPayload) -> str: ...


class MockJourneyDeliveryAdapter:
    async def deliver(self, payload: JourneyDeliveryPayload) -> str:
        return f"mock:{payload.kind}:{payload.run_id}"


class LiveJourneyDeliveryAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._storage = ObjectStorage(settings)
        client = build_whatsapp_client(settings, self._storage)
        if not isinstance(client, WhatsAppClient):
            raise JourneyDeliveryError("journey delivery requires the configured Meta provider")
        self._whatsapp = client
        self._renderer = build_voice_renderer(settings)

    async def deliver(self, payload: JourneyDeliveryPayload) -> str:
        if payload.kind == "follow_up_call":
            return await self._dispatch_call(payload)
        if not payload.voice_script:
            raise JourneyDeliveryError("approved voice script is missing")

        checksum = checksum_script(payload.voice_script)
        rendered = await self._renderer.render(
            ApprovedVoiceScript(
                artifactId=payload.run_id,
                caseId=payload.case_id,
                synthetic=True,
                spokenTextAr=payload.voice_script,
                scriptChecksum=checksum,
                approved=True,
                approvedBy=payload.approved_by,
            )
        )
        audio_id = await self._whatsapp.upload_audio(
            rendered.audio,
            f"hawlak-{payload.run_id}.ogg",
        )
        voice_message_id = await self._whatsapp.send_audio(payload.phone_e164, audio_id)
        if payload.kind == "discharge_voice_note":
            return voice_message_id

        if not payload.image_object_key or not payload.image_content_type:
            raise JourneyDeliveryError("approved medication image is missing")
        image = self._storage.get_bytes(payload.image_object_key)
        suffix = PurePosixPath(payload.image_object_key).suffix or ".jpg"
        image_id = await self._whatsapp.upload_image(
            image,
            f"medicine-{payload.run_id}{suffix}",
            payload.image_content_type,
        )
        reminder_message_id = await self._whatsapp.send_photo_reminder(
            payload.phone_e164,
            image_id,
        )
        return f"{voice_message_id},{reminder_message_id}"

    async def _dispatch_call(self, payload: JourneyDeliveryPayload) -> str:
        if (
            self._settings.hawlak_agent_control_url is None
            or self._settings.hawlak_control_token is None
        ):
            raise JourneyDeliveryError("call control is not configured")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._settings.hawlak_agent_control_url}/calls",
                    headers={
                        "Authorization": (
                            "Bearer " + self._settings.hawlak_control_token.get_secret_value()
                        ),
                        "Idempotency-Key": payload.run_id,
                    },
                    json={
                        "callPlanId": payload.run_id,
                        "caseId": payload.case_id,
                        "scheduledAt": payload.scheduled_at.isoformat(),
                    },
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise JourneyDeliveryError("call control is unavailable") from exc
        if response.is_error:
            raise JourneyDeliveryError(f"call control rejected dispatch ({response.status_code})")
        try:
            dispatch_id = response.json()["dispatch"]["dispatchId"]
        except (KeyError, TypeError, ValueError) as exc:
            raise JourneyDeliveryError("call control returned an invalid receipt") from exc
        return str(dispatch_id)


class JourneyDeliveryOrchestrator:
    """Claims and delivers every due run for one approved case."""

    def __init__(self, session: Session, adapter: JourneyDeliveryAdapter) -> None:
        self._session = session
        self._adapter = adapter

    async def dispatch_due(self, case_id: str) -> list[DeliveryRun]:
        journey = self._session.get(CareJourney, case_id)
        patient = self._session.get(PatientCase, case_id)
        if journey is None or patient is None:
            raise JourneyDeliveryError("case_not_found")
        if journey.review_status != "approved" or not journey.approved_by:
            raise JourneyDeliveryError("case_not_approved")

        runs = list(
            self._session.scalars(
                select(DeliveryRun)
                .where(
                    DeliveryRun.case_id == case_id,
                    DeliveryRun.scheduled_at <= utc_now(),
                )
                .order_by(DeliveryRun.created_at, DeliveryRun.id)
            ).all()
        )
        for run in runs:
            if run.status in {"sent", "completed", "transferred"}:
                continue
            if run.status == "failed":
                continue
            if run.status == "pending":
                run.status = "claimed"
                self._session.commit()
            try:
                run.provider_ref = await self._adapter.deliver(self._payload(run, journey, patient))
                run.status = "sent"
            except Exception as exc:
                run.status = "failed"
                run.provider_ref = type(exc).__name__
            self._session.commit()
        return runs

    @staticmethod
    def _payload(
        run: DeliveryRun,
        journey: CareJourney,
        patient: PatientCase,
    ) -> JourneyDeliveryPayload:
        script: str | None = None
        image_key: str | None = None
        image_type: str | None = None
        if run.kind == "discharge_voice_note":
            script = journey.discharge_voice_note.get("script")
        elif run.kind == "medication_reminder":
            medication_id = run.content_ref.split(":", 1)[-1]
            medication = next(
                (item for item in journey.medications if item.get("medicationId") == medication_id),
                None,
            )
            if medication:
                script = medication.get("reminderScript")
                image = medication.get("image") or {}
                image_key = image.get("objectKey")
                image_type = _image_content_type(image_key)
        return JourneyDeliveryPayload(
            run_id=run.id,
            case_id=run.case_id,
            kind=run.kind,
            content_ref=run.content_ref,
            scheduled_at=run.scheduled_at,
            phone_e164=patient.phone_e164,
            approved_by=journey.approved_by or "",
            voice_script=script,
            image_object_key=image_key,
            image_content_type=image_type,
        )


def build_journey_delivery_adapter(settings: Settings) -> JourneyDeliveryAdapter:
    if settings.demo_provider_mode == "mock":
        return MockJourneyDeliveryAdapter()
    return LiveJourneyDeliveryAdapter(settings)


def _image_content_type(object_key: str | None) -> str | None:
    if not object_key:
        return None
    return {
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(PurePosixPath(object_key).suffix.lower(), "image/jpeg")
