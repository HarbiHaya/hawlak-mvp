import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.dialects import get_dialect_profile
from app.schemas.voice import ComposedAudioFirstScripts, DialectComposeRequest
from app.services.clinical_fact_guard import ensure_clinical_facts_match
from app.services.dialect_composer import (
    KNOWN_SYNTHETIC_CASE_ID,
    KNOWN_SYNTHETIC_PLAN_ID,
    KNOWN_SYNTHETIC_SOURCE_HASH,
    DialectComposerError,
    UnsafeDialectOutputError,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "audio-first-v1.txt"


class AudioFirstComposer(Protocol):
    async def compose(self, request: DialectComposeRequest) -> ComposedAudioFirstScripts: ...


class AudioFirstProvider(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any] | ComposedAudioFirstScripts: ...


class OpenAIAudioFirstProvider:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(self, *, prompt: str, input_data: dict[str, Any]):
        response = await self._client.responses.parse(
            model=self._model,
            instructions=prompt,
            input=json.dumps(input_data, ensure_ascii=False),
            text_format=ComposedAudioFirstScripts,
            store=False,
        )
        if response.output_parsed is None:
            raise DialectComposerError("OpenAI returned no audio-first output")
        return response.output_parsed


class ProviderAudioFirstComposer:
    def __init__(self, provider: AudioFirstProvider, *, prompt_path: Path = PROMPT_PATH) -> None:
        self._provider = provider
        self._prompt_path = prompt_path

    async def compose(self, request: DialectComposeRequest) -> ComposedAudioFirstScripts:
        profile = get_dialect_profile(request.dialect_code)
        try:
            raw = await self._provider.generate(
                prompt=self._prompt_path.read_text(encoding="utf-8"),
                input_data={
                    "patientAlias": request.patient_alias,
                    "dialectCode": request.dialect_code,
                    "dialectProfile": profile.as_prompt_input(),
                    "approvedClinicalFacts": request.clinical_facts.model_dump(
                        by_alias=True, mode="json"
                    ),
                },
            )
        except Exception as exc:
            raise DialectComposerError("audio-first provider request failed") from exc
        try:
            result = (
                raw
                if isinstance(raw, ComposedAudioFirstScripts)
                else ComposedAudioFirstScripts.model_validate(raw)
            )
        except ValidationError as exc:
            raise DialectComposerError("audio-first provider returned invalid output") from exc
        _validate(request, result)
        return result


class MockAudioFirstComposer:
    async def compose(self, request: DialectComposeRequest) -> ComposedAudioFirstScripts:
        if not _known_fixture(request):
            raise DialectComposerError("mock composer accepts only the known synthetic fixture")
        medicines = [
            f"{item.name} {item.strength}: {item.dose}، {item.frequency}، {item.timing}."
            for item in request.clinical_facts.new_medicines
        ]
        session = " ".join(
            [
                f"يا {request.patient_alias}، هذا تسجيل صوتي من خطة خروجك المعتمدة.",
                "في جلسة الخروج راجعنا أدويتك:",
                *medicines,
                "ووقفنا " + "، ".join(request.clinical_facts.stopped_medicines) + ".",
                "الحين أرسل لنا صور علب الأدوية، علبة علبة، وكل صورة تكون واضحة.",
            ]
        )
        recovery = " ".join(
            [
                "وبالنسبة للتعافي:",
                *request.clinical_facts.activity_instructions,
                *request.clinical_facts.diet_instructions,
                "انتبه للعلامات التالية: " + "، ".join(request.clinical_facts.red_flags) + ".",
                f"إذا صار شيء منها، اتصل بالطوارئ على {request.clinical_facts.emergency_number}.",
            ]
        )
        result = ComposedAudioFirstScripts(
            patient_alias=request.patient_alias,
            dialect_code=request.dialect_code,
            session_summary_ar=session,
            recovery_warning_ar=recovery,
            copied_facts=request.clinical_facts.model_copy(deep=True),
            prohibited_content_detected=False,
            safety_notes=["deterministic synthetic demo output"],
        )
        _validate(request, result)
        return result


def _validate(request: DialectComposeRequest, result: ComposedAudioFirstScripts) -> None:
    if result.patient_alias != request.patient_alias or result.dialect_code != request.dialect_code:
        raise UnsafeDialectOutputError("audio-first output changed case identity")
    if result.prohibited_content_detected:
        raise UnsafeDialectOutputError("audio-first output reported prohibited content")
    try:
        ensure_clinical_facts_match(request.clinical_facts, result.copied_facts)
    except ValueError as exc:
        raise UnsafeDialectOutputError(
            "audio-first output changed approved clinical facts"
        ) from exc


def _known_fixture(request: DialectComposeRequest) -> bool:
    return (
        request.synthetic
        and request.case_id == KNOWN_SYNTHETIC_CASE_ID
        and request.plan_id == KNOWN_SYNTHETIC_PLAN_ID
        and request.source_hash == KNOWN_SYNTHETIC_SOURCE_HASH
    )
