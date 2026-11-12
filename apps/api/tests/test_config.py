import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app


def test_accepts_a_complete_valid_configuration(settings_values):
    settings = Settings(_env_file=None, **settings_values)

    assert settings.whatsapp_test_recipient == "+966500000000"
    assert settings.s3_endpoint == "http://127.0.0.1:19000"
    assert settings.s3_bucket == "hawlak-mvp"
    assert settings.internal_api_token.get_secret_value() == "test-internal-api-token-long-enough"
    assert settings.dashboard_origin == "http://localhost:5173"
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.openai_text_model == "gpt-6-astra"
    assert settings.elevenlabs_model_id == "eleven_v4"
    assert settings.elevenlabs_language_code == "ar"
    assert settings.elevenlabs_stability == 0.35
    assert settings.elevenlabs_similarity_boost == 0.8


def test_accepts_an_https_dashboard_origin_for_the_hosted_demo(settings_values):
    settings = Settings(
        _env_file=None,
        **{**settings_values, "dashboard_origin": "https://demo.hawlak.example"},
    )

    assert settings.dashboard_origin == "https://demo.hawlak.example"


def test_twilio_provider_requires_its_sandbox_credentials(settings_values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings_values, "whatsapp_provider": "twilio"})

    settings = Settings(
        _env_file=None,
        **{
            **settings_values,
            "whatsapp_provider": "twilio",
            "public_base_url": "https://hawlak-tunnel.example",
            "twilio_account_sid": "AC" + "1" * 32,
            "twilio_auth_token": "twilio-test-auth-token-long-enough",
            "twilio_whatsapp_from": "+14155238886",
        },
    )

    assert settings.whatsapp_provider == "twilio"
    assert settings.twilio_whatsapp_from == "+14155238886"


def test_twilio_provider_does_not_require_unused_meta_credentials(settings_values):
    twilio_values = {
        key: value
        for key, value in settings_values.items()
        if key
        not in {
            "meta_graph_api_version",
            "whatsapp_phone_number_id",
            "whatsapp_access_token",
            "whatsapp_verify_token",
            "meta_app_secret",
            "whatsapp_test_recipient",
        }
    }

    settings = Settings(
        _env_file=None,
        **{
            **twilio_values,
            "whatsapp_provider": "twilio",
            "public_base_url": "https://hawlak.example",
            "twilio_account_sid": "AC" + "1" * 32,
            "twilio_auth_token": "twilio-test-auth-token-long-enough",
        },
    )

    assert settings.whatsapp_provider == "twilio"
    assert settings.whatsapp_test_recipient is None


def test_meta_provider_requires_only_its_own_credentials(settings_values):
    for field in (
        "meta_graph_api_version",
        "whatsapp_phone_number_id",
        "whatsapp_access_token",
        "whatsapp_verify_token",
        "meta_app_secret",
    ):
        values = dict(settings_values)
        values.pop(field)

        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("whatsapp_verify_token", "too-short"),
        ("whatsapp_test_recipient", "0500000000"),
        ("whatsapp_test_recipient", "+9665XXXXXXXX"),
        ("meta_app_secret", ""),
        ("whatsapp_access_token", ""),
        ("whatsapp_phone_number_id", ""),
        ("meta_graph_api_version", ""),
        ("s3_endpoint", "not-a-url"),
        ("s3_bucket", "Invalid Bucket Name"),
        ("s3_access_key", ""),
        ("s3_secret_key", "short"),
        ("internal_api_token", "too-short"),
        ("dashboard_origin", "http://127.0.0.1:5173"),
        ("dashboard_origin", "https://demo.hawlak.example/path"),
        ("dashboard_origin", "http://localhost:5173/path"),
        ("dashboard_origin", "http://localhost:70000"),
        ("database_url", "mysql://localhost/hawlak"),
        ("elevenlabs_stability", 1.1),
        ("elevenlabs_similarity_boost", -0.1),
    ],
)
def test_rejects_an_invalid_value(settings_values, field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings_values, field: value})


@pytest.mark.parametrize("field", ["internal_api_token", "dashboard_origin", "database_url"])
def test_rejects_a_missing_internal_boundary_setting(settings_values, field):
    values = dict(settings_values)
    values.pop(field)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_reads_storage_keys_and_ignores_unimplemented_milestones(tmp_path, settings_values):
    lines = [f"{key.upper()}={value}" for key, value in settings_values.items()]
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join([*lines, "OPENAI_API_KEY=replace_me"]))

    settings = Settings(_env_file=env_file)

    assert settings.meta_app_secret == "test-app-secret"
    assert settings.s3_bucket == "hawlak-mvp"


def test_startup_fails_fast_when_the_configuration_is_invalid(monkeypatch, settings_values):
    for key, value in {**settings_values, "whatsapp_verify_token": "too-short"}.items():
        monkeypatch.setenv(key.upper(), value)
    get_settings.cache_clear()

    with pytest.raises(ValidationError), TestClient(app):
        pass

    get_settings.cache_clear()
