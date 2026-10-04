from fastapi.testclient import TestClient

from app.main import app
from app.schemas.request import AnalyzeRequest


def test_secret_masking_in_request_model():
    req = AnalyzeRequest(
        repoUrl="https://github.com/KLGomez/repo",
        githubToken="ghp_super_secret_personal_access_token_12345",
        userId="user-123",
        jobId="job-456",
    )
    # Ensure repr masks the secret
    assert "ghp_super_secret" not in repr(req)
    assert "**********" in repr(req)
    # Ensure raw secret is retrievable via get_secret_value
    assert req.githubToken.get_secret_value() == "ghp_super_secret_personal_access_token_12345"


def test_analyze_forbidden_without_secret():
    client = TestClient(app)
    response = client.post(
        "/analyze",
        json={
            "repoUrl": "https://github.com/KLGomez/repo",
            "githubToken": "token",
            "userId": "user-1",
            "jobId": "job-1",
        },
    )
    assert response.status_code in (403, 422)


def test_analyze_forbidden_with_invalid_secret():
    client = TestClient(app)
    response = client.post(
        "/analyze",
        headers={"X-Internal-Secret": "invalid_unauthorized_secret_99999"},
        json={
            "repoUrl": "https://github.com/KLGomez/repo",
            "githubToken": "token",
            "userId": "user-1",
            "jobId": "job-1",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid internal secret"


def test_cors_does_not_permit_arbitrary_origins():
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={"Origin": "https://attacker.evil.com"},
    )
    assert response.status_code == 200
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "*"
    assert allow_origin != "https://attacker.evil.com"
