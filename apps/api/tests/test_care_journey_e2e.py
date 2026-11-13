def synthetic_intake() -> dict:
    return {
        "caseId": "case_e2e_delivery",
        "patientName": "مها سالم التجريبية",
        "preferredFormOfAddress": "أم سالم",
        "phoneE164": "+966500000000",
        "memberId": "SYN-4471203",
        "languageCode": "ar",
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {
            "objectKey": "synthetic/discharges/case_e2e_delivery.pdf",
            "filename": "synthetic-discharge.pdf",
        },
    }


def synthetic_reviewed_content() -> dict:
    return {
        "dischargeVoiceNote": {
            "enabled": True,
            "script": "هذه تعليمات الخروج التي اعتمدها فريق الرعاية للحالة التجريبية.",
        },
        "medications": [
            {
                "medicationId": "SYN-E2E-MED-001",
                "displayName": "دواء تجريبي باء",
                "doseInstruction": "قرص تجريبي واحد مساء",
                "dispensed": True,
                "image": {
                    "source": "catalog",
                    "objectKey": "synthetic/catalog/med-b.jpg",
                    "reviewStatus": "approved",
                    "ocrCandidate": None,
                },
                "reminderEnabled": True,
                "reminderScript": "هذا تذكير معتمد بجرعة دواء تجريبي باء.",
                "unitStrength": None,
                "reminderTimes": [],
            }
        ],
        "callPlan": {
            "enabled": True,
            "scheduledAfterHours": 24,
            "firstCallAt": None,
            "repeat": "none",
            "occurrences": 1,
            "openingScript": "سأسألك الآن الأسئلة التي اعتمدها فريق الرعاية.",
            "questions": [{"id": "synthetic-check", "prompt": "هل تحتاج مساعدة؟"}],
            "completionScript": "شكرا، انتهت المتابعة التجريبية.",
            "transferScript": "سأحولك الآن إلى فريق الرعاية.",
            "transferTarget": "integrated_care",
            "responderPhoneE164": "+966511111111",
        },
    }


def test_hospital_intake_to_approved_mock_delivery_preserves_exact_content(
    client, internal_auth_headers
):
    intake = client.post(
        "/internal/workspace/cases",
        json=synthetic_intake(),
        headers=internal_auth_headers,
    )
    reviewed_content = synthetic_reviewed_content()
    review = client.patch(
        "/internal/workspace/cases/case_e2e_delivery/content",
        json=reviewed_content,
        headers=internal_auth_headers,
    )
    approval = client.post(
        "/internal/workspace/cases/case_e2e_delivery/approve",
        json={"approvedBy": "SYN-INTEGRATED-CARE-E2E"},
        headers={**internal_auth_headers, "Idempotency-Key": "approve-e2e-delivery-v1"},
    )
    dispatch = client.post(
        "/internal/workspace/cases/case_e2e_delivery/dispatch",
        headers={**internal_auth_headers, "Idempotency-Key": "dispatch-e2e-delivery-v1"},
    )
    detail = client.get(
        "/internal/workspace/cases/case_e2e_delivery",
        headers=internal_auth_headers,
    )

    assert intake.status_code == 201
    assert review.status_code == 200
    assert approval.status_code == 200
    assert dispatch.status_code == 200
    assert [run["kind"] for run in dispatch.json()["data"]] == [
        "discharge_voice_note",
        "medication_reminder",
        "photo_request",
    ]
    assert all(run["status"] == "sent" for run in dispatch.json()["data"])

    approved = detail.json()
    assert approved["reviewStatus"] == "approved"
    assert approved["dischargeVoiceNote"] == reviewed_content["dischargeVoiceNote"]
    assert approved["medications"] == reviewed_content["medications"]
    assert approved["callPlan"] == reviewed_content["callPlan"]
    assert {run["kind"]: run["status"] for run in approved["deliveryRuns"]} == {
        "discharge_voice_note": "sent",
        "medication_reminder": "sent",
        "photo_request": "sent",
        "follow_up_call": "pending",
    }

    rejected_edit = client.patch(
        "/internal/workspace/cases/case_e2e_delivery/content",
        json={
            **reviewed_content,
            "dischargeVoiceNote": {
                "enabled": True,
                "script": "نص لا يجوز أن يستبدل النص المعتمد.",
            },
        },
        headers=internal_auth_headers,
    )
    assert rejected_edit.status_code == 409
    assert rejected_edit.json() == {"error": "approved_content_is_immutable"}
