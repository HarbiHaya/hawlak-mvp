from types import SimpleNamespace

from app.main import app
from app.models import Alert, CareJourney, DeliveryRun
from app.services.object_storage import get_object_storage


def intake_body() -> dict:
    return {
        "caseId": "case_poc_01",
        "patientName": "مريم خالد العتيبي",
        "preferredFormOfAddress": "أم نورة",
        "phoneE164": "+966500000000",
        "memberId": "SYN-4471203",
        "languageCode": "ar",
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {
            "objectKey": "synthetic/discharges/case_poc_01.pdf",
            "filename": "synthetic-discharge.pdf",
        },
        "dischargeVoiceNote": {
            "enabled": True,
            "script": "هذه تعليمات الخروج المعتمدة للحالة التجريبية.",
        },
        "medications": [
            {
                "medicationId": "SYN-MED-001",
                "displayName": "دواء تجريبي ألف",
                "doseInstruction": "قرص واحد صباحا",
                "dispensed": True,
                "image": {
                    "source": "catalog",
                    "objectKey": "synthetic/catalog/med-a.jpg",
                    "reviewStatus": "approved",
                },
                "reminderEnabled": True,
                "reminderScript": "هذا تذكير بجرعة دواء تجريبي ألف.",
            }
        ],
        "callPlan": {
            "enabled": True,
            "scheduledAfterHours": 24,
            "openingScript": "سأسألك الآن عن علامات الخطر المعتمدة.",
            "questions": [{"id": "red-flag", "prompt": "هل تشعر بألم جديد؟"}],
            "completionScript": "شكرا، انتهت المتابعة.",
            "transferScript": "سأحولك الآن إلى فريق الرعاية.",
            "transferTarget": "integrated_care",
            "responderPhoneE164": "+966511111111",
        },
    }


def test_hospital_uploads_pdf_then_creates_case_without_entering_clinical_content(
    client, internal_auth_headers
):
    seen = {}

    class Storage:
        def store_case_media(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(key="cases/case_poc_01/media/synthetic.pdf")

        def get_bytes(self, key):
            return seen["content"]

    app.dependency_overrides[get_object_storage] = Storage
    upload = client.post(
        "/internal/workspace/documents",
        content=b"%PDF-1.4 synthetic discharge",
        headers={
            **internal_auth_headers,
            "Content-Type": "application/pdf",
            "X-Case-Id": "case_poc_01",
            "X-Filename": "synthetic-discharge.pdf",
        },
    )
    minimal = intake_body()
    minimal["sourceDocument"] = upload.json()
    minimal.pop("dischargeVoiceNote")
    minimal.pop("medications")
    minimal.pop("callPlan")
    created = client.post("/internal/workspace/cases", json=minimal, headers=internal_auth_headers)

    assert upload.status_code == 201
    assert created.status_code == 201
    assert upload.json()["objectKey"].endswith("synthetic.pdf")
    assert seen["content"] == b"%PDF-1.4 synthetic discharge"
    assert (
        client.get("/internal/workspace/cases/case_poc_01", headers=internal_auth_headers).json()[
            "medications"
        ]
        == []
    )


def test_insurer_uploads_a_controlled_medication_image(client, internal_auth_headers):
    seen = {}

    class Storage:
        def store_case_media(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(key="cases/case_poc_01/media/medicine.jpg")

    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)
    app.dependency_overrides[get_object_storage] = Storage
    response = client.post(
        "/internal/workspace/cases/case_poc_01/medication-images",
        content=b"\xff\xd8\xffsynthetic-image",
        headers={
            **internal_auth_headers,
            "Content-Type": "image/jpeg",
            "X-Filename": "medicine.jpg",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "objectKey": "cases/case_poc_01/media/medicine.jpg",
        "filename": "medicine.jpg",
        "contentType": "image/jpeg",
    }
    assert seen["content"] == b"\xff\xd8\xffsynthetic-image"


def test_hospital_intake_is_replay_safe_and_visible_to_insurer(
    client, internal_auth_headers, db_session
):
    first = client.post(
        "/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers
    )
    second = client.post(
        "/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json() == {"caseId": "case_poc_01", "reviewStatus": "draft"}
    assert db_session.query(CareJourney).count() == 1

    listing = client.get("/internal/workspace/cases", headers=internal_auth_headers)
    assert listing.status_code == 200
    assert listing.json()["data"] == [
        {
            "caseId": "case_poc_01",
            "patientName": "مريم خالد العتيبي",
            "languageCode": "ar",
            "reviewStatus": "draft",
            "alertCount": 0,
        }
    ]


def test_insurer_can_edit_then_approve_exact_content_and_create_delivery_runs(
    client, internal_auth_headers, db_session
):
    body = intake_body()
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
    edited_script = "هذه النسخة التي راجعها فريق الرعاية المتكاملة."

    edit = client.patch(
        "/internal/workspace/cases/case_poc_01/content",
        json={
            "dischargeVoiceNote": {"enabled": True, "script": edited_script},
            "medications": body["medications"],
            "callPlan": body["callPlan"],
        },
        headers=internal_auth_headers,
    )
    approval = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-case-poc-01-v1"},
    )
    replay = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-case-poc-01-v1"},
    )

    assert edit.status_code == 200
    assert approval.status_code == 200
    assert approval.json() == replay.json()
    assert approval.json()["reviewStatus"] == "approved"
    assert [item["kind"] for item in approval.json()["deliveryRuns"]] == [
        "discharge_voice_note",
        "medication_reminder",
        "follow_up_call",
    ]
    assert db_session.query(DeliveryRun).count() == 3

    detail = client.get(
        "/internal/workspace/cases/case_poc_01", headers=internal_auth_headers
    ).json()
    assert detail["dischargeVoiceNote"]["script"] == edited_script
    assert detail["preferredFormOfAddress"] == "أم نورة"

    call_run = next(
        run for run in approval.json()["deliveryRuns"] if run["kind"] == "follow_up_call"
    )
    call_plan = client.get(f"/internal/call-plans/{call_run['id']}", headers=internal_auth_headers)
    assert call_plan.status_code == 200
    assert call_plan.json()["questions"] == body["callPlan"]["questions"]
    assert call_plan.json()["participantLabel"] == "أم نورة"


def test_unapproved_ocr_candidate_blocks_approval(client, internal_auth_headers):
    body = intake_body()
    body["medications"][0]["image"] = {
        "source": "patient_photo",
        "objectKey": "synthetic/inbound/unknown.jpg",
        "reviewStatus": "pending",
        "ocrCandidate": "دواء تجريبي ألف",
    }
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    response = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approval-blocked"},
    )

    assert response.status_code == 409
    assert response.json() == {"error": "medication_image_requires_review"}


def test_call_worker_can_fetch_by_case_only_after_approval(client, internal_auth_headers):
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)

    draft = client.get("/internal/call-plans/case_poc_01", headers=internal_auth_headers)
    assert draft.status_code == 409
    assert draft.json() == {"error": "call_plan_not_approved"}

    client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-call-plan"},
    )
    approved = client.get("/internal/call-plans/case_poc_01", headers=internal_auth_headers)

    assert approved.status_code == 200
    assert approved.json()["approvalStatus"] == "approved"
    assert len(approved.json()["approvalChecksum"]) == 64
    assert approved.json()["dialectCode"] == "ar-SA-najdi"


def test_worker_claims_and_completes_delivery_run_without_duplicate_dispatch(
    client, internal_auth_headers
):
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)
    approved = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-delivery"},
    ).json()
    run_id = approved["deliveryRuns"][0]["id"]

    claim = client.post(
        f"/internal/delivery-runs/{run_id}/claim",
        headers={**internal_auth_headers, "Idempotency-Key": "worker-claim-01"},
    )
    replay = client.post(
        f"/internal/delivery-runs/{run_id}/claim",
        headers={**internal_auth_headers, "Idempotency-Key": "worker-claim-01"},
    )
    completed = client.patch(
        f"/internal/delivery-runs/{run_id}",
        json={"status": "sent", "providerRef": "synthetic-provider-01"},
        headers=internal_auth_headers,
    )

    assert claim.json() == replay.json()
    assert claim.json()["status"] == "claimed"
    assert completed.json()["status"] == "sent"


def test_not_dispensed_medication_creates_access_alert_without_reminder(
    client, internal_auth_headers, db_session
):
    body = intake_body()
    body["medications"][0]["dispensed"] = False
    body["medications"][0]["reminderEnabled"] = False
    body["medications"][0]["image"] = None
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    response = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approval-access-alert"},
    )

    assert response.status_code == 200
    assert [item["kind"] for item in response.json()["deliveryRuns"]] == [
        "discharge_voice_note",
        "follow_up_call",
    ]
    assert db_session.query(Alert).count() == 1
    alerts = client.get("/internal/workspace/alerts", headers=internal_auth_headers).json()["data"]
    assert alerts[0]["type"] == "medication_access"
    assert alerts[0]["patientName"] == "مريم خالد العتيبي"

    url = f"/internal/workspace/alerts/{alerts[0]['id']}/resolve"
    resolved = client.post(url, headers=internal_auth_headers)
    replay = client.post(url, headers=internal_auth_headers)
    caregiver = client.get("/internal/caregiver/cases/case_poc_01", headers=internal_auth_headers)

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert replay.status_code == 200
    assert caregiver.json()["openAlertCount"] == 0


def test_caregiver_projection_excludes_phone_scripts_and_document(client, internal_auth_headers):
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)
    client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-caregiver"},
    )

    response = client.get("/internal/caregiver/cases/case_poc_01", headers=internal_auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["patientName"] == "مريم خالد العتيبي"
    assert payload["medications"] == [
        {
            "medicationId": "SYN-MED-001",
            "displayName": "دواء تجريبي ألف",
            "status": "scheduled",
        }
    ]
    serialized = str(payload)
    assert "+966" not in serialized
    assert "script" not in serialized.lower()
    assert "objectKey" not in serialized


def test_operator_dispatches_due_whatsapp_runs_without_duplicate_provider_calls(
    client, internal_auth_headers, db_session
):
    body = intake_body()
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
    client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-for-dispatch"},
    )

    first = client.post(
        "/internal/workspace/cases/case_poc_01/dispatch",
        headers={**internal_auth_headers, "Idempotency-Key": "dispatch-case-poc-01"},
    )
    replay = client.post(
        "/internal/workspace/cases/case_poc_01/dispatch",
        headers={**internal_auth_headers, "Idempotency-Key": "dispatch-case-poc-01"},
    )

    assert first.status_code == 200
    assert first.json() == replay.json()
    assert [item["kind"] for item in first.json()["data"]] == [
        "discharge_voice_note",
        "medication_reminder",
    ]
    assert all(item["status"] == "sent" for item in first.json()["data"])
    assert all(item["providerRef"].startswith("mock:") for item in first.json()["data"])
    call_run = db_session.query(DeliveryRun).filter_by(kind="follow_up_call").one()
    assert call_run.status == "pending"


def test_insurer_can_save_an_incomplete_draft_but_not_approve_it(client, internal_auth_headers):
    body = intake_body()
    for key in ("dischargeVoiceNote", "medications", "callPlan"):
        body.pop(key)
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
    draft = {
        "dischargeVoiceNote": {"enabled": True, "script": "نص أولي"},
        "medications": [
            {
                "medicationId": "SYN-MED-002",
                "displayName": "",
                "doseInstruction": "",
                "dispensed": True,
                "image": None,
                "reminderEnabled": False,
                "reminderScript": "",
            }
        ],
        "callPlan": {
            "enabled": True,
            "scheduledAfterHours": 24,
            "openingScript": "",
            "questions": [],
            "completionScript": "",
            "transferScript": "",
            "transferTarget": "",
            "responderPhoneE164": "",
        },
    }

    saved = client.patch(
        "/internal/workspace/cases/case_poc_01/content", json=draft, headers=internal_auth_headers
    )
    blocked = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "incomplete"},
    )

    assert saved.status_code == 200
    assert blocked.status_code == 409
    assert blocked.json() == {"error": "medication_details_required"}


def test_approval_names_the_first_incomplete_section(client, internal_auth_headers):
    cases = [
        (lambda b: b["dischargeVoiceNote"].update(script=""), "voice_script_required"),
        (lambda b: b["medications"][0].update(reminderScript=""), "reminder_script_required"),
        (lambda b: b["callPlan"].update(questions=[]), "call_plan_incomplete"),
        (lambda b: b["callPlan"].update(responderPhoneE164=""), "call_plan_incomplete"),
    ]
    for index, (mutate, error) in enumerate(cases):
        body = intake_body()
        body["caseId"] = f"case_incomplete_{index}"
        mutate(body)
        client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
        response = client.post(
            f"/internal/workspace/cases/{body['caseId']}/approve",
            json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
            headers={**internal_auth_headers, "Idempotency-Key": f"incomplete-{index}"},
        )
        assert response.json() == {"error": error}, error


def test_disabled_voice_note_and_call_need_no_scripts(client, internal_auth_headers):
    body = intake_body()
    body["dischargeVoiceNote"] = {"enabled": False, "script": ""}
    body["callPlan"].update(enabled=False, openingScript="", questions=[])
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    response = client.post(
        "/internal/workspace/cases/case_poc_01/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**internal_auth_headers, "Idempotency-Key": "reminder-only"},
    )

    assert response.status_code == 200
    assert [run["kind"] for run in response.json()["deliveryRuns"]] == ["medication_reminder"]


def test_insurer_can_view_only_files_that_belong_to_the_case(client, internal_auth_headers):
    reads = []

    class Storage:
        def get_bytes(self, key):
            reads.append(key)
            return b"%PDF-1.4 synthetic"

    app.dependency_overrides[get_object_storage] = Storage
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)
    url = "/internal/workspace/cases/case_poc_01/files"

    pdf = client.get(
        url, params={"key": "cases/case_poc_01/media/a.pdf"}, headers=internal_auth_headers
    )
    other = client.get(
        url, params={"key": "cases/case_other/media/a.pdf"}, headers=internal_auth_headers
    )
    escape = client.get(
        url, params={"key": "cases/case_poc_01/../case_other/a.pdf"}, headers=internal_auth_headers
    )

    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content == b"%PDF-1.4 synthetic"
    assert other.status_code == 404
    assert escape.status_code == 404
    assert reads == ["cases/case_poc_01/media/a.pdf"]


def pdf_storage(fixtures_dir, reads=None):
    pdf = (fixtures_dir / "approved-plan.abu-mohammed.pdf").read_bytes()

    class Storage:
        def get_bytes(self, key):
            if reads is not None:
                reads.append(key)
            return pdf

    return Storage


def pdf_intake_body(language="en") -> dict:
    body = intake_body()
    for key in ("dischargeVoiceNote", "medications", "callPlan"):
        body.pop(key)
    body["languageCode"] = language
    body["sourceDocument"] = {
        "objectKey": "cases/case_poc_01/media/discharge.pdf",
        "filename": "discharge.pdf",
    }
    return body


def test_intake_prefills_the_draft_from_the_discharge_pdf(
    client, internal_auth_headers, fixtures_dir
):
    app.dependency_overrides[get_object_storage] = pdf_storage(fixtures_dir)
    body = pdf_intake_body("en")

    created = client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
    replay = client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
    detail = client.get(
        "/internal/workspace/cases/case_poc_01", headers=internal_auth_headers
    ).json()

    assert created.status_code == 201
    assert replay.status_code == 200
    assert [m["displayName"] for m in detail["medications"]] == [
        "Fictional medicine A",
        "Fictional medicine B",
        "Fictional medicine C",
    ]
    assert detail["medications"][0]["reminderEnabled"] is False
    assert detail["medications"][0]["reminderScript"].startswith("Hawlak reminder:")
    assert detail["dischargeVoiceNote"]["script"].startswith("Hello أم نورة.")
    assert detail["callPlan"]["questions"][0]["id"] == "warning-1"
    assert detail["generatedDraft"]["generator"] == "template"
    assert detail["generatedDraft"]["voiceScript"] == detail["dischargeVoiceNote"]["script"]
    assert detail["reviewStatus"] == "draft"


def test_intake_never_reads_a_document_from_another_case(
    client, internal_auth_headers, fixtures_dir
):
    reads = []
    app.dependency_overrides[get_object_storage] = pdf_storage(fixtures_dir, reads)
    body = pdf_intake_body()
    body["sourceDocument"]["objectKey"] = "cases/case_other/media/discharge.pdf"

    created = client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    assert created.status_code == 201
    assert reads == []


def test_insurer_sees_what_was_read_from_the_pdf(client, internal_auth_headers, fixtures_dir):
    app.dependency_overrides[get_object_storage] = pdf_storage(fixtures_dir)
    client.post(
        "/internal/workspace/cases", json=pdf_intake_body("ar"), headers=internal_auth_headers
    )

    response = client.get(
        "/internal/workspace/cases/case_poc_01/extraction", headers=internal_auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "parsed"
    assert body["language"] == "en"
    assert body["medications"][0] == {
        "name": "Fictional medicine A",
        "instruction": "5 mg, 1 tablet, once daily (morning)",
    }
    assert body["stoppedMedications"] == ["Fictional medicine D"]
    assert body["sections"][2]["heading"] == "WARNING SIGNS - CALL 997 AT ONCE"
    assert "NEW MEDICINES" in body["text"]


def approve(client, headers, case_id: str, key: str):
    return client.post(
        f"/internal/workspace/cases/{case_id}/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**headers, "Idempotency-Key": key},
    )


def test_a_recurring_call_schedule_creates_one_run_per_call(client, internal_auth_headers):
    from datetime import UTC, datetime, timedelta

    first = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    body = intake_body()
    body["callPlan"].update(firstCallAt=first.isoformat(), repeat="every_2_days", occurrences=3)
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    response = approve(client, internal_auth_headers, "case_poc_01", "recurring-calls")

    calls = [r for r in response.json()["deliveryRuns"] if r["kind"] == "follow_up_call"]
    first = first.replace(tzinfo=None)  # SQLite drops the offset; Postgres keeps UTC
    assert [datetime.fromisoformat(r["scheduledAt"]).replace(tzinfo=None) for r in calls] == [
        first,
        first + timedelta(days=2),
        first + timedelta(days=4),
    ]
    caregiver = client.get(
        "/internal/caregiver/cases/case_poc_01", headers=internal_auth_headers
    ).json()
    assert datetime.fromisoformat(caregiver["nextCallAt"]).replace(tzinfo=None) == first


def test_a_call_time_in_the_past_blocks_approval(client, internal_auth_headers):
    body = intake_body()
    body["callPlan"]["firstCallAt"] = "2020-01-01T09:00:00+00:00"
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    response = approve(client, internal_auth_headers, "case_poc_01", "past-call")

    assert response.json() == {"error": "call_time_in_past"}


def test_insurer_regenerates_drafts_from_the_corrected_medication_list(
    client, internal_auth_headers, fixtures_dir
):
    app.dependency_overrides[get_object_storage] = pdf_storage(fixtures_dir)
    client.post(
        "/internal/workspace/cases", json=pdf_intake_body("ar"), headers=internal_auth_headers
    )
    detail = client.get(
        "/internal/workspace/cases/case_poc_01", headers=internal_auth_headers
    ).json()
    content = {k: detail[k] for k in ("dischargeVoiceNote", "medications", "callPlan")}
    content["medications"] = content["medications"][:1]
    client.patch(
        "/internal/workspace/cases/case_poc_01/content", json=content, headers=internal_auth_headers
    )

    response = client.post(
        "/internal/workspace/cases/case_poc_01/draft", headers=internal_auth_headers
    )

    assert response.status_code == 200
    script = response.json()["dischargeVoiceNote"]["script"]
    assert script.startswith("السلام عليكم أم نورة.")
    assert "Fictional medicine A" in script and "Fictional medicine B" not in script


def test_coverage_is_checked_at_intake_and_enrollment_is_recorded_at_approval(
    client, internal_auth_headers
):
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)

    approval = approve(client, internal_auth_headers, "case_poc_01", "covered")
    insurance = approval.json()["insurance"]

    assert insurance["status"] == "eligible"
    assert insurance["plan"]
    assert insurance["enrollmentReference"].startswith("ENR-")


def test_approval_requires_an_eligible_member(client, internal_auth_headers):
    body = intake_body()
    body.pop("memberId")
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)

    missing = approve(client, internal_auth_headers, "case_poc_01", "no-member")
    lapsed = client.post(
        "/internal/workspace/cases/case_poc_01/eligibility",
        json={"memberId": "SYN-1000000"},
        headers=internal_auth_headers,
    )
    blocked = approve(client, internal_auth_headers, "case_poc_01", "lapsed")
    covered = client.post(
        "/internal/workspace/cases/case_poc_01/eligibility",
        json={"memberId": "SYN-4471203"},
        headers=internal_auth_headers,
    )

    assert missing.json() == {"error": "eligibility_not_verified"}
    assert lapsed.json()["insurance"]["reason"] == "policy_lapsed"
    assert blocked.json() == {"error": "member_not_eligible"}
    assert covered.json()["insurance"]["status"] == "eligible"
    assert approve(client, internal_auth_headers, "case_poc_01", "ok").status_code == 200


def test_case_detail_says_when_delivery_is_only_simulated(client, internal_auth_headers):
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)

    detail = client.get("/internal/workspace/cases/case_poc_01", headers=internal_auth_headers)

    assert detail.json()["deliveryMode"] == "mock"
