import hashlib
import hmac
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_db_session
from app.main import app
from app.services.whatsapp_client import WhatsAppClient

SETTINGS_VALUES = {
    "meta_graph_api_version": "v-test",
    "whatsapp_phone_number_id": "phone-id",
    "whatsapp_access_token": "test-token",
    "whatsapp_verify_token": "test-verify-token-long-enough",
    "meta_app_secret": "test-app-secret",
    "whatsapp_test_recipient": "+966500000000",
    "s3_endpoint": "http://127.0.0.1:19000",
    "s3_region": "us-east-1",
    "s3_bucket": "hawlak-mvp",
    "s3_access_key": "hawlak-test",
    "s3_secret_key": "test-secret-long-enough",
    "internal_api_token": "test-internal-api-token-long-enough",
    "demo_login_password": "synthetic-demo-password",
    "dashboard_origin": "http://localhost:5173",
    "database_url": "sqlite:///:memory:",
}


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def plan() -> dict:
    """The synthetic approved plan for the demo case."""
    return json.loads((FIXTURES / "approved-plan.abu-mohammed.json").read_text(encoding="utf-8"))


@pytest.fixture
def settings_values() -> dict[str, str]:
    return dict(SETTINGS_VALUES)


@pytest.fixture
def settings(settings_values) -> Settings:
    return Settings(_env_file=None, **settings_values)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(settings, db_session):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.state.dashboard_origin = settings.dashboard_origin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def internal_auth_headers(settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.internal_api_token.get_secret_value()}"}


@pytest.fixture
def sign(settings):
    """Sign a raw body the way Meta does (HMAC-SHA256 with the app secret)."""

    def _sign(body: bytes, secret: str | None = None) -> str:
        key = (secret or settings.meta_app_secret).encode()
        return "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()

    return _sign


@pytest.fixture
def fake_meta(settings):
    """Build a WhatsAppClient whose HTTP calls get `response`; also return the requests it sent."""

    def build(response: httpx.Response) -> tuple[WhatsAppClient, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return response

        whatsapp = WhatsAppClient(
            settings.meta_graph_api_version,
            settings.whatsapp_phone_number_id,
            settings.whatsapp_access_token,
            transport=httpx.MockTransport(handler),
        )
        return whatsapp, seen

    return build
