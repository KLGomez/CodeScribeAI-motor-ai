from pydantic import BaseModel, SecretStr


class AnalyzeRequest(BaseModel):
    repoUrl: str
    githubToken: SecretStr = SecretStr("")
    userId: str
    jobId: str
