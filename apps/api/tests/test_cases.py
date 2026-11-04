from copy import deepcopy

from app.models import ApprovedPlan, PatientCase


def request_body(plan: dict) -> dict:
    return {**plan, "demoRecipient": "+966500000000"}


def test_create_case_requires_internal_authentication(client, plan):
    response = client.post("/internal/cases", json=request_body(plan))

    assert response.status_code == 401


def test_create_case_is_created_then_replay_safe(client, internal_auth_headers, db_session, plan):
    body = request_body(plan)

    first = client.post("/internal/cases", json=body, headers=internal_auth_headers)
    second = client.post("/internal/cases", json=body, headers=internal_auth_headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json() == {
        "caseId": "case_01",
        "planId": "plan_01",
        "version": 1,
        "status": "active",
    }
    assert db_session.query(PatientCase).count() == 1
    assert db_session.query(ApprovedPlan).count() == 1


def test_create_case_rejects_a_conflicting_plan(client, internal_auth_headers, plan):
    body = request_body(plan)
    assert (
        client.post("/internal/cases", json=body, headers=internal_auth_headers).status_code == 201
    )
    conflicting = deepcopy(body)
    conflicting["approvedPlan"]["clinicalFacts"]["emergencyNumber"] = "998"

    response = client.post("/internal/cases", json=conflicting, headers=internal_auth_headers)

    assert response.status_code == 409
    assert response.json() == {"error": "case_conflict"}


def test_timeline_contains_case_and_plan_creation(client, internal_auth_headers, plan):
    client.post("/internal/cases", json=request_body(plan), headers=internal_auth_headers)

    response = client.get("/internal/cases/case_01/timeline", headers=internal_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["caseId"] == "case_01"
    assert [entry["type"] for entry in body["data"]] == [
        "case_created",
        "approved_plan_loaded",
    ]
    assert body["data"][1]["details"] == {"planId": "plan_01", "version": 1}


def test_timeline_returns_not_found_for_an_unknown_case(client, internal_auth_headers):
    response = client.get("/internal/cases/missing/timeline", headers=internal_auth_headers)

    assert response.status_code == 404
    assert response.json() == {"error": "case_not_found"}
