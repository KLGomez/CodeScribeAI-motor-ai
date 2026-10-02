import os
from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    ai_service_secret: str = ""

    max_file_size_kb: int = 100
    max_files_per_repo: int = 200

    port: int = 8000
    environment: str = "development"

    @model_validator(mode="after")
    def validate_secrets(self):
        if self.environment == "production":
            if not self.ai_service_secret:
                raise ValueError("[ConfigError] AI_SERVICE_SECRET es obligatorio en entorno de producción")
            if not self.gemini_api_key and not os.getenv("GOOGLE_API_KEY"):
                raise ValueError("[ConfigError] GEMINI_API_KEY o GOOGLE_API_KEY es obligatorio en producción")
        elif not self.ai_service_secret:
            self.ai_service_secret = "dev_ai_secret_codescribe_local_only"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
