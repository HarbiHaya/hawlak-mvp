from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.config import SettingsDep
from app.db import SessionDep
from app.dialects import dialect_options
from app.schemas.voice import (
    ApproveAndSendRequest,
    ApproveAndSendResponse,
    ApproveAudioFirstRequest,
    ApproveAudioFirstResponse,
    AudioFirstScriptPart,
    GenerateAudioFirstResponse,
    GenerateScriptResponse,
    VoiceOptionsResponse,
)
from app.services.audio_first_composer import (
    MockAudioFirstComposer,
    OpenAIAudioFirstProvider,
    ProviderAudioFirstComposer,
)
from app.services.dialect_composer import (
    MockDialectComposer,
    OpenAIResponsesProvider,
    ProviderDialectComposer,
)
from app.services.object_storage import ObjectStorage
from app.services.voice_renderer import (
    build_voice_renderer,
)
from app.services.voice_workflow import (
    VoiceWorkflow,
    VoiceWorkflowConflict,
    VoiceWorkflowNotFound,
)
from app.services.whatsapp_factory import build_whatsapp_client

router = APIRouter()


@router.get("/voice-options", response_model=VoiceOptionsResponse)
def voice_options(settings: SettingsDep):
    return {
        "dialects": dialect_options(),
        "voice": {
            "provider": "elevenlabs",
            "voiceLabel": settings.elevenlabs_voice_label,
            "modelId": settings.elevenlabs_model_id,
            "languageCode": settings.elevenlabs_language_code,
        },
    }


def get_voice_workflow(settings: SettingsDep, session: SessionDep) -> VoiceWorkflow:
    if settings.demo_provider_mode == "live":
        if settings.openai_api_key is None or settings.elevenlabs_api_key is None:
            raise RuntimeError("live providers require OpenAI and ElevenLabs keys")
        composer = ProviderDialectComposer(
            OpenAIResponsesProvider(
                settings.openai_api_key.get_secret_value(), settings.openai_text_model
            )
        )
        audio_first_composer = ProviderAudioFirstComposer(
            OpenAIAudioFirstProvider(
                settings.openai_api_key.get_secret_value(), settings.openai_text_model
            )
        )
    else:
        composer = MockDialectComposer()
        audio_first_composer = MockAudioFirstComposer()
    renderer = build_voice_renderer(settings)
    storage = ObjectStorage(settings)
    whatsapp = build_whatsapp_client(settings, storage)
    return VoiceWorkflow(
        session,
        composer,
        renderer,
        storage,
        whatsapp,
        audio_first_composer=audio_first_composer,
    )


@router.post("/cases/{case_id}/generate-script", response_model=GenerateScriptResponse)
async def generate_script(
    case_id: str,
    workflow: Annotated[VoiceWorkflow, Depends(get_voice_workflow)],
):
    try:
        result = await workflow.generate_script(case_id)
    except VoiceWorkflowNotFound:
        return JSONResponse(status_code=404, content={"error": "case_not_found"})
    except VoiceWorkflowConflict as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    return GenerateScriptResponse(
        artifact_id=result.artifact.id,
        case_id=case_id,
        spoken_text_ar=result.artifact.generated_script_ar or "",
        script_checksum=result.artifact.generated_script_sha256 or "",
        fact_report={"passed": True, "differences": result.differences},
    )


@router.post(
    "/cases/{case_id}/generate-audio-first",
    response_model=GenerateAudioFirstResponse,
)
async def generate_audio_first(
    case_id: str,
    workflow: Annotated[VoiceWorkflow, Depends(get_voice_workflow)],
):
    try:
        result = await workflow.generate_audio_first_scripts(case_id)
    except VoiceWorkflowNotFound:
        return JSONResponse(status_code=404, content={"error": "case_not_found"})
    except VoiceWorkflowConflict as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    return GenerateAudioFirstResponse(
        case_id=case_id,
        approval_checksum=result.approval_checksum,
        scripts=[
            AudioFirstScriptPart(
                kind="session_summary",
                artifact_id=result.session_artifact.id,
                spoken_text_ar=result.session_artifact.generated_script_ar or "",
                script_checksum=result.session_artifact.generated_script_sha256 or "",
            ),
            AudioFirstScriptPart(
                kind="recovery_warning",
                artifact_id=result.recovery_artifact.id,
                spoken_text_ar=result.recovery_artifact.generated_script_ar or "",
                script_checksum=result.recovery_artifact.generated_script_sha256 or "",
            ),
        ],
        fact_report={"passed": True, "differences": result.differences},
    )


@router.post(
    "/cases/{case_id}/approve-and-send",
    response_model=ApproveAndSendResponse,
)
async def approve_and_send(
    case_id: str,
    body: ApproveAndSendRequest,
    workflow: Annotated[VoiceWorkflow, Depends(get_voice_workflow)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    try:
        result = await workflow.approve_and_send(
            case_id=case_id,
            artifact_id=body.artifact_id,
            script_checksum=body.script_checksum,
            approved_by=body.approved_by,
            idempotency_key=idempotency_key,
        )
    except VoiceWorkflowNotFound:
        return JSONResponse(status_code=404, content={"error": "voice_artifact_not_found"})
    except VoiceWorkflowConflict as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    return ApproveAndSendResponse(
        artifact_id=result.artifact.id,
        case_id=case_id,
        script_checksum=result.artifact.approved_script_sha256 or "",
        audio_checksum=result.artifact.audio_checksum or "",
        message_ids=result.message_ids,
    )


@router.post(
    "/cases/{case_id}/approve-audio-first-and-send",
    response_model=ApproveAudioFirstResponse,
)
async def approve_audio_first_and_send(
    case_id: str,
    body: ApproveAudioFirstRequest,
    workflow: Annotated[VoiceWorkflow, Depends(get_voice_workflow)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    try:
        result = await workflow.approve_audio_first_and_send(
            case_id=case_id,
            session_artifact_id=body.session_artifact_id,
            recovery_artifact_id=body.recovery_artifact_id,
            approval_checksum=body.approval_checksum,
            approved_by=body.approved_by,
            idempotency_key=idempotency_key,
        )
    except VoiceWorkflowNotFound:
        return JSONResponse(status_code=404, content={"error": "voice_artifact_not_found"})
    except VoiceWorkflowConflict as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    return ApproveAudioFirstResponse(
        case_id=case_id,
        approval_checksum=result.approval_checksum,
        audio_checksums={
            "sessionSummary": result.session_artifact.audio_checksum or "",
            "recoveryWarning": result.recovery_artifact.audio_checksum or "",
        },
        message_ids=result.message_ids,
    )
