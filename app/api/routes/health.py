import os
from fastapi import APIRouter
from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health():
    settings = get_settings()
    has_gemini_key = bool(settings.gemini_api_key or os.getenv("GOOGLE_API_KEY"))

    return {
        "status": "ok" if has_gemini_key else "degraded",
        "service": "documentador-ai-service",
        "model": settings.gemini_model,
        "geminiConfigured": has_gemini_key,
        "environment": settings.environment,
    }
