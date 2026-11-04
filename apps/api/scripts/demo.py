"""Run Hawlak's synthetic demo in deterministic mock mode or guarded live mode.

From the repository root:

    uv run --directory apps/api python -m scripts.demo --mock --case abu-mohammed

Mock mode uses in-memory fakes and no provider keys or network. Live mode talks
to an already-running Hawlak API only after all preflight checks pass, then
requires the operator to type the exact generated script checksum.
"""

import argparse
import asyncio
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base
from app.schemas.approved_plan import ApprovedPlanDocument
from app.schemas.review_event import ReviewOutcomeRequest
from app.services.case_service import CaseService
from app.services.dialect_composer import MockDialectComposer
from app.services.inbound_workflow import InboundWorkflow
from app.services.object_storage import StoredObject
from app.services.review_service import ReviewService
from app.services.voice_renderer import MockVoiceRenderer
from app.services.voice_workflow import VoiceWorkflow
from app.services.whatsapp_client import DownloadedMedia

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "fixtures"
CASES = {"abu-mohammed": FIXTURES / "approved-plan.abu-mohammed.json"}


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


class PreflightFailed(RuntimeError):
    pass


class DemoStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def store_case_media(self, *, case_id, content, content_type, source_media_id):
        extension = "ogg" if content_type == "audio/ogg" else "jpg"
        key = f"cases/{case_id}/media/{source_media_id}.{extension}"
        self.objects[key] = content
        return StoredObject(
            key=key,
            size=len(content),
            sha256=sha256(content).hexdigest(),
            etag="mock",
            content_type=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]


class DemoWhatsApp:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def send_text(self, to: str, text: str) -> str:
        self.calls.append(("text", to[-4:], text))
        return f"wamid.mock.{len(self.calls)}"

    async def upload_audio(self, audio: bytes, filename: str) -> str:
        self.calls.append(("upload", filename, len(audio)))
        return "meta-audio-mock"

    async def send_audio(self, to: str, media_id: str) -> str:
        self.calls.append(("audio", to[-4:], media_id))
        return f"wamid.mock.{len(self.calls)}"

    async def download_image(self, media_id: str) -> DownloadedMedia:
        return DownloadedMedia(f"synthetic:{media_id}".encode(), "image/jpeg")


def load_case(name: str) -> dict[str, Any]:
    return json.loads(CASES[name].read_text(encoding="utf-8"))


def require_preflight(checks: list[PreflightCheck]) -> None:
    failures = [check.name for check in checks if not check.passed]
    if failures:
        raise PreflightFailed("required checks failed: " + ", ".join(failures))


async def run_mock(
    plan: dict[str, Any],
    *,
    approve: Callable[[str], bool],
) -> dict[str, Any]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            document = ApprovedPlanDocument.model_validate(plan)
            case = CaseService(session).create_case(document, "+966500000000")
            storage = DemoStorage()
            whatsapp = DemoWhatsApp()
            voice = VoiceWorkflow(
                session,
                MockDialectComposer(),
                MockVoiceRenderer(),
                storage,
                whatsapp,
            )
            generated = await voice.generate_script(case.case.id)
            checksum = generated.artifact.generated_script_sha256 or ""
            if not approve(checksum):
                raise RuntimeError("operator did not approve the exact script checksum")
            sent = await voice.approve_and_send(
                case_id=case.case.id,
                artifact_id=generated.artifact.id,
                script_checksum=checksum,
                approved_by="demo-operator",
                idempotency_key="mock-demo-send-v1",
            )

            inbound = InboundWorkflow(session, storage, whatsapp)
            for number in range(1, case.case.expected_box_count + 1):
                values = {
                    "wa_message_id": f"wamid.mock.photo.{number}",
                    "sender": case.case.phone_e164,
                    "message_type": "image",
                    "media_id": f"mock-media-{number}",
                    "mime_type": "image/jpeg",
                }
                await inbound.ingest_message(**values)
                await inbound.ingest_message(**values)
            done = {
                "wa_message_id": "wamid.mock.done",
                "sender": case.case.phone_e164,
                "message_type": "text",
                "text": "تم",
            }
            await inbound.ingest_message(**done)
            await inbound.ingest_message(**done)

            review = ReviewService(session)
            events, cursor = review.list_events(None, 20)
            if len(events) != 1:
                raise RuntimeError("mock demo did not create exactly one review event")
            outcome = ReviewOutcomeRequest(
                event_version=1,
                outcome="matched",
                reviewer_id="demo-pharmacist-01",
            )
            first = review.record_outcome(events[0].event_id, "mock-outcome-v1", outcome)
            replayed = review.record_outcome(events[0].event_id, "mock-outcome-v1", outcome)
            return {
                "mode": "mock",
                "synthetic": True,
                "caseId": case.case.id,
                "scriptChecksum": checksum,
                "factGuardPassed": not generated.differences,
                "messageIds": sent.message_ids,
                "storedObjectCount": len(storage.objects),
                "reviewEvent": events[0].model_dump(mode="json", by_alias=True),
                "nextCursor": cursor,
                "outcomeId": first.outcome.id,
                "outcomeReplayCreated": replayed.created,
            }
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


async def collect_live_preflight(
    settings: Settings,
    base_url: str,
    plan: dict[str, Any],
) -> list[PreflightCheck]:
    openai_ready = (
        settings.openai_api_key is not None
        and not settings.openai_api_key.get_secret_value().startswith("replace_")
    )
    elevenlabs_ready = (
        settings.elevenlabs_api_key is not None
        and not settings.elevenlabs_api_key.get_secret_value().startswith("replace_")
        and not settings.elevenlabs_voice_id.startswith("replace_")
    )
    checks = [
        PreflightCheck(
            "live provider mode",
            settings.demo_provider_mode == "live",
            "DEMO_PROVIDER_MODE must be live",
        ),
        PreflightCheck(
            "OpenAI key",
            openai_ready,
            "configured" if openai_ready else "missing or placeholder",
        ),
        PreflightCheck(
            "ElevenLabs key and voice",
            elevenlabs_ready,
            "configured" if elevenlabs_ready else "missing or placeholder",
        ),
        PreflightCheck(
            "ffprobe",
            shutil.which("ffprobe") is not None,
            "available" if shutil.which("ffprobe") else "missing",
        ),
        _fixture_hash_check(plan),
    ]
    headers = {"Authorization": f"Bearer {settings.internal_api_token.get_secret_value()}"}
    async with httpx.AsyncClient(timeout=15) as client:
        for name, url, request_headers in (
            ("API health", f"{base_url}/health", None),
            ("MinIO health", f"{base_url}/health/storage", None),
            ("internal API auth", f"{base_url}/internal/review-events", headers),
        ):
            try:
                response = await client.get(url, headers=request_headers)
                checks.append(
                    PreflightCheck(name, response.is_success, f"HTTP {response.status_code}")
                )
            except httpx.HTTPError:
                checks.append(PreflightCheck(name, False, "unreachable"))
        try:
            meta = await client.get(
                "https://graph.facebook.com/"
                f"{settings.meta_graph_api_version}/{settings.whatsapp_phone_number_id}",
                params={"fields": "verified_name,quality_rating"},
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            )
            checks.append(
                PreflightCheck("Meta test number", meta.is_success, f"HTTP {meta.status_code}")
            )
        except httpx.HTTPError:
            checks.append(PreflightCheck("Meta test number", False, "unreachable"))
    return checks


def _fixture_hash_check(plan: dict[str, Any]) -> PreflightCheck:
    source = plan["approvedPlan"]["source"]
    document = FIXTURES / source["document"]
    expected = source["sourceHash"]
    if not document.is_file():
        return PreflightCheck("fixture hash", False, "source document missing")
    actual = "sha256:" + sha256(document.read_bytes()).hexdigest()
    return PreflightCheck(
        "fixture hash", actual == expected, "matches" if actual == expected else "mismatch"
    )


async def run_live(
    plan: dict[str, Any],
    *,
    base_url: str,
    approve: Callable[[str], bool],
    wait_seconds: int,
) -> dict[str, Any]:
    settings = get_settings()
    checks = await collect_live_preflight(settings, base_url, plan)
    for check in checks:
        print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    require_preflight(checks)

    headers = {"Authorization": f"Bearer {settings.internal_api_token.get_secret_value()}"}
    body = {**plan, "demoRecipient": settings.whatsapp_test_recipient}
    async with httpx.AsyncClient(timeout=120) as client:
        created = await client.post(f"{base_url}/internal/cases", json=body, headers=headers)
        created.raise_for_status()
        generated = await client.post(
            f"{base_url}/internal/cases/{plan['case']['caseId']}/generate-script",
            headers=headers,
        )
        generated.raise_for_status()
        script = generated.json()
        checksum = script["scriptChecksum"]
        print("\nGenerated Arabic script:\n", script["spokenTextAr"])
        print("\nApproval checksum:", checksum)
        if not approve(checksum):
            raise RuntimeError("operator did not approve the exact script checksum")
        send_headers = {**headers, "Idempotency-Key": f"live-demo-{checksum[-12:]}"}
        sent = await client.post(
            f"{base_url}/internal/cases/{plan['case']['caseId']}/approve-and-send",
            json={
                "artifactId": script["artifactId"],
                "scriptChecksum": checksum,
                "approvedBy": "live-demo-operator",
            },
            headers=send_headers,
        )
        sent.raise_for_status()
        result = sent.json()
        if wait_seconds:
            print("Waiting for synthetic phone photos and the pharmacist-review event…")
            for _ in range(wait_seconds):
                events = await client.get(f"{base_url}/internal/review-events", headers=headers)
                events.raise_for_status()
                data = events.json()["data"]
                if data:
                    result["reviewEvent"] = data[0]
                    break
                await asyncio.sleep(1)
    return {"mode": "live", "synthetic": True, **result}


def typed_approval(expected: str, supplied: str | None) -> bool:
    actual = supplied
    if actual is None:
        actual = input("Type the exact checksum to approve and continue: ").strip()
    return actual == expected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="keyless deterministic local demo")
    mode.add_argument("--live", action="store_true", help="guarded live-provider/test-number demo")
    parser.add_argument("--case", choices=sorted(CASES), default="abu-mohammed")
    parser.add_argument("--url", default="http://127.0.0.1:3000", help="internal API base URL")
    parser.add_argument(
        "--approve-checksum",
        help="explicit checksum for automation; interactive use should omit this",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=120,
        help="live seconds to wait for inbound review event",
    )
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    plan = load_case(args.case)

    def approve(checksum: str) -> bool:
        return typed_approval(checksum, args.approve_checksum)

    if args.mock:
        result = await run_mock(plan, approve=approve)
    else:
        result = await run_live(
            plan,
            base_url=args.url.rstrip("/"),
            approve=approve,
            wait_seconds=args.wait_seconds,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
