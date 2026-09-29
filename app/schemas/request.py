from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    repoUrl: str
    githubToken: str
    userId: str
    jobId: str
