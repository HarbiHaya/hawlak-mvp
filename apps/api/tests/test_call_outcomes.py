from app.models import Alert


def approved_runs(client, internal_auth_headers) -> list[dict]:
    body = {
        "caseId": "case_call_outcome",
        "patientName": "سارة أحمد التجريبية",
        "preferredFormOfAddress": "أم أحمد",
        "phoneE164": "+966500000000",
        "languageCode": "ar",
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {
            "objectKey": "synthetic/discharges/call-outcome.pdf",
            "filename": "synthetic-discharge.pdf",
        },
        "dischargeVoiceNote": {
            "enabled": True,
            "script": "هذه تعليمات خروج معتمدة لحالة تجريبية.",
        },
        "medications": [
            {
                "medicationId": "SYN-CALL-MED-001",
                "displayName": "دواء تجريبي جيم",
                "doseInstruction": "قرص تجريبي واحد صباحا",
                "dispensed": True,
                "image": {
                    "source": "catalog",
                    "objectKey": "synthetic/catalog/med-c.jpg",
                    "reviewStatus": "approved",
                },
                "reminderEnabled": True,
                "reminderScript": "هذا تذكير معتمد لدواء تجريبي جيم.",
            }
        ],
        "callPlan": {
            "enabled": True,
            "scheduledAfterHours": 24,
            "openingScript": "سأسألك الآن الأسئلة المعتمدة.",
            "questions": [{"id": "red-flag", "prompt": "هل تشعر بألم جديد؟"}],
            "completionScript": "شكرا، انتهت المتابعة.",
            "transferScript": "سأحولك الآن إلى فريق الرعاية.",
            "transferTarget": "integrated_care",
            "responderPhoneE164": "+966511111111",
        },
    }
    client.post("/internal/workspace/cases", json=body, headers=internal_auth_headers)
    response = client.post(
        "/internal/workspace/cases/case_call_outcome/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-CALL"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-call-outcome"},
    )
    return response.json()["deliveryRuns"]


def mark_sent(client, internal_auth_headers, run_id: str) -> None:
    client.post(
        f"/internal/delivery-runs/{run_id}/claim",
        headers={**internal_auth_headers, "Idempotency-Key": f"claim-{run_id}"},
    )
    client.patch(
        f"/internal/delivery-runs/{run_id}",
        json={"status": "sent", "providerRef": "synthetic-call-dispatch"},
        headers=internal_auth_headers,
    )


def test_transferred_call_outcome_is_idempotent_and_opens_one_minimized_alert(
    client, internal_auth_headers, db_session
):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, call_run["id"])
    payload = {
        "status": "transferred",
        "providerRef": "synthetic-call-outcome",
        "escalation": {"questionId": "red-flag", "answerKind": "red_flag"},
    }
    headers = {**internal_auth_headers, "Idempotency-Key": "call-outcome-transfer-01"}

    first = client.post(
        f"/internal/delivery-runs/{call_run['id']}/call-outcome",
        json=payload,
        headers=headers,
    )
    replay = client.post(
        f"/internal/delivery-runs/{call_run['id']}/call-outcome",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "transferred"
    assert db_session.query(Alert).count() == 1
    alert = db_session.query(Alert).one()
    assert alert.type == "call_escalation"
    assert alert.status == "open"
    assert alert.summary == "Call escalation: red_flag at approved question red-flag"
    assert "+966" not in alert.summary
    assert "ألم" not in alert.summary
    caregiver = client.get(
        "/internal/caregiver/cases/case_call_outcome", headers=internal_auth_headers
    )
    assert caregiver.json()["openAlertCount"] == 1


def test_completed_call_outcome_is_idempotent_without_alert(
    client, internal_auth_headers, db_session
):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, call_run["id"])
    headers = {**internal_auth_headers, "Idempotency-Key": "call-outcome-completed-01"}
    payload = {"status": "completed", "providerRef": "synthetic-completed-call"}

    first = client.post(
        f"/internal/delivery-runs/{call_run['id']}/call-outcome",
        json=payload,
        headers=headers,
    )
    replay = client.post(
        f"/internal/delivery-runs/{call_run['id']}/call-outcome",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "completed"
    assert db_session.query(Alert).count() == 0


def test_call_outcome_rejects_non_call_run_and_invalid_transition(client, internal_auth_headers):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    reminder_run = next(run for run in runs if run["kind"] == "medication_reminder")
    headers = {**internal_auth_headers, "Idempotency-Key": "invalid-call-outcome"}

    non_call = client.post(
        f"/internal/delivery-runs/{reminder_run['id']}/call-outcome",
        json={"status": "completed"},
        headers=headers,
    )
    pending_call = client.post(
        f"/internal/delivery-runs/{call_run['id']}/call-outcome",
        json={"status": "completed"},
        headers=headers,
    )

    assert non_call.status_code == 409
    assert non_call.json() == {"error": "delivery_run_is_not_call"}
    assert pending_call.status_code == 409
    assert pending_call.json() == {"error": "call_run_not_sent"}


def test_transferred_call_outcome_requires_a_valid_minimized_escalation(
    client, internal_auth_headers
):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, call_run["id"])
    url = f"/internal/delivery-runs/{call_run['id']}/call-outcome"
    headers = {**internal_auth_headers, "Idempotency-Key": "invalid-transfer-outcome"}

    missing = client.post(url, json={"status": "transferred"}, headers=headers)
    unknown_question = client.post(
        url,
        json={
            "status": "transferred",
            "escalation": {"questionId": "not-approved", "answerKind": "uncertain"},
        },
        headers=headers,
    )

    assert missing.status_code == 422
    assert unknown_question.status_code == 409
    assert unknown_question.json() == {"error": "call_question_not_approved"}
    assert db_session_status(client, internal_auth_headers, call_run["id"]) == "sent"


def test_call_outcome_requires_internal_authentication_and_idempotency_key(client):
    url = "/internal/delivery-runs/synthetic-run/call-outcome"

    unauthenticated = client.post(
        url,
        json={"status": "completed"},
        headers={"Idempotency-Key": "synthetic-outcome"},
    )
    missing_idempotency_key = client.post(
        url,
        json={"status": "completed"},
        headers={"Authorization": "Bearer test-internal-api-token-long-enough"},
    )

    assert unauthenticated.status_code == 401
    assert missing_idempotency_key.status_code == 422


def db_session_status(client, internal_auth_headers, run_id: str) -> str:
    response = client.get(
        "/internal/workspace/cases/case_call_outcome", headers=internal_auth_headers
    )
    return next(run["status"] for run in response.json()["deliveryRuns"] if run["id"] == run_id)
