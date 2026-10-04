import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.core.exceptions import ServiceException
from app.core.security import verify_internal_secret
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services.analyzer import AnalyzerService

logger = logging.getLogger(__name__)
router = APIRouter()

_analyzer = AnalyzerService()
_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        settings = get_settings()
        _semaphore = asyncio.Semaphore(settings.max_concurrent_analyses)
    return _semaphore


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repository(
    request: AnalyzeRequest,
    _: None = Depends(verify_internal_secret),
) -> AnalyzeResponse:
    # Notice: request.githubToken is SecretStr, repr masks it as **********
    logger.info(f"Received analysis request for job {request.jobId} -> {request.repoUrl}")

    sem = get_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning(f"Concurrency limit reached. Rejecting job {request.jobId}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AI_BUSY",
                "message": "El motor está al máximo de su capacidad. Reintenta en unos instantes.",
            },
            headers={"Retry-After": "30"},
        )

    try:
        return await _analyzer.analyze(
            repo_url=request.repoUrl,
            github_token=request.githubToken.get_secret_value(),
            job_id=request.jobId,
        )
    except ServiceException as se:
        logger.warning(f"Service exception for job {request.jobId} [{se.code}]: {se.message}")
        raise HTTPException(
            status_code=se.status_code,
            detail={"code": se.code, "message": se.message},
        )
    except ValueError as ve:
        logger.warning(f"Invalid request for job {request.jobId}: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REQUEST", "message": str(ve)},
        )
    except Exception as exc:
        logger.error(f"Unexpected error processing job {request.jobId}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AI_UNAVAILABLE",
                "message": "Error interno durante la generación de documentación.",
            },
        )
    finally:
        sem.release()
