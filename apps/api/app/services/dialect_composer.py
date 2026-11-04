import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.dialects import get_dialect_profile
from app.schemas.voice import ComposedVoiceScript, DialectComposeRequest
from app.services.clinical_fact_guard import ensure_clinical_facts_match

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "dialect-v2.txt"
KNOWN_SYNTHETIC_CASE_ID = "case_01"
KNOWN_SYNTHETIC_PLAN_ID = "plan_01"
KNOWN_SYNTHETIC_SOURCE_HASH = (
    "sha256:09576e8aee7dfe40e8bb7165eed814a837d5b9d226f04b8ade37db395c93e66a"
)


class DialectComposerError(RuntimeError):
    """The dialect provider failed or returned an unusable response."""


class UnsafeDialectOutputError(DialectComposerError):
    """The composed response failed a deterministic safety boundary."""


class DialectComposer(Protocol):
    async def compose(self, request: DialectComposeRequest) -> ComposedVoiceScript: ...


class StructuredDialectProvider(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        input_data: dict[str, Any],
        response_schema: dict[str, Any],
    ) -> dict[str, Any] | ComposedVoiceScript: ...


class OpenAIResponsesProvider:
    """Official Python SDK adapter using Responses API Structured Outputs."""

    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(
        self,
        *,
        prompt: str,
        input_data: dict[str, Any],
        response_schema: dict[str, Any],
    ) -> ComposedVoiceScript:
        del response_schema  # The SDK derives the strict schema from the Pydantic model.
        response = await self._client.responses.parse(
            model=self._model,
            instructions=prompt,
            input=json.dumps(input_data, ensure_ascii=False),
            text_format=ComposedVoiceScript,
            store=False,
        )
        if response.output_parsed is None:
            raise DialectComposerError("OpenAI returned no structured dialect output")
        return response.output_parsed


class ProviderDialectComposer:
    """Provider-neutral adapter that applies all local checks before returning."""

    def __init__(
        self,
        provider: StructuredDialectProvider,
        *,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        self._provider = provider
        self._prompt_path = prompt_path

    async def compose(self, request: DialectComposeRequest) -> ComposedVoiceScript:
        dialect_profile = get_dialect_profile(request.dialect_code)
        try:
            raw = await self._provider.generate(
                prompt=self._prompt_path.read_text(encoding="utf-8"),
                input_data={
                    "patientAlias": request.patient_alias,
                    "dialectCode": request.dialect_code,
                    "dialectProfile": dialect_profile.as_prompt_input(),
                    "approvedClinicalFacts": request.clinical_facts.model_dump(
                        by_alias=True, mode="json"
                    ),
                },
                response_schema=ComposedVoiceScript.model_json_schema(by_alias=True),
            )
        except Exception as exc:
            raise DialectComposerError("dialect provider request failed") from exc

        try:
            result = (
                raw
                if isinstance(raw, ComposedVoiceScript)
                else ComposedVoiceScript.model_validate(raw)
            )
        except ValidationError as exc:
            raise DialectComposerError("dialect provider returned an invalid response") from exc

        _validate_output(request, result)
        return result


class MockDialectComposer:
    """Deterministic fallback restricted to the repository's synthetic fixture."""

    async def compose(self, request: DialectComposeRequest) -> ComposedVoiceScript:
        if not _is_known_synthetic_fixture(request):
            raise DialectComposerError("mock composer accepts only the known synthetic fixture")

        medicine_lines = [
            f"{medicine.name} {medicine.strength}: {medicine.dose}, "
            f"{medicine.frequency}, {medicine.timing}."
            for medicine in request.clinical_facts.new_medicines
        ]
        spoken_text = " ".join(
            [
                f"يا {request.patient_alias}، هذه خطة الخروج التجريبية المعتمدة.",
                *medicine_lines,
                *request.clinical_facts.activity_instructions,
                *request.clinical_facts.diet_instructions,
                "الأدوية الموقوفة: " + "، ".join(request.clinical_facts.stopped_medicines) + ".",
                "علامات تستدعي الانتباه: " + "، ".join(request.clinical_facts.red_flags) + ".",
                f"للطوارئ اتصل على {request.clinical_facts.emergency_number}.",
            ]
        )
        result = ComposedVoiceScript(
            patient_alias=request.patient_alias,
            dialect_code=request.dialect_code,
            spoken_text_ar=spoken_text,
            copied_facts=request.clinical_facts.model_copy(deep=True),
            prohibited_content_detected=False,
            safety_notes=["deterministic synthetic demo output"],
        )
        _validate_output(request, result)
        return result


def _validate_output(
    request: DialectComposeRequest,
    result: ComposedVoiceScript,
) -> None:
    if result.patient_alias != request.patient_alias or result.dialect_code != request.dialect_code:
        raise UnsafeDialectOutputError("dialect output changed case identity")
    if result.prohibited_content_detected:
        raise UnsafeDialectOutputError("dialect output reported prohibited content")
    try:
        ensure_clinical_facts_match(request.clinical_facts, result.copied_facts)
    except ValueError as exc:
        raise UnsafeDialectOutputError("dialect output changed approved clinical facts") from exc


def _is_known_synthetic_fixture(request: DialectComposeRequest) -> bool:
    return (
        request.synthetic
        and request.case_id == KNOWN_SYNTHETIC_CASE_ID
        and request.plan_id == KNOWN_SYNTHETIC_PLAN_ID
        and request.source_hash == KNOWN_SYNTHETIC_SOURCE_HASH
    )
