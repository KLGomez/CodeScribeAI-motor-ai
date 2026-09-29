from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8"
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    ai_service_secret: str = "shared_secret"

    max_file_size_kb: int = 100
    max_files_per_repo: int = 200
    chunk_size: int = 2000
    chunk_overlap: int = 200

    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
