import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ApprovedPlan, InboundMedia, MessageLog, PatientCase, WorkflowEvent, new_id
from app.schemas.review_event import PharmacistReviewRequested
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


class InboundPersistenceError(RuntimeError):
    pass


class InboundWorkflow:
    def __init__(self, session: Session, storage: StorageLike, whatsapp: WhatsAppLike) -> None:
        self.session = session
        self.storage = storage
        self.whatsapp = whatsapp

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
        patient_case = self.session.scalar(
            select(PatientCase).where(
                PatientCase.phone_e164 == normalized_sender,
                PatientCase.status.in_(("active", "photo_collection", "review_requested")),
            )
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
                await self._process_image(message, patient_case, media_id, mime_type)
            elif message_type == "text" and (text or "").strip() == "تم":
                self._create_review_event(patient_case, "patient_marked_done", require_media=True)
                message.processing_status = "processed"
                self.session.commit()
            elif message_type == "button" and button_payload in {"taken", "not_yet"}:
                message.processing_status = "processed"
                self.session.commit()
            else:
                self._create_human_review_event(patient_case)
                await self.whatsapp.send_text(patient_case.phone_e164, SAFE_REPLY)
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
            raise ValueError("approved plan missing")
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
