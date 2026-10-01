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


@router.delete("/cleanup/{target_id}")
async def cleanup_temporary_files(
    target_id: str,
    _: None = Depends(verify_internal_secret),
):
    """
    Limpia archivos temporales, clones o directorios de caché asociados
    al análisis de un repositorio o job eliminado en la base de datos.
    """
    logger.info(f"Received request to clean temporary resources for target {target_id}")
    import shutil
    import tempfile
    from pathlib import Path

    temp_base = Path(tempfile.gettempdir())
    candidates = [
        temp_base / f"codescribe_{target_id}",
        temp_base / target_id,
        temp_base / f"repo_{target_id}",
    ]

    cleaned_paths = []
    for candidate in candidates:
        if candidate.exists():
            try:
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                else:
                    candidate.unlink(missing_ok=True)
                cleaned_paths.append(str(candidate))
                logger.info(f"Cleaned up temporary path: {candidate}")
            except Exception as e:
                logger.warning(f"Failed to delete {candidate}: {e}")

    return {
        "success": True,
        "targetId": target_id,
        "message": "Temporary resources cleaned successfully",
        "cleanedPaths": cleaned_paths,
    }
