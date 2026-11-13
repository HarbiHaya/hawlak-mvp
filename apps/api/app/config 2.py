from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Run from apps/api: ../../.env is the repo-root .env from the README; ./.env overrides it.
    # .env.example also lists keys for later milestones (OpenAI, ElevenLabs, S3): ignore them.
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    meta_graph_api_version: str = Field(min_length=1)
    whatsapp_phone_number_id: str = Field(min_length=1)
    whatsapp_access_token: str = Field(min_length=1)
    whatsapp_verify_token: str = Field(min_length=16)
    meta_app_secret: str = Field(min_length=1)
    whatsapp_test_recipient: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
