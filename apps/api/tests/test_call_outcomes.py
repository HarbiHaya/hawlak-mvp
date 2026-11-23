from app.models import Alert, WorkflowEvent


def approved_runs(client, internal_auth_headers, case_id: str = "case_call_outcome") -> list[dict]:
    body = {
        "caseId": case_id,
        "patientName": "سارة أحمد التجريبية",
        "preferredFormOfAddress": "أم أحمد",
        "phoneE164": "+966500000000",
        "memberId": "SYN-4471203",
        "languageCode": "ar",
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {
            "objectKey": f"synthetic/discharges/{case_id}.pdf",
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
        f"/internal/workspace/cases/{case_id}/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-CALL"},
        headers={**internal_auth_headers, "Idempotency-Key": f"approve-{case_id}"},
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
    assert db_session.query(WorkflowEvent).count() == 1
    event = db_session.query(WorkflowEvent).one()
    assert event.event_type == "call_outcome"
    assert event.idempotency_key == "call-outcome-transfer-01"
    assert event.payload == {"runId": call_run["id"], **payload}
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
    assert caregiver.json()["nextCallAt"] is None


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
    assert db_session.query(WorkflowEvent).count() == 1
    caregiver = client.get(
        "/internal/caregiver/cases/case_call_outcome", headers=internal_auth_headers
    )
    assert caregiver.json()["nextCallAt"] is None


def test_failed_call_outcome_is_idempotent_and_opens_one_minimized_alert(
    client, internal_auth_headers, db_session
):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, call_run["id"])
    payload = {
        "status": "failed",
        "providerRef": "synthetic-failed-call",
        "escalation": {"questionId": "red-flag", "answerKind": "uncertain"},
    }
    headers = {**internal_auth_headers, "Idempotency-Key": "call-outcome-failed-01"}
    url = f"/internal/delivery-runs/{call_run['id']}/call-outcome"

    first = client.post(url, json=payload, headers=headers)
    replay = client.post(url, json=payload, headers=headers)

    assert first.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "failed"
    assert db_session.query(Alert).count() == 1
    assert db_session.query(WorkflowEvent).count() == 1
    alert = db_session.query(Alert).one()
    event = db_session.query(WorkflowEvent).one()
    assert alert.type == "call_escalation"
    assert alert.summary == "Call escalation: uncertain at approved question red-flag"
    assert event.event_type == "call_outcome"
    assert event.idempotency_key == "call-outcome-failed-01"
    assert event.payload == {"runId": call_run["id"], **payload}
    caregiver = client.get(
        "/internal/caregiver/cases/case_call_outcome", headers=internal_auth_headers
    )
    assert caregiver.json()["openAlertCount"] == 1
    assert caregiver.json()["nextCallAt"] is None


def test_failed_call_outcome_requires_a_valid_minimized_escalation(client, internal_auth_headers):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, call_run["id"])
    url = f"/internal/delivery-runs/{call_run['id']}/call-outcome"
    headers = {**internal_auth_headers, "Idempotency-Key": "invalid-failed-outcome"}

    missing = client.post(url, json={"status": "failed"}, headers=headers)
    unknown_question = client.post(
        url,
        json={
            "status": "failed",
            "escalation": {"questionId": "not-approved", "answerKind": "red_flag"},
        },
        headers=headers,
    )

    assert missing.status_code == 422
    assert unknown_question.status_code == 409
    assert unknown_question.json() == {"error": "call_question_not_approved"}
    assert db_session_status(client, internal_auth_headers, call_run["id"]) == "sent"


def test_call_outcome_rejects_conflicting_replays_without_duplicate_events_or_alerts(
    client, internal_auth_headers, db_session
):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, call_run["id"])
    url = f"/internal/delivery-runs/{call_run['id']}/call-outcome"
    original = {
        "status": "transferred",
        "providerRef": "synthetic-transfer",
        "escalation": {"questionId": "red-flag", "answerKind": "uncertain"},
    }
    first = client.post(
        url,
        json=original,
        headers={**internal_auth_headers, "Idempotency-Key": "stable-call-outcome-key"},
    )

    changed_payload = client.post(
        url,
        json={
            **original,
            "escalation": {"questionId": "red-flag", "answerKind": "red_flag"},
        },
        headers={**internal_auth_headers, "Idempotency-Key": "stable-call-outcome-key"},
    )
    changed_key = client.post(
        url,
        json=original,
        headers={**internal_auth_headers, "Idempotency-Key": "different-call-outcome-key"},
    )

    assert first.status_code == 200
    assert changed_payload.status_code == 409
    assert changed_payload.json() == {"error": "idempotency_key_conflict"}
    assert changed_key.status_code == 409
    assert changed_key.json() == {"error": "call_outcome_already_recorded"}
    assert db_session.query(WorkflowEvent).count() == 1
    assert db_session.query(Alert).count() == 1


def test_call_outcome_idempotency_key_cannot_be_reused_for_another_run(
    client, internal_auth_headers, db_session
):
    first_runs = approved_runs(client, internal_auth_headers, "case_call_outcome_a")
    second_runs = approved_runs(client, internal_auth_headers, "case_call_outcome_b")
    first_call = next(run for run in first_runs if run["kind"] == "follow_up_call")
    second_call = next(run for run in second_runs if run["kind"] == "follow_up_call")
    mark_sent(client, internal_auth_headers, first_call["id"])
    mark_sent(client, internal_auth_headers, second_call["id"])
    headers = {**internal_auth_headers, "Idempotency-Key": "shared-call-outcome-key"}

    first = client.post(
        f"/internal/delivery-runs/{first_call['id']}/call-outcome",
        json={"status": "completed"},
        headers=headers,
    )
    reused = client.post(
        f"/internal/delivery-runs/{second_call['id']}/call-outcome",
        json={"status": "completed"},
        headers=headers,
    )

    assert first.status_code == 200
    assert reused.status_code == 409
    assert reused.json() == {"error": "idempotency_key_conflict"}
    assert db_session.query(WorkflowEvent).count() == 1


def test_caregiver_next_call_ignores_a_failed_call_run(client, internal_auth_headers):
    runs = approved_runs(client, internal_auth_headers)
    call_run = next(run for run in runs if run["kind"] == "follow_up_call")
    client.post(
        f"/internal/delivery-runs/{call_run['id']}/claim",
        headers={**internal_auth_headers, "Idempotency-Key": "claim-failed-call"},
    )
    failed = client.patch(
        f"/internal/delivery-runs/{call_run['id']}",
        json={"status": "failed", "providerRef": "synthetic-call-failure"},
        headers=internal_auth_headers,
    )

    caregiver = client.get(
        "/internal/caregiver/cases/case_call_outcome", headers=internal_auth_headers
    )

    assert failed.status_code == 200
    assert caregiver.json()["nextCallAt"] is None


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


TURNS = {
    "turns": [
        {"seq": 1, "speaker": "agent", "text": "سأسألك الآن الأسئلة المعتمدة.", "guard": "ok"},
        {"seq": 2, "speaker": "patient", "text": "تفضل", "answerKind": "clear"},
    ]
}


def call_run_id(client, internal_auth_headers, case_id="case_call_turns") -> str:
    runs = approved_runs(client, internal_auth_headers, case_id)
    return next(run["id"] for run in runs if run["kind"] == "follow_up_call")


def test_call_turns_round_trip_for_the_care_team(client, internal_auth_headers):
    run_id = call_run_id(client, internal_auth_headers)

    posted = client.post(
        f"/internal/delivery-runs/{run_id}/call-turns",
        json=TURNS,
        headers={**internal_auth_headers, "Idempotency-Key": f"turns-{run_id}"},
    )
    read = client.get(
        f"/internal/workspace/cases/case_call_turns/calls/{run_id}/turns",
        headers=internal_auth_headers,
    )

    assert posted.status_code == 202
    assert [(t["seq"], t["speaker"], t["text"]) for t in read.json()["data"]] == [
        (1, "agent", "سأسألك الآن الأسئلة المعتمدة."),
        (2, "patient", "تفضل"),
    ]
    assert read.json()["data"][1]["answerKind"] == "clear"


def test_reposting_call_turns_adds_nothing(client, internal_auth_headers):
    run_id = call_run_id(client, internal_auth_headers)
    headers = {**internal_auth_headers, "Idempotency-Key": f"turns-{run_id}"}

    for _ in range(2):
        client.post(f"/internal/delivery-runs/{run_id}/call-turns", json=TURNS, headers=headers)

    read = client.get(
        f"/internal/workspace/cases/case_call_turns/calls/{run_id}/turns",
        headers=internal_auth_headers,
    )
    assert len(read.json()["data"]) == 2


def test_call_turns_only_attach_to_a_call_run(client, internal_auth_headers):
    runs = approved_runs(client, internal_auth_headers, "case_call_turns")
    voice_run = next(run["id"] for run in runs if run["kind"] == "discharge_voice_note")

    response = client.post(
        f"/internal/delivery-runs/{voice_run}/call-turns",
        json=TURNS,
        headers={**internal_auth_headers, "Idempotency-Key": "turns-voice"},
    )

    assert response.status_code == 409


def test_call_turn_text_stays_out_of_logs_and_the_caregiver_view(
    client, internal_auth_headers, caplog
):
    import logging

    run_id = call_run_id(client, internal_auth_headers)
    with caplog.at_level(logging.DEBUG):
        client.post(
            f"/internal/delivery-runs/{run_id}/call-turns",
            json=TURNS,
            headers={**internal_auth_headers, "Idempotency-Key": f"turns-{run_id}"},
        )
    caregiver = client.get(
        "/internal/caregiver/cases/case_call_turns", headers=internal_auth_headers
    )

    assert "تفضل" not in caplog.text
    assert "تفضل" not in caregiver.text
