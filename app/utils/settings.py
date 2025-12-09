# app/utils/settings.py
from __future__ import annotations

import os
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- Neo4j ----
    NEO4J_URI: str = Field(default="bolt://localhost:7687")
    NEO4J_USER: str = Field(default="neo4j")
    NEO4J_PASSWORD: str = Field(default="password")
    NEO4J_DATABASE: Optional[str] = Field(
        default=None,
        # accept both NEO4J_DATABASE and neo4j_database from .env
        validation_alias="neo4j_database",
    )

    # ---- LLM / Browser-Use provider + model ----
    BROWSERUSE_LLM_PROVIDER: Optional[str] = Field(
        default=None, validation_alias="browseruse_llm_provider"
    )
    BROWSERUSE_LLM_MODEL: Optional[str] = Field(
        default=None, validation_alias="browseruse_llm_model"
    )

    # ---- API keys ----
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    GOOGLE_API_KEY: Optional[str] = Field(default=None, validation_alias="google_api_key")

    # You can add other optional keys you might use later:
    DEFAULT_CITY: Optional[str] = None
    DEFAULT_STATE: Optional[str] = None
    DEFAULT_ZIP: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # accept unknown keys instead of crashing (prevents future breakage)
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()

# Make sure downstream libraries that read env vars directly see the keys.
# (browser-use reads OPENAI_API_KEY / GOOGLE_API_KEY from the environment)
if settings.OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY

if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY
