import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.exceptions import (
    AiTimeoutException,
    GitHubRateLimitException,
    RepoEmptyException,
    RepoNotFoundException,
)
from app.core.github_client import RepositoryFilesResult
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_headers():
    settings = get_settings()
    secret = settings.ai_service_secret or "dev_ai_secret_codescribe_local_only"
    return {"X-Internal-Secret": secret}


def test_successful_analysis_flow_with_git_tree_limits(client, valid_headers):
    # Mocking files exceeding max_source_files (25 files total, 20 analyzed)
    mock_files = {f"src/file_{i}.ts": f"console.log('file {i}');" for i in range(20)}
    mock_files_result = RepositoryFilesResult(
        files=mock_files,
        files_analyzed=20,
        files_total=25,
        truncated=True,
    )

    with patch(
        "app.services.analyzer.fetch_repository_files",
        return_value=mock_files_result,
    ), patch(
        "app.services.analyzer.LLMService.generate_full_architecture_docs",
        new_callable=AsyncMock,
        return_value=("# Documentación Técnica: react\n\n## 1. Propósito\nExplicación...", 150),
    ):
        response = client.post(
            "/analyze",
            headers=valid_headers,
            json={
                "repoUrl": "https://github.com/facebook/react",
                "githubToken": "ghp_mock_token_12345",
                "userId": "user-1",
                "jobId": "job-1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filesAnalyzed"] == 20
        assert data["filesTotal"] == 25
        assert data["truncated"] is True
        assert data["tokensUsed"] == 150
        assert "## 1. Propósito" in data["markdown"]
        assert "1. Propósito" in data["sections"]


def test_repo_empty_returns_422(client, valid_headers):
    with patch(
        "app.services.analyzer.fetch_repository_files",
        side_effect=RepoEmptyException("Repositorio vacío"),
    ):
        response = client.post(
            "/analyze",
            headers=valid_headers,
            json={
                "repoUrl": "https://github.com/KLGomez/empty-repo",
                "githubToken": "token",
                "userId": "user-1",
                "jobId": "job-1",
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["code"] == "REPO_EMPTY"


def test_repo_not_found_returns_404(client, valid_headers):
    with patch(
        "app.services.analyzer.fetch_repository_files",
        side_effect=RepoNotFoundException("Repositorio no encontrado"),
    ):
        response = client.post(
            "/analyze",
            headers=valid_headers,
            json={
                "repoUrl": "https://github.com/KLGomez/non-existent-repo",
                "githubToken": "token",
                "userId": "user-1",
                "jobId": "job-1",
            },
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["code"] == "REPO_NOT_FOUND"


def test_github_rate_limit_returns_429(client, valid_headers):
    with patch(
        "app.services.analyzer.fetch_repository_files",
        side_effect=GitHubRateLimitException("Rate limit excedido"),
    ):
        response = client.post(
            "/analyze",
            headers=valid_headers,
            json={
                "repoUrl": "https://github.com/KLGomez/some-repo",
                "githubToken": "token",
                "userId": "user-1",
                "jobId": "job-1",
            },
        )
        assert response.status_code == 429
        data = response.json()
        assert data["detail"]["code"] == "GITHUB_RATE_LIMIT"


def test_gemini_timeout_returns_504(client, valid_headers):
    mock_files_result = RepositoryFilesResult(
        files={"src/main.ts": "console.log(1);"},
        files_analyzed=1,
        files_total=1,
        truncated=False,
    )

    with patch(
        "app.services.analyzer.fetch_repository_files",
        return_value=mock_files_result,
    ), patch(
        "app.services.analyzer.LLMService.generate_full_architecture_docs",
        side_effect=AiTimeoutException("Timeout de 60s excedido"),
    ):
        response = client.post(
            "/analyze",
            headers=valid_headers,
            json={
                "repoUrl": "https://github.com/KLGomez/slow-repo",
                "githubToken": "token",
                "userId": "user-1",
                "jobId": "job-1",
            },
        )
        assert response.status_code == 504
        data = response.json()
        assert data["detail"]["code"] == "AI_TIMEOUT"


def test_concurrency_saturation_returns_503(client, valid_headers):
    # Mock semaphore with 0 permits available
    mock_sem = MagicMock()
    mock_sem.acquire = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("app.api.routes.analyze.get_semaphore", return_value=mock_sem):
        response = client.post(
            "/analyze",
            headers=valid_headers,
            json={
                "repoUrl": "https://github.com/KLGomez/busy-repo",
                "githubToken": "token",
                "userId": "user-1",
                "jobId": "job-1",
            },
        )
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["code"] == "AI_BUSY"
        assert response.headers.get("retry-after") == "30"
