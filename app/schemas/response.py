from pydantic import BaseModel
from typing import List


class AnalyzeResponse(BaseModel):
    markdown: str
    tokensUsed: int
    durationMs: int
    sections: List[str]
