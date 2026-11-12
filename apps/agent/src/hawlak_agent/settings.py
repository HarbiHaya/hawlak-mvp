from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSettings:
    mode: str
    hawlak_api_base_url: str
    hawlak_internal_api_token: str
    hawlak_control_token: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    livekit_sip_outbound_trunk_id: str
    openai_api_key: str
    openai_base_url: str
    openai_stt_model: str
    openai_classifier_model: str
    openai_llm_model: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    agent_name: str

    @classmethod
    def from_env(cls) -> AgentSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> AgentSettings:
        mode = values.get("HAWLAK_AGENT_MODE", "mock").strip().lower()
        if mode not in {"mock", "live"}:
            raise ValueError("HAWLAK_AGENT_MODE must be mock or live")

        required = [
            "HAWLAK_API_BASE_URL",
            "HAWLAK_INTERNAL_API_TOKEN",
            "HAWLAK_CONTROL_TOKEN",
        ]
        if mode == "live":
            required.extend(
                [
                    "LIVEKIT_URL",
                    "LIVEKIT_API_KEY",
                    "LIVEKIT_API_SECRET",
                    "LIVEKIT_SIP_OUTBOUND_TRUNK_ID",
                    "OPENAI_API_KEY",
                    "OPENAI_BASE_URL",
                    "OPENAI_STT_MODEL",
                    "OPENAI_CLASSIFIER_MODEL",
                    "OPENAI_LLM_MODEL",
                    "ELEVENLABS_API_KEY",
                    "ELEVENLABS_VOICE_ID",
                    "ELEVENLABS_MODEL_ID",
                    "HAWLAK_AGENT_NAME",
                ]
            )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise ValueError(f"missing required settings: {', '.join(missing)}")

        return cls(
            mode=mode,
            hawlak_api_base_url=values.get("HAWLAK_API_BASE_URL", "").rstrip("/"),
            hawlak_internal_api_token=values.get("HAWLAK_INTERNAL_API_TOKEN", ""),
            hawlak_control_token=values.get("HAWLAK_CONTROL_TOKEN", ""),
            livekit_url=values.get("LIVEKIT_URL", ""),
            livekit_api_key=values.get("LIVEKIT_API_KEY", ""),
            livekit_api_secret=values.get("LIVEKIT_API_SECRET", ""),
            livekit_sip_outbound_trunk_id=values.get("LIVEKIT_SIP_OUTBOUND_TRUNK_ID", ""),
            openai_api_key=values.get("OPENAI_API_KEY", ""),
            openai_base_url=values.get("OPENAI_BASE_URL", "").rstrip("/"),
            openai_stt_model=values.get("OPENAI_STT_MODEL", ""),
            openai_classifier_model=values.get("OPENAI_CLASSIFIER_MODEL", ""),
            openai_llm_model=values.get("OPENAI_LLM_MODEL", ""),
            elevenlabs_api_key=values.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=values.get("ELEVENLABS_VOICE_ID", ""),
            elevenlabs_model_id=values.get("ELEVENLABS_MODEL_ID", ""),
            agent_name=values.get("HAWLAK_AGENT_NAME", "hawlak-follow-up"),
        )

    def parse_job_metadata(self, raw_metadata: str) -> str:
        try:
            payload = json.loads(raw_metadata)
        except json.JSONDecodeError as exc:
            raise ValueError("job metadata must be valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"call_plan_id"}:
            raise ValueError("job metadata may contain only call_plan_id")
        call_plan_id = payload["call_plan_id"]
        if not isinstance(call_plan_id, str) or not call_plan_id.strip():
            raise ValueError("call_plan_id is required")
        return call_plan_id
