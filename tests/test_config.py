import pytest

from app.config import Settings


def test_production_fails_without_secret():
    with pytest.raises(ValueError, match="AI_SERVICE_SECRET / INTERNAL_SECRET es obligatorio"):
        Settings(
            environment="production",
            internal_secret="",
            ai_service_secret="",
            gemini_api_key="valid_gemini_api_key_1234567890",
        )


def test_production_fails_with_placeholder_secret():
    with pytest.raises(ValueError, match="AI_SERVICE_SECRET / INTERNAL_SECRET es obligatorio"):
        Settings(
            environment="production",
            internal_secret="shared_secret",
            gemini_api_key="valid_gemini_api_key_1234567890",
        )


def test_production_fails_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY o GOOGLE_API_KEY es obligatorio"):
        Settings(
            environment="production",
            internal_secret="a_very_secure_production_secret_32bytes",
            gemini_api_key="",
        )


def test_production_succeeds_with_valid_credentials():
    settings = Settings(
        environment="production",
        internal_secret="a_very_secure_production_secret_32bytes",
        gemini_api_key="a_valid_production_gemini_api_key",
    )
    assert settings.environment == "production"
    assert settings.internal_secret == "a_very_secure_production_secret_32bytes"
    assert settings.gemini_api_key == "a_valid_production_gemini_api_key"


def test_development_defaults_to_local_secret():
    settings = Settings(
        environment="development",
        internal_secret="",
        ai_service_secret="",
        gemini_api_key="",
    )
    assert settings.environment == "development"
    assert settings.ai_service_secret == "dev_ai_secret_codescribe_local_only"
