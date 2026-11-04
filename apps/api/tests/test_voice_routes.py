from dataclasses import dataclass
from types import SimpleNamespace

from app.main import app
from app.routes.voice import get_voice_workflow
from app.services.voice_workflow import VoiceWorkflowConflict, VoiceWorkflowNotFound


@dataclass
class FakeGenerated:
    artifact: object
    differences: list[dict]


@dataclass
class FakeSent:
    artifact: object
    message_ids: list[str]


class FakeWorkflow:
    def __init__(self):
        self.approval = None

    async def generate_script(self, case_id):
        return FakeGenerated(
            SimpleNamespace(
                id="artifact-1",
                generated_script_ar="نص تجريبي معتمد",
                generated_script_sha256="sha256:" + "a" * 64,
            ),
            [],
        )

    async def approve_and_send(self, **kwargs):
        self.approval = kwargs
        return FakeSent(
            SimpleNamespace(
                id="artifact-1",
                approved_script_sha256="sha256:" + "a" * 64,
                audio_checksum="sha256:" + "b" * 64,
            ),
            ["wamid.1", "wamid.2", "wamid.3"],
        )


def test_voice_options_drive_the_dashboard_selector(client, internal_auth_headers):
    assert client.get("/internal/voice-options").status_code == 401

    response = client.get("/internal/voice-options", headers=internal_auth_headers)

    assert response.status_code == 200
    assert [item["code"] for item in response.json()["dialects"]] == [
        "ar-SA-hijazi",
        "ar-SA-najdi",
        "ar-SA-janoubi",
    ]
    assert response.json()["voice"] == {
        "provider": "elevenlabs",
        "voiceLabel": "Configured Saudi Arabic voice",
        "modelId": "eleven_v4",
        "languageCode": "ar",
    }


def test_voice_routes_require_auth_and_forward_exact_approval(client, internal_auth_headers):
    workflow = FakeWorkflow()
    app.dependency_overrides[get_voice_workflow] = lambda: workflow

    assert client.post("/internal/cases/case_01/generate-script").status_code == 401
    generated = client.post(
        "/internal/cases/case_01/generate-script", headers=internal_auth_headers
    )
    assert generated.status_code == 200
    assert generated.json()["scriptChecksum"] == "sha256:" + "a" * 64

    body = {
        "artifactId": "artifact-1",
        "scriptChecksum": "sha256:" + "a" * 64,
        "approvedBy": "reviewer-1",
    }
    headers = {**internal_auth_headers, "Idempotency-Key": "send-1"}
    sent = client.post("/internal/cases/case_01/approve-and-send", json=body, headers=headers)
    assert sent.status_code == 200
    assert sent.json()["messageIds"] == ["wamid.1", "wamid.2", "wamid.3"]
    assert workflow.approval == {
        "case_id": "case_01",
        "artifact_id": "artifact-1",
        "script_checksum": "sha256:" + "a" * 64,
        "approved_by": "reviewer-1",
        "idempotency_key": "send-1",
    }


def test_voice_routes_require_idempotency_key(client, internal_auth_headers):
    app.dependency_overrides[get_voice_workflow] = lambda: FakeWorkflow()
    response = client.post(
        "/internal/cases/case_01/approve-and-send",
        json={
            "artifactId": "artifact-1",
            "scriptChecksum": "sha256:" + "a" * 64,
            "approvedBy": "reviewer-1",
        },
        headers=internal_auth_headers,
    )
    assert response.status_code == 422


def test_voice_routes_map_not_found_and_conflict(client, internal_auth_headers):
    class Missing(FakeWorkflow):
        async def generate_script(self, case_id):
            raise VoiceWorkflowNotFound(case_id)

        async def approve_and_send(self, **kwargs):
            raise VoiceWorkflowConflict("script_checksum_conflict")

    app.dependency_overrides[get_voice_workflow] = lambda: Missing()
    assert (
        client.post(
            "/internal/cases/missing/generate-script", headers=internal_auth_headers
        ).status_code
        == 404
    )
    response = client.post(
        "/internal/cases/case_01/approve-and-send",
        json={
            "artifactId": "artifact-1",
            "scriptChecksum": "sha256:" + "a" * 64,
            "approvedBy": "reviewer-1",
        },
        headers={**internal_auth_headers, "Idempotency-Key": "send-1"},
    )
    assert response.status_code == 409
    assert response.json() == {"error": "script_checksum_conflict"}
