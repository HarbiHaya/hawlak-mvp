from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.config import Settings

DemoRole = Literal["admin", "hospital", "insurer", "caregiver"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z]+$")
    password: str = Field(min_length=12, max_length=128)


class LoginResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    access_token: str
    role: DemoRole
    username: str
    display_name: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class AccessContext:
    username: str
    role: str


ACCOUNTS: dict[str, tuple[DemoRole, str]] = {
    "admin": ("admin", "إدارة العرض"),
    "hospital": ("hospital", "فريق المستشفى"),
    "insurer": ("insurer", "فريق الرعاية المتكاملة"),
    "caregiver": ("caregiver", "مقدم الرعاية"),
}


def authenticate_demo_user(
    settings: Settings, username: str, password: str
) -> LoginResponse | None:
    account = ACCOUNTS.get(username.lower())
    configured_password = settings.demo_login_password.get_secret_value()
    if account is None or not hmac.compare_digest(password, configured_password):
        return None
    role, display_name = account
    expires = int(time.time()) + settings.demo_session_minutes * 60
    return LoginResponse(
        access_token=_sign(settings, username.lower(), role, expires),
        role=role,
        username=username.lower(),
        display_name=display_name,
        expires_at=datetime.fromtimestamp(expires, UTC).isoformat().replace("+00:00", "Z"),
    )


def verify_demo_session(settings: Settings, token: str) -> AccessContext | None:
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
        expected_signature = _signature(settings, encoded_payload)
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_decode(encoded_payload))
        username = str(payload["sub"])
        role = str(payload["role"])
        expires = int(payload["exp"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    account = ACCOUNTS.get(username)
    if account is None or account[0] != role or expires <= int(time.time()):
        return None
    return AccessContext(username=username, role=role)


def _sign(settings: Settings, username: str, role: DemoRole, expires: int) -> str:
    payload = json.dumps(
        {"exp": expires, "role": role, "sub": username},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded_payload = _encode(payload)
    return f"{encoded_payload}.{_signature(settings, encoded_payload)}"


def _signature(settings: Settings, encoded_payload: str) -> str:
    secret = settings.internal_api_token.get_secret_value().encode()
    digest = hmac.new(secret, encoded_payload.encode(), hashlib.sha256).digest()
    return _encode(digest)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
