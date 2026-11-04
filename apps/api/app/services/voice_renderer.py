import subprocess
import tempfile
from collections.abc import Callable
from hashlib import sha256
from typing import Any, Protocol

from app.config import Settings
from app.schemas.voice import ApprovedVoiceScript, RenderedVoiceArtifact


class VoiceRendererError(RuntimeError):
    """Voice generation failed without exposing provider response details."""


class VoiceRenderer(Protocol):
    async def render(self, script: ApprovedVoiceScript) -> RenderedVoiceArtifact: ...


class VoiceProvider(Protocol):
    async def synthesize(
        self,
        *,
        text: str,
        model_id: str,
        voice_id: str,
        output_format: str,
        language_code: str,
        stability: float,
        similarity_boost: float,
    ) -> bytes: ...


class ElevenLabsVoiceProvider:
    """Official ElevenLabs async SDK adapter."""

    def __init__(self, api_key: str, *, client: Any | None = None) -> None:
        if client is None:
            from elevenlabs.client import AsyncElevenLabs

            client = AsyncElevenLabs(api_key=api_key)
        self._client = client

    async def synthesize(
        self,
        *,
        text: str,
        model_id: str,
        voice_id: str,
        output_format: str,
        language_code: str,
        stability: float,
        similarity_boost: float,
    ) -> bytes:
        from elevenlabs import VoiceSettings

        chunks = self._client.text_to_speech.convert(
            voice_id,
            text=text,
            model_id=model_id,
            output_format=output_format,
            language_code=language_code,
            voice_settings=VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
            ),
        )
        return b"".join([chunk async for chunk in chunks])


class ProviderVoiceRenderer:
    def __init__(
        self,
        provider: VoiceProvider,
        *,
        model_id: str,
        voice_id: str,
        output_format: str,
        language_code: str,
        stability: float,
        similarity_boost: float,
        validate_audio: Callable[[bytes], None] | None = None,
    ) -> None:
        self._provider = provider
        self._model_id = model_id
        self._voice_id = voice_id
        self._output_format = output_format
        self._language_code = language_code
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._validate_audio = validate_audio or _validate_ogg_opus

    async def render(self, script: ApprovedVoiceScript) -> RenderedVoiceArtifact:
        _verify_script_checksum(script)
        try:
            audio = await self._provider.synthesize(
                text=script.spoken_text_ar,
                model_id=self._model_id,
                voice_id=self._voice_id,
                output_format=self._output_format,
                language_code=self._language_code,
                stability=self._stability,
                similarity_boost=self._similarity_boost,
            )
        except Exception as exc:
            raise VoiceRendererError("voice provider request failed") from exc
        self._validate_audio(audio)
        return _artifact(script, audio, self._model_id, self._voice_id, self._output_format)


class MockVoiceRenderer:
    """Keyless renderer restricted to explicitly synthetic approved scripts."""

    async def render(self, script: ApprovedVoiceScript) -> RenderedVoiceArtifact:
        if not script.synthetic:
            raise VoiceRendererError("mock renderer accepts only synthetic scripts")
        _verify_script_checksum(script)
        audio = b"OggS\x00HAWLAK-SYNTHETIC-DEMO"
        return _artifact(script, audio, "mock-model", "mock-voice", "ogg-opus-mock")


def build_voice_renderer(settings: Settings) -> VoiceRenderer:
    if settings.demo_provider_mode == "live":
        if settings.elevenlabs_api_key is None:
            raise RuntimeError("live voice rendering requires an ElevenLabs key")
        return ProviderVoiceRenderer(
            ElevenLabsVoiceProvider(settings.elevenlabs_api_key.get_secret_value()),
            model_id=settings.elevenlabs_model_id,
            voice_id=settings.elevenlabs_voice_id,
            output_format=settings.elevenlabs_output_format,
            language_code=settings.elevenlabs_language_code,
            stability=settings.elevenlabs_stability,
            similarity_boost=settings.elevenlabs_similarity_boost,
        )
    return MockVoiceRenderer()


def checksum_script(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def _verify_script_checksum(script: ApprovedVoiceScript) -> None:
    if checksum_script(script.spoken_text_ar) != script.script_checksum:
        raise VoiceRendererError("approved script checksum does not match its text")


def _validate_ogg_container(audio: bytes) -> None:
    if not audio or not audio.startswith(b"OggS"):
        raise VoiceRendererError("voice provider did not return an OGG container")


def _validate_ogg_opus(audio: bytes) -> None:
    _validate_ogg_container(audio)
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg") as temporary:
            temporary.write(audio)
            temporary.flush()
            inspected = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=nokey=1:noprint_wrappers=1",
                    temporary.name,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise VoiceRendererError("ffprobe could not validate provider audio") from exc
    if inspected.returncode != 0 or inspected.stdout.strip() != "opus":
        raise VoiceRendererError("voice provider did not return OGG/Opus audio")


def _artifact(
    script: ApprovedVoiceScript,
    audio: bytes,
    model_id: str,
    voice_id: str,
    output_format: str,
) -> RenderedVoiceArtifact:
    return RenderedVoiceArtifact(
        source_artifact_id=script.artifact_id,
        script_checksum=script.script_checksum,
        audio=audio,
        audio_checksum="sha256:" + sha256(audio).hexdigest(),
        model_id=model_id,
        voice_id=voice_id,
        output_format=output_format,
    )
