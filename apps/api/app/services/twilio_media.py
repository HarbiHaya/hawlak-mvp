import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class TwilioMediaTokenError(ValueError):
    """The public media token is invalid or expired."""


@dataclass(frozen=True, slots=True)
class TwilioPublicMedia:
    object_key: str
    content_type: str
    expires_at: int


def create_twilio_media_token(
    object_key: str,
    content_type: str,
    secret: str,
    *,
    expires_in: int = 900,
    now: int | None = None,
) -> str:
    if not object_key or content_type not in {"audio/ogg", "image/jpeg", "image/png"}:
        raise ValueError("unsupported public media")
    timestamp = int(time.time() if now is None else now)
    payload = json.dumps(
        {"key": object_key, "type": content_type, "exp": timestamp + expires_in},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def resolve_twilio_media_token(
    token: str,
    secret: str,
    *,
    now: int | None = None,
) -> TwilioPublicMedia:
    try:
        encoded, supplied_signature = token.rsplit(".", 1)
        expected_signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise TwilioMediaTokenError("invalid media signature")
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        media = TwilioPublicMedia(
            object_key=str(payload["key"]),
            content_type=str(payload["type"]),
            expires_at=int(payload["exp"]),
        )
    except TwilioMediaTokenError:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise TwilioMediaTokenError("invalid media token") from exc

    timestamp = int(time.time() if now is None else now)
    if media.expires_at < timestamp:
        raise TwilioMediaTokenError("expired media token")
    if media.content_type not in {"audio/ogg", "image/jpeg", "image/png"}:
        raise TwilioMediaTokenError("unsupported media type")
    return media
