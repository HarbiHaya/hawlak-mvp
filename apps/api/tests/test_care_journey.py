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
