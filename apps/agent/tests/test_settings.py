import pytest

from hawlak_agent.settings import AgentSettings

LIVE_ENV = {
    "HAWLAK_AGENT_MODE": "live",
    "HAWLAK_API_BASE_URL": "https://api.example.test",
    "HAWLAK_INTERNAL_API_TOKEN": "internal-token",
    "HAWLAK_CONTROL_TOKEN": "control-token",
    "LIVEKIT_URL": "wss://project.livekit.cloud",
    "LIVEKIT_API_KEY": "livekit-key",
    "LIVEKIT_API_SECRET": "livekit-secret",
    "LIVEKIT_SIP_OUTBOUND_TRUNK_ID": "ST_test",
    "OPENAI_API_KEY": "openai-key",
    "OPENAI_BASE_URL": "https://api.openai.example/v1",
    "OPENAI_STT_MODEL": "transcription-model",
    "OPENAI_CLASSIFIER_MODEL": "classifier-model",
    "OPENAI_LLM_MODEL": "conversation-model",
    "ELEVENLABS_API_KEY": "eleven-key",
    "ELEVENLABS_VOICE_ID": "voice-id",
    "ELEVENLABS_MODEL_ID": "eleven_multilingual_v2",
    "HAWLAK_AGENT_NAME": "hawlak-follow-up",
}


def test_live_settings_require_every_provider_value() -> None:
    settings = AgentSettings.from_mapping(LIVE_ENV)

    assert settings.livekit_sip_outbound_trunk_id == "ST_test"
    assert settings.openai_base_url == "https://api.openai.example/v1"
    assert settings.openai_stt_model == "transcription-model"
    assert settings.agent_name == "hawlak-follow-up"


def test_live_settings_fail_closed_when_a_secret_is_missing() -> None:
    incomplete = LIVE_ENV | {"ELEVENLABS_API_KEY": ""}

    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        AgentSettings.from_mapping(incomplete)


def test_job_metadata_accepts_only_call_plan_id() -> None:
    settings = AgentSettings.from_mapping(LIVE_ENV)

    assert settings.parse_job_metadata('{"call_plan_id":"plan-synthetic-001"}') == (
        "plan-synthetic-001"
    )

    with pytest.raises(ValueError, match="only call_plan_id"):
        settings.parse_job_metadata(
            '{"call_plan_id":"plan-synthetic-001","phone_number":"+966500000000"}'
        )
