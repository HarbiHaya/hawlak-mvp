"""Play the patient's side of a case against a running Hawlak API.

Sends signed Meta-style webhooks: one photo message per medicine box, then optionally "تم"
("done"). Run from apps/api so .env is found:

    uv run python -m scripts.replay_patient ../../fixtures/approved-plan.abu-mohammed.json --done
"""

import argparse
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

from app.config import get_settings

Post = Callable[[bytes, str], int]  # (raw body, X-Hub-Signature-256 value) -> HTTP status


def sign(body: bytes, app_secret: str) -> str:
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


def webhook_body(message: dict, *, phone: str, phone_number_id: str, alias: str) -> bytes:
    """One inbound-message webhook in the shape Meta sends (trimmed to what the API reads)."""
    wa_id = phone.lstrip("+")
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550000000", "phone_number_id": phone_number_id},
        "contacts": [{"profile": {"name": alias}, "wa_id": wa_id}],
        "messages": [{"from": wa_id, "timestamp": str(int(time.time())), **message}],
    }
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "SYNTHETIC-WABA", "changes": [{"field": "messages", "value": value}]}],
    }
    return json.dumps(payload, ensure_ascii=False).encode()


def replay(
    plan: dict,
    *,
    post: Post,
    phone: str,
    phone_number_id: str,
    app_secret: str,
    photos: int | None = None,
    done: bool = False,
    repeat: bool = False,
    run_id: str | None = None,
) -> list[int]:
    """Send the patient's photos (and "تم") as signed webhooks; return the HTTP statuses."""
    case = plan["case"]
    run_id = run_id or uuid.uuid4().hex[:8]
    count = case["expectedBoxCount"] if photos is None else photos
    messages = [
        {
            "id": f"wamid.REPLAY.{run_id}.{n}",
            "type": "image",
            "image": {"id": f"MEDIA-REPLAY-{run_id}-{n}", "mime_type": "image/jpeg"},
        }
        for n in range(1, count + 1)
    ]
    if done:
        text = {"body": "تم"}
        messages.append({"id": f"wamid.REPLAY.{run_id}.done", "type": "text", "text": text})

    statuses = []
    for message in messages:
        body = webhook_body(
            message, phone=phone, phone_number_id=phone_number_id, alias=case["patientAlias"]
        )
        for _ in range(2 if repeat else 1):
            statuses.append(post(body, sign(body, app_secret)))
    return statuses


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("plan", type=Path, help="approved-plan fixture (JSON)")
    parser.add_argument("--url", default="http://127.0.0.1:3000", help="API base URL or tunnel URL")
    parser.add_argument(
        "--photos", type=int, help="photo count (default: the case's expectedBoxCount)"
    )
    parser.add_argument("--done", action="store_true", help='finish with the text message "تم"')
    parser.add_argument("--repeat", action="store_true", help="send every message twice")
    parser.add_argument("--run-id", help="fixed id: a re-run replays the same WhatsApp message IDs")
    args = parser.parse_args()

    settings = get_settings()

    def post(body: bytes, signature: str) -> int:
        headers = {"content-type": "application/json", "x-hub-signature-256": signature}
        response = httpx.post(f"{args.url}/webhooks/whatsapp", content=body, headers=headers)
        return response.status_code

    statuses = replay(
        json.loads(args.plan.read_text(encoding="utf-8")),
        post=post,
        phone=settings.whatsapp_test_recipient,
        phone_number_id=settings.whatsapp_phone_number_id,
        app_secret=settings.meta_app_secret,
        photos=args.photos,
        done=args.done,
        repeat=args.repeat,
        run_id=args.run_id,
    )
    print("HTTP statuses:", statuses)


if __name__ == "__main__":
    main()
