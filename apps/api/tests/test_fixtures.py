import hashlib
import json

from scripts.make_fixture_pdf import render_pdf


def test_the_fake_pdf_is_rendered_from_the_plan_and_its_hash_is_recorded(plan, fixtures_dir):
    pdf = (fixtures_dir / "approved-plan.abu-mohammed.pdf").read_bytes()

    assert render_pdf(plan) == pdf
    expected_hash = "sha256:" + hashlib.sha256(pdf).hexdigest()
    assert plan["approvedPlan"]["source"]["sourceHash"] == expected_hash


def test_the_plan_is_the_documented_demo_case(plan):
    facts = plan["approvedPlan"]["clinicalFacts"]

    assert len(facts["newMedicines"]) == 3
    assert len(facts["stoppedMedicines"]) == 1
    assert facts["emergencyNumber"] == "997"
    assert plan["case"]["expectedBoxCount"] == len(facts["newMedicines"])


def test_the_expected_review_event_matches_the_case(plan, fixtures_dir):
    path = fixtures_dir / "expected-review-event.abu-mohammed.json"
    event = json.loads(path.read_text(encoding="utf-8"))
    case, approved = plan["case"], plan["approvedPlan"]

    assert event["eventType"] == "pharmacist_review_requested"
    assert event["idempotencyKey"] == f"{case['caseId']}:pharmacist_review_requested:v1"
    assert event["case"]["caseId"] == case["caseId"]
    assert event["case"]["expectedBoxCount"] == case["expectedBoxCount"]
    assert event["case"]["receivedBoxCount"] == len(event["medicinePhotos"])
    assert len(event["medicinePhotos"]) == case["expectedBoxCount"]
    assert event["approvedPlan"] == {
        "planId": approved["planId"],
        "version": approved["version"],
        "sourceHash": approved["source"]["sourceHash"],
    }
