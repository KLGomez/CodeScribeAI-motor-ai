import os
from functools import lru_cache
from typing import List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWN_PLACEHOLDERS = {
    "shared_secret",
    "secret",
    "test",
    "change_me",
    "dev_ai_secret_codescribe_local_only",
    "fallback_secret_change_me",
    "your_secret_here",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "production"
    debug: bool = False
    port: int = 8000

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 60

    ai_service_secret: str = ""
    internal_secret: str = ""

    github_fallback_token: str = ""

    # Scope and limit configuration
    max_source_files: int = 20
    max_chars_per_file: int = 6000
    max_bundle_chars: int = 80000
    max_files_per_repo: int = 40
    max_file_size_kb: int = 100

    # Concurrency
    max_concurrent_analyses: int = 3

    # Network & CORS
    cors_origins: Union[List[str], str] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[List[str], str]) -> List[str]:
        if isinstance(value, str):
            if not value.strip():
                return []
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value or []

    @model_validator(mode="after")
    def validate_and_normalize(self) -> "Settings":
        # Synchronize ai_service_secret and internal_secret
        effective_secret = self.internal_secret or self.ai_service_secret or os.getenv("INTERNAL_SECRET", "")
        self.ai_service_secret = effective_secret
        self.internal_secret = effective_secret

        effective_gemini_key = self.gemini_api_key or os.getenv("GOOGLE_API_KEY", "")
        self.gemini_api_key = effective_gemini_key

        env = (self.environment or "").strip().lower()

        if env == "production":
            if not self.ai_service_secret or self.ai_service_secret.lower() in KNOWN_PLACEHOLDERS or len(self.ai_service_secret) < 16:
                raise ValueError(
                    "[ConfigError] AI_SERVICE_SECRET / INTERNAL_SECRET es obligatorio, no puede ser un placeholder conocido y debe tener al menos 16 caracteres en producción"
                )
            if not self.gemini_api_key or self.gemini_api_key.lower() in KNOWN_PLACEHOLDERS:
                raise ValueError(
                    "[ConfigError] GEMINI_API_KEY o GOOGLE_API_KEY es obligatorio y válido en entorno de producción"
                )
        elif env == "development":
            if not self.ai_service_secret:
                self.ai_service_secret = "dev_ai_secret_codescribe_local_only"
                self.internal_secret = "dev_ai_secret_codescribe_local_only"

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
