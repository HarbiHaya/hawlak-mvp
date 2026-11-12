from hawlak_agent.mock_runner import run_mock_call


def test_mock_call_exercises_same_conversation_engine() -> None:
    result = run_mock_call(
        plan_payload={
            "id": "plan-synthetic-001",
            "caseId": "case-synthetic-001",
            "version": 1,
            "approvedAt": "2026-11-12T09:00:00Z",
            "phoneE164": "+966500000000",
            "participantLabel": "Synthetic patient",
            "language": "ar-SA",
            "openingScript": "Approved opening",
            "questions": [{"id": "status", "prompt": "Approved question"}],
            "completionScript": "Approved completion",
            "transferScript": "Approved transfer",
            "responderPhoneE164": "+966511111111",
        },
        answers=["clear"],
    )

    assert result == {
        "status": "completed",
        "spoken": ["Approved opening", "Approved question", "Approved completion"],
        "transferToLast4": None,
        "escalation": None,
    }


def test_mock_call_returns_safe_structured_escalation_outcome() -> None:
    result = run_mock_call(
        plan_payload={
            "id": "plan-synthetic-001",
            "caseId": "case-synthetic-001",
            "version": 1,
            "approvedAt": "2026-11-12T09:00:00Z",
            "phoneE164": "+966500000000",
            "participantLabel": "Synthetic patient",
            "language": "ar-SA",
            "openingScript": "Approved opening",
            "questions": [{"id": "status", "prompt": "Approved question"}],
            "completionScript": "Approved completion",
            "transferScript": "Approved transfer",
            "responderPhoneE164": "+966511111111",
        },
        answers=["red_flag"],
    )

    assert result == {
        "status": "transferred",
        "spoken": ["Approved opening", "Approved question", "Approved transfer"],
        "transferToLast4": "1111",
        "escalation": {
            "answerKind": "red_flag",
            "questionId": "status",
        },
    }
    assert "+966511111111" not in str(result)
