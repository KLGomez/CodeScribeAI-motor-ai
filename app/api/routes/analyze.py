import logging
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services.analyzer import AnalyzerService
from app.core.security import verify_internal_secret

logger = logging.getLogger(__name__)
router = APIRouter()

_analyzer = AnalyzerService()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repository(
    request: AnalyzeRequest,
    _: None = Depends(verify_internal_secret),
) -> AnalyzeResponse:
    logger.info(f"Received analysis request for job {request.jobId} -> {request.repoUrl}")
    try:
        return await _analyzer.analyze(
            repo_url=request.repoUrl,
            github_token=request.githubToken,
            job_id=request.jobId,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.error(f"Error processing job {request.jobId}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(exc)}",
        )
