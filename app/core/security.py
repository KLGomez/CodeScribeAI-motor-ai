import secrets
from fastapi import Header, HTTPException, status
from app.config import get_settings


async def verify_internal_secret(
    x_internal_secret: str = Header(..., alias="X-Internal-Secret"),
) -> None:
    """Validates the shared secret between NestJS and this service using constant-time comparison."""
    settings = get_settings()
    if not secrets.compare_digest(x_internal_secret, settings.ai_service_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal secret",
        )
