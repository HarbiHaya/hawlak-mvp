from types import SimpleNamespace

import pytest

from app.schemas.voice import ApprovedVoiceScript
from app.services.voice_renderer import (
    ElevenLabsVoiceProvider,
    MockVoiceRenderer,
    ProviderVoiceRenderer,
    VoiceRendererError,
    _validate_ogg_opus,
    checksum_script,
)


def approved_script(*, text="نص معتمد", synthetic=True, checksum=None):
    return ApprovedVoiceScript(
        artifact_id="artifact-1",
        case_id="case_01",
        synthetic=synthetic,
        spoken_text_ar=text,
        script_checksum=checksum or checksum_script(text),
        approved=True,
        approved_by="reviewer-1",
    )


@pytest.mark.anyio
async def test_mock_renderer_binds_audio_to_exact_approved_checksum():
    result = await MockVoiceRenderer().render(approved_script())
    assert result.audio.startswith(b"OggS")
    assert result.script_checksum == checksum_script("نص معتمد")

    with pytest.raises(VoiceRendererError):
        await MockVoiceRenderer().render(approved_script(checksum="sha256:" + "0" * 64))
    with pytest.raises(VoiceRendererError):
        await MockVoiceRenderer().render(approved_script(synthetic=False))


@pytest.mark.anyio
async def test_provider_receives_exact_stored_text():
    seen = []

    class Provider:
        async def synthesize(self, **kwargs):
            seen.append(kwargs)
            return b"OggS-real-audio"

    renderer = ProviderVoiceRenderer(
        Provider(),
        model_id="model",
        voice_id="voice",
        output_format="opus",
        language_code="ar",
        stability=0.35,
        similarity_boost=0.8,
        validate_audio=lambda audio: None,
    )
    await renderer.render(approved_script(text="النص نفسه"))
    assert seen[0]["text"] == "النص نفسه"
    assert seen[0]["language_code"] == "ar"
    assert seen[0]["stability"] == 0.35
    assert seen[0]["similarity_boost"] == 0.8


@pytest.mark.anyio
async def test_elevenlabs_sdk_adapter_collects_audio_chunks():
    seen = []

    class TextToSpeech:
        def convert(self, voice_id, **kwargs):
            seen.append((voice_id, kwargs))

            async def chunks():
                yield b"OggS"
                yield b"-audio"

            return chunks()

    class Client:
        text_to_speech = TextToSpeech()

    provider = ElevenLabsVoiceProvider("not-used", client=Client())
    result = await provider.synthesize(
        text="النص المعتمد",
        model_id="eleven_multilingual_v2",
        voice_id="voice-1",
        output_format="opus_48000_64",
        language_code="ar",
        stability=0.35,
        similarity_boost=0.8,
    )

    assert result == b"OggS-audio"
    assert seen[0][0] == "voice-1"
    kwargs = seen[0][1]
    assert kwargs["text"] == "النص المعتمد"
    assert kwargs["model_id"] == "eleven_multilingual_v2"
    assert kwargs["output_format"] == "opus_48000_64"
    assert kwargs["language_code"] == "ar"
    assert kwargs["voice_settings"].stability == 0.35
    assert kwargs["voice_settings"].similarity_boost == 0.8
    assert kwargs["voice_settings"].style is None
    assert kwargs["voice_settings"].speed is None


def test_live_audio_validation_requires_an_opus_stream(monkeypatch):
    monkeypatch.setattr(
        "app.services.voice_renderer.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="opus\n"),
    )
    _validate_ogg_opus(b"OggS-provider-audio")

    monkeypatch.setattr(
        "app.services.voice_renderer.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="vorbis\n"),
    )
    with pytest.raises(VoiceRendererError, match="OGG/Opus"):
        _validate_ogg_opus(b"OggS-wrong-codec")
