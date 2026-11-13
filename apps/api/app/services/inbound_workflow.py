import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    ApprovedPlan,
    CareJourney,
    InboundMedia,
    MessageLog,
    PatientCase,
    WorkflowEvent,
    new_id,
)
from app.schemas.review_event import PharmacistReviewRequested
from app.services.medicine_photos import MISMATCH, LabelReading, compare_reading, reply
from app.services.object_storage import ObjectStorageError
from app.services.whatsapp_client import WhatsAppApiError, WhatsAppMediaError

logger = logging.getLogger(__name__)

SAFE_REPLY = "وصلت رسالتك، وبنخلي الفريق الصحي يراجعها. إذا عندك حالة طارئة اتصل على الإسعاف ٩٩٧."


class StorageLike(Protocol):
    def store_case_media(
        self, *, case_id: str, content: bytes, content_type: str, source_media_id: str
    ): ...


class WhatsAppLike(Protocol):
    async def download_image(self, media_id: str): ...

    async def send_text(self, to: str, text: str) -> str: ...


class LabelReaderLike(Protocol):
    async def read(self, content: bytes, mime_type: str) -> LabelReading: ...


class InboundPersistenceError(RuntimeError):
    pass


class InboundWorkflow:
    def __init__(
        self,
        session: Session,
        storage: StorageLike,
        whatsapp: WhatsAppLike,
        reader: LabelReaderLike | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.whatsapp = whatsapp
        self.reader = reader

    async def ingest_message(
        self,
        *,
        wa_message_id: str,
        sender: str,
        message_type: str,
        media_id: str | None = None,
        mime_type: str | None = None,
        text: str | None = None,
        button_payload: str | None = None,
    ) -> bool:
        existing = self.session.scalar(
            select(MessageLog).where(MessageLog.wa_message_id == wa_message_id)
        )
        if existing is not None:
            return False

        normalized_sender = "+" + sender.lstrip("+")
        # ponytail: first open case wins when one caregiver looks after several patients;
        # route by case if that becomes common.
        patient_case = self.session.scalar(
            select(PatientCase).where(
                or_(
                    PatientCase.phone_e164 == normalized_sender,
                    PatientCase.caregiver_phone_e164 == normalized_sender,
                ),
                PatientCase.status.in_(("active", "photo_collection", "review_requested")),
            )
        )
        sender_role = (
            "caregiver"
            if patient_case and patient_case.phone_e164 != normalized_sender
            else "patient"
        )
        message = MessageLog(
            case_id=patient_case.id if patient_case else None,
            wa_message_id=wa_message_id,
            direction="inbound",
            message_type=message_type,
            processing_status="pending" if patient_case else "unmatched",
            normalized_payload={
                "mediaId": media_id,
                "mimeType": mime_type,
                "text": text,
                "buttonPayload": button_payload,
                "senderRole": sender_role,
            },
        )
        self.session.add(message)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return False
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise InboundPersistenceError("inbound_message_not_persisted") from exc

        if patient_case is None:
            logger.info(
                "WhatsApp inbound sender unmatched wa_message_id=%s sender_suffix=%s",
                wa_message_id,
                sender[-4:],
            )
            return True

        try:
            if message_type == "image" and media_id:
                await self._process_image(message, patient_case, media_id, mime_type, sender_role)
            elif message_type == "text" and (text or "").strip() == "تم":
                self._create_review_event(patient_case, "patient_marked_done", require_media=True)
                message.processing_status = "processed"
                self.session.commit()
            elif message_type == "button" and button_payload in {"taken", "not_yet"}:
                message.processing_status = "processed"
                self.session.commit()
            else:
                self._create_human_review_event(patient_case)
                await self.whatsapp.send_text(normalized_sender, SAFE_REPLY)
                message.processing_status = "processed"
                self.session.commit()
        except (
            WhatsAppApiError,
            WhatsAppMediaError,
            ObjectStorageError,
            ValueError,
            SQLAlchemyError,
        ) as exc:
            self.session.rollback()
            persisted = self.session.get(MessageLog, message.id)
            if persisted is not None:
                persisted.processing_status = "failed"
                self.session.commit()
            logger.warning(
                "WhatsApp inbound processing failed wa_message_id=%s error_type=%s",
                wa_message_id,
                type(exc).__name__,
            )
        return True

    def apply_delivery_status(self, wa_message_id: str, status: str | None) -> None:
        message = self.session.scalar(
            select(MessageLog).where(MessageLog.wa_message_id == wa_message_id)
        )
        if message is not None and message.direction == "outbound":
            message.delivery_status = status
            self.session.commit()

    async def retry_failed_message(self, wa_message_id: str) -> str:
        message = self.session.scalar(
            select(MessageLog).where(MessageLog.wa_message_id == wa_message_id)
        )
        if message is None:
            return "not_found"
        if message.processing_status != "failed" or message.case_id is None:
            return "not_retryable"
        patient_case = self.session.get(PatientCase, message.case_id)
        if patient_case is None:
            return "not_found"
        payload = message.normalized_payload
        message.processing_status = "pending"
        self.session.commit()
        try:
            if message.message_type == "image" and payload.get("mediaId"):
                await self._process_image(
                    message,
                    patient_case,
                    str(payload["mediaId"]),
                    payload.get("mimeType"),
                    payload.get("senderRole", "patient"),
                )
            else:
                message.processing_status = "failed"
                self.session.commit()
                return "not_retryable"
        except (
            WhatsAppApiError,
            WhatsAppMediaError,
            ObjectStorageError,
            ValueError,
            SQLAlchemyError,
        ):
            self.session.rollback()
            persisted = self.session.get(MessageLog, message.id)
            if persisted is not None:
                persisted.processing_status = "failed"
                self.session.commit()
            return "failed"
        return "processed"

    async def _process_image(
        self,
        message: MessageLog,
        patient_case: PatientCase,
        media_id: str,
        webhook_mime_type: str | None,
        sender_role: str = "patient",
    ) -> None:
        media = self.session.scalar(
            select(InboundMedia).where(InboundMedia.message_log_id == message.id)
        )
        if media is None:
            media = InboundMedia(
                case_id=patient_case.id,
                message_log_id=message.id,
                meta_media_id=media_id,
                mime_type=webhook_mime_type or "application/octet-stream",
                processing_status="downloading",
                sender_role=sender_role,
            )
            self.session.add(media)
            self.session.commit()

        downloaded = await self.whatsapp.download_image(media_id)
        stored = self.storage.store_case_media(
            case_id=patient_case.id,
            content=downloaded.content,
            content_type=downloaded.mime_type,
            source_media_id=media_id,
        )
        media.mime_type = downloaded.mime_type
        media.object_key = stored.key
        media.object_sha256 = stored.sha256
        media.processing_status = "stored"
        message.processing_status = "processed"
        patient_case.status = "photo_collection"
        self.session.commit()

        journey = self.session.get(CareJourney, patient_case.id)
        if journey is not None:
            await self._check_photo(media, patient_case, journey, downloaded)
            return

        count = (
            self.session.scalar(
                select(func.count(InboundMedia.id)).where(
                    InboundMedia.case_id == patient_case.id,
                    InboundMedia.processing_status == "stored",
                )
            )
            or 0
        )
        if count >= patient_case.expected_box_count:
            self._create_review_event(patient_case, "expected_photo_count_reached")

    def _create_review_event(
        self,
        patient_case: PatientCase,
        reason: str,
        *,
        require_media: bool = False,
    ) -> WorkflowEvent | None:
        key = f"{patient_case.id}:pharmacist_review_requested:v1"
        existing = self.session.scalar(
            select(WorkflowEvent).where(WorkflowEvent.idempotency_key == key)
        )
        if existing is not None:
            return existing
        media = self.session.scalars(
            select(InboundMedia)
            .where(
                InboundMedia.case_id == patient_case.id,
                InboundMedia.processing_status == "stored",
            )
            .order_by(InboundMedia.received_at, InboundMedia.id)
        ).all()
        if require_media and not media:
            return None
        plan = self.session.scalar(
            select(ApprovedPlan)
            .where(ApprovedPlan.case_id == patient_case.id)
            .order_by(ApprovedPlan.version.desc())
        )
        if plan is None:
            return None  # Care-journey cases are reviewed through their medicine photos.
        event_id = new_id()
        occurred_at = datetime.now(UTC)
        payload = PharmacistReviewRequested(
            event_id=event_id,
            event_type="pharmacist_review_requested",
            event_version=1,
            idempotency_key=key,
            occurred_at=occurred_at,
            case={
                "case_id": patient_case.id,
                "patient_alias": patient_case.patient_alias,
                "phone_e164_masked": _mask_phone(patient_case.phone_e164),
                "expected_box_count": patient_case.expected_box_count,
                "received_box_count": len(media),
            },
            approved_plan={
                "plan_id": plan.id,
                "version": plan.version,
                "source_hash": plan.source_hash,
            },
            medicine_photos=[
                {"media_id": item.id, "object_key": item.object_key or ""} for item in media
            ],
            review_reason=reason,
        )
        event = WorkflowEvent(
            event_id=event_id,
            case_id=patient_case.id,
            event_type="pharmacist_review_requested",
            event_version=1,
            payload=payload.model_dump(mode="json", by_alias=True),
            idempotency_key=key,
        )
        patient_case.status = "review_requested"
        self.session.add(event)
        self.session.commit()
        return event

    async def _check_photo(self, media, patient_case, journey, downloaded) -> None:
        """Link the photo to the medicine Hawlak asked for (or, when the box was sent out of
        order, to the one other waiting medicine its label matches), alert a person on a
        mismatch, then ask for the next box with a fixed reply."""
        dispensed = [m for m in journey.medications if m["dispensed"]]
        earlier = [p for p in self._case_photos(patient_case.id) if p.id != media.id]
        accepted = {p.medication_id for p in earlier if p.check_status not in (None, "unreadable")}
        expected = next((m for m in dispensed if m["medicationId"] not in accepted), None)
        language = journey.language_code
        if expected is None:
            # Every requested box already arrived: keep the photo for a person, skip the read.
            media.check_status = "extra"
            self.session.commit()
            await self._reply(patient_case, media, reply(language, "received_extra"))
            return

        reading = await self._read_once(earlier, media, downloaded)
        status = compare_reading(reading, expected)
        if status == "different_medicine":
            # Sent out of order: code (not the model) finds the one other approved medicine
            # still waiting that this label matches. None or several: keep the requested slot.
            waiting = [
                m
                for m in dispensed
                if m["medicationId"] not in accepted
                and m is not expected
                and compare_reading(reading, m) == "matched"
            ]
            if len(waiting) == 1:
                expected, status = waiting[0], "matched"
        media.medication_id = expected["medicationId"]
        media.label_reading = reading.to_json() if reading else None
        media.check_status = status
        if status in MISMATCH:
            summary = (
                f"Medicine photo does not match the requested medicine: {expected['displayName']}"
            )
            self._add_alert(patient_case.id, "medicine_photo_mismatch", "high", summary, media.id)
        if status == "unreadable":
            self.session.commit()
            await self._reply(
                patient_case, media, reply(language, "retake", name=expected["displayName"])
            )
            return

        accepted.add(expected["medicationId"])
        following = next((m for m in dispensed if m["medicationId"] not in accepted), None)
        if following is None:
            text = reply(language, "complete")
            self._add_alert(
                patient_case.id,
                "medicine_photos_ready",
                "low",
                "Medicine photos received for every dispensed medicine",
                "ready",
            )
        else:
            text = reply(
                language,
                "next",
                n=dispensed.index(following) + 1,
                total=len(dispensed),
                name=following["displayName"],
            )
        self.session.commit()
        await self._reply(patient_case, media, text)

    async def _read_once(self, earlier, media, downloaded) -> LabelReading | None:
        """Reuse the reading of an identical photo; otherwise read the label once."""
        same = next(
            (p for p in earlier if p.object_sha256 == media.object_sha256 and p.label_reading),
            None,
        )
        if same is not None:
            return LabelReading(**same.label_reading)
        if self.reader is None:
            return None
        try:
            return await self.reader.read(downloaded.content, downloaded.mime_type)
        except Exception as exc:  # noqa: BLE001 - a failed read leaves the photo for a person
            logger.warning("Medicine label read failed error_type=%s", type(exc).__name__)
            return None

    def _case_photos(self, case_id: str) -> list[InboundMedia]:
        return list(
            self.session.scalars(
                select(InboundMedia)
                .where(InboundMedia.case_id == case_id, InboundMedia.processing_status == "stored")
                .order_by(InboundMedia.received_at, InboundMedia.id)
            )
        )

    async def _reply(self, patient_case, media, text: str) -> None:
        recipient = (
            patient_case.caregiver_phone_e164
            if media.sender_role == "caregiver" and patient_case.caregiver_phone_e164
            else patient_case.phone_e164
        )
        await self.whatsapp.send_text(recipient, text)

    def _add_alert(self, case_id: str, kind: str, severity: str, summary: str, ref: str) -> None:
        key = f"{case_id}:{kind}:{ref}"
        if self.session.scalar(select(Alert).where(Alert.idempotency_key == key)) is None:
            self.session.add(
                Alert(
                    case_id=case_id,
                    type=kind,
                    severity=severity,
                    summary=summary,
                    idempotency_key=key,
                )
            )

    def _create_human_review_event(self, patient_case: PatientCase) -> None:
        key = f"{patient_case.id}:human_review_requested:v1"
        if self.session.scalar(select(WorkflowEvent).where(WorkflowEvent.idempotency_key == key)):
            return
        self.session.add(
            WorkflowEvent(
                event_id=new_id(),
                case_id=patient_case.id,
                event_type="human_review_requested",
                event_version=1,
                payload={"caseId": patient_case.id, "reason": "unsupported_input"},
                idempotency_key=key,
            )
        )
        self.session.commit()


def _mask_phone(phone: str) -> str:
    if len(phone) <= 8:
        return "*" * len(phone)
    return phone[:5] + "*" * (len(phone) - 8) + phone[-3:]
