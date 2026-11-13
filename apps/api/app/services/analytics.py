"""Programme analytics for the care team.

Counts, rates and times only: no name, phone number or case reference leaves this module.
The funnel and the breakdowns cover cases registered in the chosen period; the "now" block
covers everything still waiting, whatever its age.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, CareJourney, DeliveryRun, InboundMedia, PatientCase, utc_now
from app.services.dose_facts import RIYADH
from app.services.medicine_photos import MISMATCH

RUN_KINDS = ("discharge_voice_note", "photo_request", "medication_reminder", "follow_up_call")
DELIVERED = {"sent", "completed", "transferred"}
SCHEDULED = {"pending", "claimed"}
ALERT_TYPES = (
    "call_escalation",
    "medication_access",
    "medicine_photo_mismatch",
    "medicine_photos_ready",
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _hours(start: datetime, end: datetime) -> float:
    return (_aware(end) - _aware(start)).total_seconds() / 3600


def _median(values: list[float]) -> float | None:
    return round(median(values), 1) if values else None


def _pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def _oldest(starts: list[datetime], now: datetime) -> float | None:
    return round(max(_hours(start, now) for start in starts), 1) if starts else None


def case_stage(journey: CareJourney, runs: list[DeliveryRun], open_high_alerts: int) -> str:
    """Where a case stands for the care team: needs_review, needs_attention, active, completed."""
    if journey.review_status != "approved":
        return "needs_review"
    if open_high_alerts:
        return "needs_attention"
    return "active" if any(run.status in SCHEDULED for run in runs) else "completed"


def programme_analytics(session: Session, days: int, now: datetime | None = None) -> dict:
    now = now or utc_now()
    since = now - timedelta(days=days)
    # ponytail: loads every row and aggregates in Python; move to SQL GROUP BY when the
    # programme holds more than a few thousand cases.
    journeys = session.execute(
        select(CareJourney, PatientCase).join(PatientCase, PatientCase.id == CareJourney.case_id)
    ).all()
    runs: dict[str, list[DeliveryRun]] = defaultdict(list)
    for run in session.scalars(select(DeliveryRun)):
        runs[run.case_id].append(run)
    alerts = list(session.scalars(select(Alert)))
    photos: dict[str, list[InboundMedia]] = defaultdict(list)
    for photo in session.scalars(
        select(InboundMedia)
        .where(InboundMedia.processing_status == "stored")
        .order_by(InboundMedia.received_at, InboundMedia.id)
    ):
        photos[photo.case_id].append(photo)

    open_alerts = [a for a in alerts if a.status == "open"]
    open_high = Counter(a.case_id for a in open_alerts if a.severity == "high")
    drafts = [j for j, _ in journeys if j.review_status != "approved"]
    stages = Counter(case_stage(j, runs[j.case_id], open_high[j.case_id]) for j, _ in journeys)
    waiting_photos = [
        p
        for j, _ in journeys
        for p in photos[j.case_id]
        if p.review_status is None and p.check_status != "unreadable"
    ]

    cohort = [(j, p) for j, p in journeys if _aware(j.created_at) >= since]
    ids = {j.case_id for j, _ in cohort}
    approved = [j for j, _ in cohort if j.review_status == "approved" and j.approved_at]
    cohort_runs = [run for case_id in ids for run in runs[case_id]]
    cohort_photos = [photo for case_id in ids for photo in photos[case_id]]
    cohort_alerts = [a for a in alerts if a.case_id in ids]
    medications = [m for j, _ in cohort for m in j.medications]

    def with_photo(journey: CareJourney, medication: dict) -> bool:
        mine = [p for p in photos[journey.case_id] if p.medication_id == medication["medicationId"]]
        return bool(mine) and mine[-1].check_status != "unreadable"

    boxes = [(j, m) for j in approved for m in j.medications if m["dispensed"]]
    boxes_by_case = Counter(j.case_id for j, _ in boxes)
    photographed = Counter(j.case_id for j, m in boxes if with_photo(j, m))
    drafted = [j for j, _ in cohort if j.generated_draft]
    approved_drafted = [j for j in approved if j.generated_draft]
    to_approval = [_hours(j.created_at, j.approved_at) for j in approved]
    photo_status = Counter(p.check_status or "not_checked" for p in cohort_photos)
    read = sum(photo_status[key] for key in ("matched", *MISMATCH))
    calls = Counter(run.status for run in cohort_runs if run.kind == "follow_up_call")
    answered = calls["completed"] + calls["transferred"]

    def delivery(kind: str) -> dict:
        mine = [run for run in cohort_runs if run.kind == kind]
        delivered = sum(run.status in DELIVERED for run in mine)
        failed = sum(run.status == "failed" for run in mine)
        return {
            "kind": kind,
            "scheduled": sum(run.status in SCHEDULED for run in mine),
            "delivered": delivered,
            "failed": failed,
            "simulated": sum((run.provider_ref or "").startswith("mock:") for run in mine),
            "successPct": _pct(delivered, delivered + failed),
        }

    def alert_row(kind: str) -> dict:
        mine = [a for a in cohort_alerts if a.type == kind]
        resolved = [a for a in mine if a.status == "resolved" and a.resolved_at]
        return {
            "type": kind,
            "severity": mine[0].severity if mine else None,
            "open": sum(a.status == "open" for a in mine),
            "resolved": len(resolved),
            "medianHoursToResolve": _median(
                [_hours(a.created_at, a.resolved_at) for a in resolved]
            ),
        }

    def day(value: datetime) -> str:
        return _aware(value).astimezone(RIYADH).date().isoformat()

    registered_on = Counter(day(j.created_at) for j, _ in cohort)
    approved_on = Counter(
        day(j.approved_at) for j, _ in journeys if j.approved_at and _aware(j.approved_at) >= since
    )
    today = now.astimezone(RIYADH).date()
    dates = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    kinds = [*ALERT_TYPES, *sorted({a.type for a in cohort_alerts} - set(ALERT_TYPES))]

    return {
        "periodDays": days,
        "generatedAt": now,
        "now": {
            "awaitingReview": len(drafts),
            "oldestWaitingHours": _oldest([j.created_at for j in drafts], now),
            "needsAttention": stages["needs_attention"],
            "activeJourneys": stages["active"],
            "completedJourneys": stages["completed"],
            "openAlerts": {
                "high": sum(a.severity == "high" for a in open_alerts),
                "low": sum(a.severity != "high" for a in open_alerts),
            },
            "oldestOpenAlertHours": _oldest([a.created_at for a in open_alerts], now),
            "photosAwaitingReview": len(waiting_photos),
        },
        "funnel": [
            {"stage": "registered", "count": len(cohort)},
            {
                "stage": "eligible",
                "count": sum((j.insurance or {}).get("status") == "eligible" for j, _ in cohort),
            },
            {"stage": "approved", "count": len(approved)},
            {
                "stage": "contacted",
                "count": sum(
                    any(run.status in DELIVERED for run in runs[j.case_id]) for j in approved
                ),
            },
            {
                "stage": "photos_received",
                "count": sum(
                    count > 0 and photographed[case_id] == count
                    for case_id, count in boxes_by_case.items()
                ),
            },
            {
                "stage": "call_completed",
                "count": sum(
                    any(
                        run.kind == "follow_up_call" and run.status in {"completed", "transferred"}
                        for run in runs[j.case_id]
                    )
                    for j in approved
                ),
            },
        ],
        "review": {
            "medianHoursToApproval": _median(to_approval),
            "approvedWithin24hPct": _pct(sum(hours <= 24 for hours in to_approval), len(approved)),
            # How often a person changed the drafted voice note before approving it.
            "draftEditedPct": _pct(
                sum(
                    j.discharge_voice_note.get("script", "").strip()
                    != (j.generated_draft.get("voiceScript") or "").strip()
                    for j in approved_drafted
                ),
                len(approved_drafted),
            ),
            "aiDraftPct": _pct(
                sum(
                    str(j.generated_draft.get("generator", "")).startswith("openai")
                    for j in drafted
                ),
                len(drafted),
            ),
            "aiDraftRejected": sum(
                "live_draft_rejected" in (j.generated_draft.get("notes") or []) for j in drafted
            ),
        },
        "delivery": [delivery(kind) for kind in RUN_KINDS],
        "calls": {
            "scheduled": calls["pending"] + calls["claimed"],
            # Placed, with no outcome reported back yet.
            "awaitingOutcome": calls["sent"],
            "completed": calls["completed"],
            "transferred": calls["transferred"],
            "failed": calls["failed"],
            "escalationPct": _pct(calls["transferred"], answered),
        },
        "photos": {
            "total": len(cohort_photos),
            "byStatus": {
                key: photo_status[key]
                for key in (
                    "matched",
                    "strength_mismatch",
                    "different_medicine",
                    "unreadable",
                    "not_checked",
                    "extra",
                )
            },
            "bySender": dict(Counter(p.sender_role for p in cohort_photos)),
            "boxesExpected": len(boxes),
            "boxesWithPhoto": sum(photographed.values()),
            "firstReadMatchPct": _pct(photo_status["matched"], read),
            "awaitingReview": sum(p in waiting_photos for p in cohort_photos),
            "medianHoursToReview": _median(
                [_hours(p.received_at, p.reviewed_at) for p in cohort_photos if p.reviewed_at]
            ),
        },
        "alerts": [alert_row(kind) for kind in kinds],
        "medications": {
            "total": len(medications),
            "notDispensed": sum(not m["dispensed"] for m in medications),
            "remindersEnabled": sum(m["dispensed"] and m["reminderEnabled"] for m in medications),
            "withReminderTimes": sum(bool(m.get("reminderTimes")) for m in medications),
            "withConfirmedStrength": sum(bool(m.get("unitStrength")) for m in medications),
        },
        "languages": dict(Counter(j.language_code for j, _ in cohort)),
        "dialects": dict(Counter(p.dialect_code for j, p in cohort if j.language_code == "ar")),
        "daily": [
            {"date": date, "registered": registered_on[date], "approved": approved_on[date]}
            for date in dates
        ],
    }
