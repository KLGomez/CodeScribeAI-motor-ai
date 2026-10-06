from typing import List

from pydantic import BaseModel


class AnalyzeResponse(BaseModel):
    markdown: str
    tokensUsed: int
    durationMs: int
    sections: List[str]
    filesAnalyzed: int = 0
    filesTotal: int = 0
    truncated: bool = False
