import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analyze, health
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(f"🚀 CodeScribe AI Service starting on port {settings.port} (env: {settings.environment})")
    yield
    logger.info("🛑 CodeScribe AI Service stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CodeScribe AI Service",
        description="Microservicio de análisis de código y generación de documentación con Gemini",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Only add CORS if explicitly configured (by default empty, strictly internal communication)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    app.include_router(health.router, tags=["Health"])
    app.include_router(analyze.router, tags=["Analysis"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    app_settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=app_settings.port, reload=app_settings.debug)
