import asyncio
import logging
import time
from typing import List
from app.core.github_client import fetch_repository_files
from app.core.prioritizer import prioritize_files
from app.core.chunker import chunk_files
from app.services.llm_service import LLMService
from app.schemas.response import AnalyzeResponse

logger = logging.getLogger(__name__)


class AnalyzerService:
    def __init__(self):
        self.llm = LLMService()

    async def analyze(self, repo_url: str, github_token: str, job_id: str) -> AnalyzeResponse:
        start_time = time.time()
        logger.info(f"[{job_id}] Starting analysis for repository: {repo_url}")

        # 1. Fetch files from GitHub
        files = fetch_repository_files(repo_url, github_token)
        logger.info(f"[{job_id}] Fetched {len(files)} files")

        if not files:
            raise ValueError(f"No valid text files found in {repo_url} or repository empty")

        # 2. Prioritize files
        ordered_files = prioritize_files(files)

        # 3. Overview section
        file_tree = "\n".join([f[0] for f in ordered_files])
        readme_content = files.get("README.md", files.get("readme.md", ""))
        overview = await self.llm.generate_overview(file_tree, readme_content)

        # 4. Chunk files (top 40 prioritized files)
        chunks = chunk_files(ordered_files[:40])
        sections: List[str] = [overview]
        section_names: List[str] = ["Overview"]

        # Limit concurrency to 5 parallel calls to avoid rate limits
        semaphore = asyncio.Semaphore(5)

        async def process_chunk(chunk_data: dict):
            async with semaphore:
                return await self.llm.document_chunk(
                    chunk_data["filepath"],
                    chunk_data["chunk"],
                    chunk_data["chunk_index"],
                )

        tasks = [process_chunk(c) for c in chunks[:30]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for chunk_data, result in zip(chunks[:30], results):
            if isinstance(result, Exception):
                logger.warning(f"[{job_id}] Chunk failed: {result}")
                continue
            filepath = chunk_data["filepath"]
            if filepath not in section_names:
                section_names.append(filepath)
            sections.append(f"## `{filepath}`\n\n{result}")

        # 5. Assemble Markdown
        repo_name = repo_url.rstrip("/").split("/")[-1]
        header = (
            f"# Documentación Técnica: {repo_name}\n\n"
            f"> Generado automáticamente por **CodeScribe AI** · [Ver Repositorio]({repo_url})\n\n"
            f"---\n\n"
        )
        final_markdown = header + "\n\n---\n\n".join(sections)
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(f"[{job_id}] Analysis finished in {duration_ms}ms")

        return AnalyzeResponse(
            markdown=final_markdown,
            tokensUsed=0,
            durationMs=duration_ms,
            sections=section_names,
        )
