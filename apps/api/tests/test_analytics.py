from datetime import timedelta

from app.models import CareJourney, DeliveryRun, utc_now

NAME = "مريم خالد العتيبي"


def intake_body(case_id: str, phone: str, dispensed: bool = True) -> dict:
    return {
        "caseId": case_id,
        "patientName": NAME,
        "phoneE164": phone,
        "memberId": "SYN-4471203",
        "languageCode": "ar",
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {
            "objectKey": f"synthetic/discharges/{case_id}.pdf",
            "filename": "synthetic-discharge.pdf",
        },
        "dischargeVoiceNote": {"enabled": True, "script": "هذه تعليمات الخروج المعتمدة."},
        "medications": [
            {
                "medicationId": "SYN-MED-001",
                "displayName": "دواء تجريبي ألف",
                "doseInstruction": "قرص واحد صباحا",
                "dispensed": dispensed,
                "image": None,
                "reminderEnabled": dispensed,
                "reminderScript": "هذا تذكير بجرعة دواء تجريبي ألف.",
            }
        ],
    }


def register(client, headers, case_id: str, phone: str, dispensed: bool = True) -> None:
    body = intake_body(case_id, phone, dispensed)
    assert client.post("/internal/workspace/cases", json=body, headers=headers).status_code == 201


def approve(client, headers, case_id: str) -> None:
    response = client.post(
        f"/internal/workspace/cases/{case_id}/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-01"},
        headers={**headers, "Idempotency-Key": f"approve-{case_id}"},
    )
    assert response.status_code == 200


def session_headers(client, username: str) -> dict[str, str]:
    body = {"username": username, "password": "synthetic-demo-password"}
    token = client.post("/auth/login", json=body).json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_analytics_counts_the_programme_without_naming_a_patient(
    client, internal_auth_headers, db_session
):
    register(client, internal_auth_headers, "case_an_01", "+966500000001")
    register(client, internal_auth_headers, "case_an_02", "+966500000002")
    register(client, internal_auth_headers, "case_an_03", "+966500000003", dispensed=False)
    approve(client, internal_auth_headers, "case_an_01")
    approve(client, internal_auth_headers, "case_an_03")
    sent = db_session.query(DeliveryRun).filter_by(
        case_id="case_an_01", kind="discharge_voice_note"
    )
    sent.one().status = "sent"
    db_session.commit()

    response = client.get("/internal/workspace/analytics?days=30", headers=internal_auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["periodDays"] == 30
    assert {row["stage"]: row["count"] for row in data["funnel"]} == {
        "registered": 3,
        "eligible": 3,
        "approved": 2,
        "contacted": 1,
        "photos_received": 0,
        "call_completed": 0,
    }
    assert data["now"]["awaitingReview"] == 1
    assert data["now"]["openAlerts"] == {"high": 1, "low": 0}
    voice = next(row for row in data["delivery"] if row["kind"] == "discharge_voice_note")
    assert (voice["delivered"], voice["scheduled"], voice["failed"]) == (1, 1, 0)
    assert data["medications"] == {
        "total": 3,
        "notDispensed": 1,
        "remindersEnabled": 2,
        "withReminderTimes": 0,
        "withConfirmedStrength": 0,
    }
    access = next(row for row in data["alerts"] if row["type"] == "medication_access")
    assert (access["open"], access["resolved"]) == (1, 0)
    assert data["review"]["approvedWithin24hPct"] == 100
    assert sum(day["registered"] for day in data["daily"]) == 3
    assert len(data["daily"]) == 30
    # Aggregates only: no name, phone or case reference leaves this endpoint.
    for private in (NAME, "+9665", "case_an_"):
        assert private not in response.text


def test_analytics_period_leaves_out_older_cases(client, internal_auth_headers, db_session):
    register(client, internal_auth_headers, "case_an_old", "+966500000004")
    db_session.get(CareJourney, "case_an_old").created_at = utc_now() - timedelta(days=40)
    db_session.commit()

    week = client.get("/internal/workspace/analytics?days=7", headers=internal_auth_headers).json()
    quarter = client.get(
        "/internal/workspace/analytics?days=90", headers=internal_auth_headers
    ).json()

    assert week["funnel"][0] == {"stage": "registered", "count": 0}
    assert quarter["funnel"][0] == {"stage": "registered", "count": 1}
    # What waits now is shown whatever the period.
    assert week["now"]["awaitingReview"] == 1
    assert week["now"]["oldestWaitingHours"] > 24 * 39


def test_worklist_puts_attention_first_then_the_longest_waiting_review(
    client, internal_auth_headers, db_session
):
    register(client, internal_auth_headers, "case_wl_active", "+966500000011")
    register(client, internal_auth_headers, "case_wl_new", "+966500000012")
    register(client, internal_auth_headers, "case_wl_waiting", "+966500000013")
    register(client, internal_auth_headers, "case_wl_alert", "+966500000014", dispensed=False)
    approve(client, internal_auth_headers, "case_wl_active")
    approve(client, internal_auth_headers, "case_wl_alert")
    db_session.get(CareJourney, "case_wl_waiting").created_at = utc_now() - timedelta(hours=30)
    db_session.commit()

    rows = client.get("/internal/workspace/cases", headers=internal_auth_headers).json()["data"]

    assert [(row["caseId"], row["stage"]) for row in rows] == [
        ("case_wl_alert", "needs_attention"),
        ("case_wl_waiting", "needs_review"),
        ("case_wl_new", "needs_review"),
        ("case_wl_active", "active"),
    ]
    assert rows[0]["highAlertCount"] == 1
    assert rows[3]["nextStepAt"] is not None

    alerts = client.get("/internal/workspace/alerts", headers=internal_auth_headers).json()["data"]
    assert alerts[0]["severity"] == "high" and alerts[0]["resolvedAt"] is None


def test_hospital_sees_its_submissions_and_only_the_care_team_sees_analytics(
    client, internal_auth_headers
):
    register(client, internal_auth_headers, "case_hs_01", "+966500000021")
    hospital = session_headers(client, "hospital")
    insurer = session_headers(client, "insurer")

    listing = client.get("/internal/hospital/cases", headers=hospital)

    assert listing.status_code == 200
    (row,) = listing.json()["data"]
    assert set(row) == {"caseId", "patientName", "submittedAt", "reviewStatus", "approvedAt"}
    assert row["reviewStatus"] == "draft"
    assert client.get("/internal/workspace/analytics", headers=hospital).status_code == 403
    assert client.get("/internal/workspace/analytics", headers=insurer).status_code == 200
    assert client.get("/internal/hospital/cases", headers=insurer).status_code == 403
    assert (
        client.get(
            "/internal/workspace/analytics", headers=session_headers(client, "caregiver")
        ).status_code
        == 403
    )
