"""Servicio de orquestación de análisis arquitectónico usando LangGraph y LCEL (M-11, M-12)."""

import asyncio
import logging
import time

from pydantic import SecretStr

from app.config import get_settings
from app.core.exceptions import RepoEmptyException
from app.core.github_client import fetch_repository_files
from app.core.prioritizer import prioritize_files
from app.graph.builder import build_analysis_graph
from app.schemas.response import AnalyzeResponse
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

MANIFEST_NAMES = {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml"}
README_NAMES = {"readme.md", "readme.rst", "readme.txt"}


class AnalyzerService:
    def __init__(self, llm_service: LLMService | None = None):
        self.llm = llm_service or LLMService()
        self.graph = build_analysis_graph(llm_service=self.llm)

    async def analyze(self, repo_url: str, github_token: str, job_id: str) -> AnalyzeResponse:
        settings = get_settings()
        start_time = time.time()
        logger.info(f"[{job_id}] Starting comprehensive architectural analysis for: {repo_url}")

        # Ruta 1 (Predeterminada): Orquestación con LangGraph StateGraph (M-12)
        if settings.use_graph:
            logger.info(f"[{job_id}] Ejecutando análisis arquitectónico mediante grafo LangGraph")
            initial_state = {
                "repo_url": repo_url,
                "github_token": SecretStr(github_token) if github_token else SecretStr(""),
                "job_id": job_id,
                "summaries": [],
                "tokens_used": 0,
                "attempts": 0,
            }

            final_state = await self.graph.ainvoke(initial_state)

            duration_ms = int((time.time() - start_time) * 1000)
            sections = final_state.get("sections") or ["Documentación General"]
            tokens_used = final_state.get("tokens_used", 0)

            return AnalyzeResponse(
                markdown=final_state.get("document", ""),
                tokensUsed=tokens_used,
                durationMs=duration_ms,
                sections=sections,
                filesAnalyzed=final_state.get("files_analyzed", 0),
                filesTotal=final_state.get("files_total", 0),
                truncated=final_state.get("truncated", False),
            )

        # Ruta 2 (Fallback): Cadena directa LCEL M-11 si USE_GRAPH=false
        logger.info(f"[{job_id}] USE_GRAPH=false: Ejecutando ruta directa LCEL (fallback M-11)")
        repo_result = await asyncio.to_thread(fetch_repository_files, repo_url, github_token)
        files = repo_result.files
        if not files:
            raise RepoEmptyException("El repositorio no contiene archivos de código analizables")

        ordered_files = prioritize_files(files)
        manifest_content = ""
        readme_content = ""
        file_tree_lines = []
        source_code_parts = []
        total_bundle_chars = 0

        for filepath, content in ordered_files:
            file_tree_lines.append(filepath)
            name_lower = filepath.lower().split("/")[-1]

            if name_lower in MANIFEST_NAMES and not manifest_content:
                manifest_content = content
            elif name_lower in README_NAMES and not readme_content:
                readme_content = content
            else:
                if len(source_code_parts) < settings.max_source_files and total_bundle_chars < settings.max_bundle_chars:
                    ext = filepath.split(".")[-1]
                    file_slice = content[: settings.max_chars_per_file]
                    part_str = f"### Archivo: `{filepath}`\n```{ext}\n{file_slice}\n```"
                    source_code_parts.append(part_str)
                    total_bundle_chars += len(part_str)

        file_tree = "\n".join(file_tree_lines)
        source_code_bundle = "\n\n".join(source_code_parts)
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        full_markdown, tokens_used = await self.llm.generate_full_architecture_docs(
            repo_url=repo_url,
            repo_name=repo_name,
            file_tree=file_tree,
            manifest_content=manifest_content,
            readme_content=readme_content,
            source_code_bundle=source_code_bundle,
        )

        sections = []
        for line in full_markdown.splitlines():
            if line.startswith("## "):
                sections.append(line.replace("## ", "").strip())

        duration_ms = int((time.time() - start_time) * 1000)
        return AnalyzeResponse(
            markdown=full_markdown,
            tokensUsed=tokens_used,
            durationMs=duration_ms,
            sections=sections if sections else ["Documentación General"],
            filesAnalyzed=repo_result.files_analyzed,
            filesTotal=repo_result.files_total,
            truncated=repo_result.truncated,
        )
