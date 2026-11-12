import json
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, CareJourney, DeliveryRun, PatientCase, WorkflowEvent, utc_now
from app.schemas.care_journey import (
    CareJourneyContent,
    CareJourneyCreate,
)


class JourneyNotFound(RuntimeError):
    pass


class JourneyConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IntakeResult:
    journey: CareJourney
    created: bool


class CareJourneyService:
    """Own the insurer-reviewed journey and its executable delivery queue."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def intake(self, body: CareJourneyCreate) -> IntakeResult:
        existing = self.session.get(CareJourney, body.case_id)
        payload = self._content(body)
        if existing is not None:
            patient = self.session.get(PatientCase, body.case_id)
            if patient is None or not self._same_intake(patient, existing, body, payload):
                raise JourneyConflict("case_conflict")
            return IntakeResult(existing, False)

        patient = PatientCase(
            id=body.case_id,
            patient_alias=body.patient_name,
            phone_e164=body.phone_e164,
            dialect_code=body.dialect_code,
            expected_box_count=max(1, len(body.medications or [])),
            status="active",
        )
        journey = CareJourney(
            case_id=body.case_id,
            preferred_form_of_address=body.preferred_form_of_address,
            language_code=body.language_code,
            source_document=body.source_document.model_dump(mode="json", by_alias=True),
            **payload,
        )
        self.session.add(patient)
        self.session.flush()
        self.session.add(journey)
        self.session.commit()
        return IntakeResult(journey, True)

    def list_cases(self) -> list[dict]:
        rows = self.session.execute(
            select(CareJourney, PatientCase)
            .join(PatientCase, PatientCase.id == CareJourney.case_id)
            .order_by(CareJourney.updated_at.desc(), CareJourney.case_id)
        ).all()
        counts = dict(
            self.session.execute(
                select(Alert.case_id, func.count(Alert.id))
                .where(Alert.status == "open")
                .group_by(Alert.case_id)
            ).all()
        )
        return [
            {
                "caseId": journey.case_id,
                "patientName": patient.patient_alias,
                "languageCode": journey.language_code,
                "reviewStatus": journey.review_status,
                "alertCount": counts.get(journey.case_id, 0),
            }
            for journey, patient in rows
        ]

    def detail(self, case_id: str) -> dict:
        journey, patient = self._get(case_id)
        runs = self.session.scalars(
            select(DeliveryRun)
            .where(DeliveryRun.case_id == case_id)
            .order_by(DeliveryRun.created_at, DeliveryRun.id)
        ).all()
        return {
            "caseId": case_id,
            "patientName": patient.patient_alias,
            "preferredFormOfAddress": journey.preferred_form_of_address,
            "languageCode": journey.language_code,
            "dialectCode": patient.dialect_code,
            "sourceDocument": journey.source_document,
            "dischargeVoiceNote": journey.discharge_voice_note,
            "medications": journey.medications,
            "callPlan": journey.call_plan,
            "reviewStatus": journey.review_status,
            "approvedBy": journey.approved_by,
            "approvedAt": journey.approved_at,
            "deliveryRuns": [self.run_view(run) for run in runs],
        }

    def replace_content(self, case_id: str, body: CareJourneyContent) -> CareJourney:
        journey, _ = self._get(case_id)
        if journey.review_status == "approved":
            raise JourneyConflict("approved_content_is_immutable")
        content = self._content(body)
        journey.discharge_voice_note = content["discharge_voice_note"]
        journey.medications = content["medications"]
        journey.call_plan = content["call_plan"]
        self.session.commit()
        return journey

    def approve(self, case_id: str, approved_by: str, idempotency_key: str) -> list[DeliveryRun]:
        journey, _ = self._get(case_id)
        if journey.review_status == "approved":
            if journey.approval_idempotency_key != idempotency_key:
                raise JourneyConflict("already_approved")
            return self._runs(case_id)

        if (
            not journey.medications
            or not journey.discharge_voice_note.get("script")
            or not journey.call_plan.get("openingScript")
        ):
            raise JourneyConflict("content_requires_review")

        for medication in journey.medications:
            if not medication["dispensed"]:
                self._create_access_alert(case_id, medication)
                continue
            if medication["reminderEnabled"]:
                image = medication.get("image")
                if not image or image.get("reviewStatus") != "approved":
                    raise JourneyConflict("medication_image_requires_review")

        approved_at = utc_now()
        journey.review_status = "approved"
        journey.approved_by = approved_by
        journey.approved_at = approved_at
        journey.approval_idempotency_key = idempotency_key
        runs: list[DeliveryRun] = []
        if journey.discharge_voice_note["enabled"]:
            runs.append(
                self._run(case_id, "discharge_voice_note", "dischargeVoiceNote", approved_at)
            )
        for medication in journey.medications:
            if medication["dispensed"] and medication["reminderEnabled"]:
                runs.append(
                    self._run(
                        case_id,
                        "medication_reminder",
                        f"medications:{medication['medicationId']}",
                        approved_at,
                    )
                )
        if journey.call_plan["enabled"]:
            scheduled_at = approved_at + timedelta(
                hours=int(journey.call_plan["scheduledAfterHours"])
            )
            runs.append(self._run(case_id, "follow_up_call", "callPlan", scheduled_at))
        self.session.commit()
        return runs

    def call_plan(self, run_id: str) -> dict:
        run = self.session.get(DeliveryRun, run_id)
        if run is None:
            run = self.session.scalar(
                select(DeliveryRun).where(
                    DeliveryRun.case_id == run_id,
                    DeliveryRun.kind == "follow_up_call",
                )
            )
        if run is None or run.kind != "follow_up_call":
            journey = self.session.get(CareJourney, run_id)
            if journey is not None and journey.review_status != "approved":
                raise JourneyConflict("call_plan_not_approved")
            raise JourneyNotFound(run_id)
        journey, patient = self._get(run.case_id)
        if journey.review_status != "approved" or journey.approved_at is None:
            raise JourneyConflict("call_plan_not_approved")
        plan = journey.call_plan
        approval_checksum = sha256(
            json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "id": run.id,
            "caseId": journey.case_id,
            "version": 1,
            "approvedAt": journey.approved_at,
            "phoneE164": patient.phone_e164,
            "participantLabel": journey.preferred_form_of_address or patient.patient_alias,
            "language": journey.language_code,
            "dialectCode": patient.dialect_code,
            "scheduledAt": run.scheduled_at,
            "approvalStatus": journey.review_status,
            "approvalChecksum": approval_checksum,
            "openingScript": plan["openingScript"],
            "questions": plan["questions"],
            "completionScript": plan["completionScript"],
            "transferScript": plan["transferScript"],
            "transferTarget": plan["transferTarget"],
            "responderPhoneE164": plan["responderPhoneE164"],
        }

    def alerts(self) -> list[dict]:
        alerts = self.session.scalars(
            select(Alert).order_by(Alert.status, Alert.created_at.desc(), Alert.id)
        ).all()
        return [
            {
                "id": item.id,
                "caseId": item.case_id,
                "type": item.type,
                "severity": item.severity,
                "status": item.status,
                "summary": item.summary,
                "createdAt": item.created_at,
            }
            for item in alerts
        ]

    def pending_runs(self, kind: str | None = None) -> list[DeliveryRun]:
        query = select(DeliveryRun).where(DeliveryRun.status == "pending")
        if kind is not None:
            query = query.where(DeliveryRun.kind == kind)
        return list(
            self.session.scalars(query.order_by(DeliveryRun.scheduled_at, DeliveryRun.id)).all()
        )

    def claim_run(self, run_id: str) -> DeliveryRun:
        run = self.session.get(DeliveryRun, run_id)
        if run is None:
            raise JourneyNotFound(run_id)
        if run.status == "pending":
            run.status = "claimed"
            self.session.commit()
        elif run.status != "claimed":
            raise JourneyConflict("delivery_run_not_claimable")
        return run

    def update_run(self, run_id: str, status: str, provider_ref: str | None) -> DeliveryRun:
        run = self.session.get(DeliveryRun, run_id)
        if run is None:
            raise JourneyNotFound(run_id)
        if run.status == status and run.provider_ref == provider_ref:
            return run
        if run.status != "claimed":
            raise JourneyConflict("delivery_run_not_claimed")
        run.status = status
        run.provider_ref = provider_ref
        self.session.commit()
        return run

    def record_call_outcome(
        self,
        run_id: str,
        idempotency_key: str,
        status: str,
        provider_ref: str | None,
        escalation: dict | None,
    ) -> DeliveryRun:
        run = self.session.get(DeliveryRun, run_id)
        if run is None:
            raise JourneyNotFound(run_id)
        if run.kind != "follow_up_call":
            raise JourneyConflict("delivery_run_is_not_call")

        event_payload = {
            "runId": run_id,
            "status": status,
            "providerRef": provider_ref,
            "escalation": escalation,
        }
        event_for_key = self.session.scalar(
            select(WorkflowEvent).where(WorkflowEvent.idempotency_key == idempotency_key)
        )
        if event_for_key is not None:
            if (
                event_for_key.event_type == "call_outcome"
                and event_for_key.payload == event_payload
            ):
                return run
            raise JourneyConflict("idempotency_key_conflict")

        prior_outcome = next(
            (
                event
                for event in self.session.scalars(
                    select(WorkflowEvent).where(
                        WorkflowEvent.case_id == run.case_id,
                        WorkflowEvent.event_type == "call_outcome",
                    )
                )
                if event.payload.get("runId") == run_id
            ),
            None,
        )
        if prior_outcome is not None:
            raise JourneyConflict("call_outcome_already_recorded")

        if status in {"transferred", "failed"}:
            journey = self.session.get(CareJourney, run.case_id)
            approved_question_ids = {
                question["id"]
                for question in (journey.call_plan.get("questions", []) if journey else [])
            }
            question_id = escalation["questionId"] if escalation else ""
            if question_id not in approved_question_ids:
                raise JourneyConflict("call_question_not_approved")

        if run.status == status:
            return run
        if run.status != "sent":
            raise JourneyConflict("call_run_not_sent")

        if status in {"transferred", "failed"}:
            answer_kind = escalation["answerKind"]
            alert_key = f"{run.id}:call_escalation"
            alert = self.session.scalar(select(Alert).where(Alert.idempotency_key == alert_key))
            if alert is None:
                self.session.add(
                    Alert(
                        case_id=run.case_id,
                        type="call_escalation",
                        severity="high",
                        summary=(
                            f"Call escalation: {answer_kind} at approved question {question_id}"
                        ),
                        idempotency_key=alert_key,
                    )
                )

        run.status = status
        if provider_ref is not None:
            run.provider_ref = provider_ref
        self.session.add(
            WorkflowEvent(
                case_id=run.case_id,
                event_type="call_outcome",
                event_version=1,
                payload=event_payload,
                idempotency_key=idempotency_key,
            )
        )
        self.session.commit()
        return run

    def caregiver(self, case_id: str) -> dict:
        journey, patient = self._get(case_id)
        runs = self._runs(case_id)
        reminder_ids = {
            run.content_ref.split(":", 1)[1] for run in runs if run.kind == "medication_reminder"
        }
        return {
            "caseId": case_id,
            "patientName": patient.patient_alias,
            "journeyStatus": journey.review_status,
            "medications": [
                {
                    "medicationId": medication["medicationId"],
                    "displayName": medication["displayName"],
                    "status": (
                        "scheduled"
                        if medication["medicationId"] in reminder_ids
                        else "needs_support"
                    ),
                }
                for medication in journey.medications
            ],
            "openAlertCount": self.session.scalar(
                select(func.count(Alert.id)).where(Alert.case_id == case_id, Alert.status == "open")
            )
            or 0,
            "nextCallAt": min(
                (
                    run.scheduled_at
                    for run in runs
                    if run.kind == "follow_up_call" and run.status in {"pending", "claimed", "sent"}
                ),
                default=None,
            ),
        }

    def _get(self, case_id: str) -> tuple[CareJourney, PatientCase]:
        journey = self.session.get(CareJourney, case_id)
        patient = self.session.get(PatientCase, case_id)
        if journey is None or patient is None:
            raise JourneyNotFound(case_id)
        return journey, patient

    def _runs(self, case_id: str) -> list[DeliveryRun]:
        return list(
            self.session.scalars(
                select(DeliveryRun)
                .where(DeliveryRun.case_id == case_id)
                .order_by(DeliveryRun.created_at, DeliveryRun.id)
            ).all()
        )

    def _run(self, case_id: str, kind: str, content_ref: str, scheduled_at) -> DeliveryRun:
        run = DeliveryRun(
            case_id=case_id,
            kind=kind,
            status="pending",
            idempotency_key=f"{case_id}:{kind}:{content_ref}:v1",
            content_ref=content_ref,
            scheduled_at=scheduled_at,
        )
        self.session.add(run)
        return run

    def _create_access_alert(self, case_id: str, medication: dict) -> None:
        key = f"{case_id}:medication_access:{medication['medicationId']}"
        existing = self.session.scalar(select(Alert).where(Alert.idempotency_key == key))
        if existing is None:
            self.session.add(
                Alert(
                    case_id=case_id,
                    type="medication_access",
                    severity="high",
                    summary=f"Medication not dispensed: {medication['displayName']}",
                    idempotency_key=key,
                )
            )

    @staticmethod
    def run_view(run: DeliveryRun) -> dict:
        return {
            "id": run.id,
            "kind": run.kind,
            "status": run.status,
            "scheduledAt": run.scheduled_at,
            "providerRef": run.provider_ref,
        }

    @staticmethod
    def _content(body) -> dict:
        discharge_voice_note = (
            body.discharge_voice_note.model_dump(mode="json", by_alias=True)
            if body.discharge_voice_note is not None
            else {"enabled": False, "script": ""}
        )
        medications = body.medications or []
        call_plan = (
            body.call_plan.model_dump(mode="json", by_alias=True)
            if body.call_plan is not None
            else {
                "enabled": False,
                "scheduledAfterHours": 24,
                "openingScript": "",
                "questions": [],
                "completionScript": "",
                "transferScript": "",
                "transferTarget": "",
                "responderPhoneE164": "",
            }
        )
        return {
            "discharge_voice_note": discharge_voice_note,
            "medications": [item.model_dump(mode="json", by_alias=True) for item in medications],
            "call_plan": call_plan,
        }

    @staticmethod
    def _same_intake(
        patient: PatientCase, journey: CareJourney, body: CareJourneyCreate, payload: dict
    ) -> bool:
        return (
            patient.patient_alias == body.patient_name
            and patient.phone_e164 == body.phone_e164
            and patient.dialect_code == body.dialect_code
            and journey.preferred_form_of_address == body.preferred_form_of_address
            and journey.language_code == body.language_code
            and journey.source_document
            == body.source_document.model_dump(mode="json", by_alias=True)
            and journey.discharge_voice_note == payload["discharge_voice_note"]
            and journey.medications == payload["medications"]
            and journey.call_plan == payload["call_plan"]
        )
