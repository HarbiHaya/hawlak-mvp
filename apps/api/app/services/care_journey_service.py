import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, CareJourney, DeliveryRun, PatientCase, WorkflowEvent, utc_now
from app.schemas.care_journey import (
    CareJourneyContent,
    CareJourneyCreate,
)
from app.services.discharge_parser import DischargeExtraction, draft_medications
from app.services.insurer_systems import MockInsurerSystems

REPEAT_DAYS = {"none": 0, "daily": 1, "every_2_days": 2, "weekly": 7}


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

    def __init__(self, session: Session, insurer: MockInsurerSystems | None = None) -> None:
        self.session = session
        self.insurer = insurer or MockInsurerSystems()

    def intake(
        self,
        body: CareJourneyCreate,
        content: CareJourneyContent | None = None,
        generated: dict | None = None,
    ) -> IntakeResult:
        existing = self.session.get(CareJourney, body.case_id)
        payload = self._content(content or body)
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
            generated_draft=generated,
            **payload,
        )
        if body.member_id:
            # Replays compare supplied content, so only prefill content Hawlak drafted itself.
            hospital_only = body.medications is None and body.discharge_voice_note is None
            self._record_eligibility(journey, body.member_id, prefill=hospital_only)
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
            "insurance": journey.insurance,
            "generatedDraft": journey.generated_draft,
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

    def check_eligibility(self, case_id: str, member_id: str) -> CareJourney:
        journey, _ = self._get(case_id)
        if journey.review_status == "approved":
            raise JourneyConflict("approved_content_is_immutable")
        self._record_eligibility(journey, member_id)
        self.session.commit()
        return journey

    def regenerate(self, case_id: str, extraction: DischargeExtraction, drafter) -> CareJourney:
        journey, patient = self._get(case_id)
        if journey.review_status == "approved":
            raise JourneyConflict("approved_content_is_immutable")
        content, generated = drafted_content(
            extraction,
            drafter,
            medications=journey.medications or draft_medications(extraction),
            call_plan=journey.call_plan,
            label=journey.preferred_form_of_address or patient.patient_alias,
            language=journey.language_code,
            dialect=patient.dialect_code,
        )
        journey.discharge_voice_note = content["dischargeVoiceNote"]
        journey.medications = content["medications"]
        journey.call_plan = content["callPlan"]
        journey.generated_draft = generated
        self.session.commit()
        return journey

    def approve(self, case_id: str, approved_by: str, idempotency_key: str) -> list[DeliveryRun]:
        journey, _ = self._get(case_id)
        if journey.review_status == "approved":
            if journey.approval_idempotency_key != idempotency_key:
                raise JourneyConflict("already_approved")
            return self._runs(case_id)

        insurance = journey.insurance or {}
        if not insurance.get("status"):
            raise JourneyConflict("eligibility_not_verified")
        if insurance["status"] != "eligible":
            raise JourneyConflict("member_not_eligible")
        incomplete = self._first_incomplete_section(journey)
        if incomplete:
            raise JourneyConflict(incomplete)

        for medication in journey.medications:
            if not medication["dispensed"]:
                self._create_access_alert(case_id, medication)

        approved_at = utc_now()
        journey.review_status = "approved"
        journey.approved_by = approved_by
        journey.approved_at = approved_at
        journey.approval_idempotency_key = idempotency_key
        journey.insurance = {
            **insurance,
            "enrollmentReference": self.insurer.enroll(case_id, insurance),
            "enrolledAt": approved_at.isoformat(),
        }
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
            for index, scheduled_at in enumerate(self._call_times(journey.call_plan, approved_at)):
                ref = "callPlan" if index == 0 else f"callPlan:{index + 1}"
                runs.append(self._run(case_id, "follow_up_call", ref, scheduled_at))
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
        names = dict(
            self.session.execute(
                select(PatientCase.id, PatientCase.patient_alias).where(
                    PatientCase.id.in_({item.case_id for item in alerts})
                )
            ).all()
        )
        return [
            {
                "id": item.id,
                "caseId": item.case_id,
                "patientName": names.get(item.case_id),
                "type": item.type,
                "severity": item.severity,
                "status": item.status,
                "summary": item.summary,
                "createdAt": item.created_at,
            }
            for item in alerts
        ]

    def resolve_alert(self, alert_id: str) -> Alert:
        alert = self.session.get(Alert, alert_id)
        if alert is None:
            raise JourneyNotFound(alert_id)
        if alert.status != "resolved":
            alert.status = "resolved"
            alert.resolved_at = utc_now()
            self.session.commit()
        return alert

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

    @staticmethod
    def _first_incomplete_section(journey: CareJourney) -> str | None:
        """Drafts may be partial; only complete, reviewed content can be approved."""
        voice, call = journey.discharge_voice_note, journey.call_plan
        if not journey.medications:
            return "medications_required"
        for medication in journey.medications:
            if not medication["displayName"].strip() or not medication["doseInstruction"].strip():
                return "medication_details_required"
            if medication["dispensed"] and medication["reminderEnabled"]:
                if not medication["reminderScript"].strip():
                    return "reminder_script_required"
                image = medication.get("image")
                if not image or image.get("reviewStatus") != "approved":
                    return "medication_image_requires_review"
        if voice.get("enabled") and not voice.get("script", "").strip():
            return "voice_script_required"
        if call.get("enabled"):
            texts = [call.get(k, "") for k in ("openingScript", "completionScript")]
            texts += [call.get(k, "") for k in ("transferScript", "transferTarget")]
            questions = call.get("questions") or []
            if (
                not all(text.strip() for text in texts)
                or not questions
                or not all(question["prompt"].strip() for question in questions)
                or not call.get("responderPhoneE164")
            ):
                return "call_plan_incomplete"
            if CareJourneyService._call_times(call, utc_now())[0] < utc_now():
                return "call_time_in_past"
        reminders = any(m["dispensed"] and m["reminderEnabled"] for m in journey.medications)
        if not (voice.get("enabled") or call.get("enabled") or reminders):
            return "no_channel_enabled"
        return None

    @staticmethod
    def _call_times(plan: dict, approved_at: datetime) -> list[datetime]:
        if plan.get("firstCallAt"):
            first = datetime.fromisoformat(plan["firstCallAt"])
            first = first if first.tzinfo else first.replace(tzinfo=UTC)
        else:
            first = approved_at + timedelta(hours=int(plan.get("scheduledAfterHours", 24)))
        step = REPEAT_DAYS.get(plan.get("repeat", "none"), 0)
        count = int(plan.get("occurrences", 1)) if step else 1
        return [first + timedelta(days=step * index) for index in range(count)]

    def _record_eligibility(self, journey: CareJourney, member_id: str, prefill=True) -> None:
        result = self.insurer.check_eligibility(member_id)
        journey.insurance = {**result, "checkedAt": utc_now().isoformat()}
        manager = result.get("caseManager")
        if prefill and manager and not journey.call_plan["responderPhoneE164"]:
            journey.call_plan = {**journey.call_plan, "responderPhoneE164": manager["phoneE164"]}

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
            else dict(DEFAULT_CALL_PLAN)
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
            and (journey.insurance or {}).get("memberId") == body.member_id
            and (
                body.medications is None
                and body.discharge_voice_note is None
                or (
                    journey.discharge_voice_note == payload["discharge_voice_note"]
                    and journey.medications == payload["medications"]
                    and journey.call_plan == payload["call_plan"]
                )
            )
        )


DEFAULT_CALL_PLAN = {
    "enabled": False,
    "scheduledAfterHours": 24,
    "firstCallAt": None,
    "repeat": "none",
    "occurrences": 1,
    "openingScript": "",
    "questions": [],
    "completionScript": "",
    "transferScript": "",
    "transferTarget": "",
    "responderPhoneE164": "",
}


def drafted_content(
    extraction: DischargeExtraction,
    drafter,
    *,
    medications: list[dict],
    call_plan: dict,
    label: str,
    language: str,
    dialect: str,
) -> tuple[dict, dict]:
    """Fill the reviewable content from a generated draft; return it with a snapshot."""
    draft = drafter.draft(extraction, medications, label, language, dialect)
    content = {
        "dischargeVoiceNote": {"enabled": True, "script": draft.voice_script[:6000]},
        "medications": [
            {**m, "reminderScript": draft.reminder_scripts.get(m["medicationId"], "")[:1000]}
            for m in medications
        ],
        "callPlan": {
            **call_plan,
            "enabled": bool(draft.call_questions),
            "openingScript": draft.call_opening[:2000],
            "questions": [{**q, "prompt": q["prompt"][:1000]} for q in draft.call_questions],
            "completionScript": draft.call_completion[:1000],
            "transferScript": draft.call_transfer[:1000],
            "transferTarget": call_plan.get("transferTarget") or "integrated_care",
        },
    }
    return content, {**draft.snapshot(), "generatedAt": utc_now().isoformat()}
