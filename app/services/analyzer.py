import asyncio
import logging
import time

from app.config import get_settings
from app.core.exceptions import RepoEmptyException
from app.core.github_client import fetch_repository_files
from app.core.prioritizer import prioritize_files
from app.schemas.response import AnalyzeResponse
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

MANIFEST_NAMES = {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml"}
README_NAMES = {"readme.md", "readme.rst", "readme.txt"}


class AnalyzerService:
    def __init__(self):
        self.llm = LLMService()

    async def analyze(self, repo_url: str, github_token: str, job_id: str) -> AnalyzeResponse:
        settings = get_settings()
        start_time = time.time()
        logger.info(f"[{job_id}] Starting comprehensive architectural analysis for: {repo_url}")

        # 1. Fetch files from GitHub asynchronously to keep event loop free
        repo_result = await asyncio.to_thread(fetch_repository_files, repo_url, github_token)
        files = repo_result.files
        logger.info(
            f"[{job_id}] Fetched {len(files)} files (total: {repo_result.files_total}, truncated: {repo_result.truncated})"
        )

        if not files:
            raise RepoEmptyException("El repositorio no contiene archivos de código analizables")

        # 2. Prioritize files (source code first, configs last)
        ordered_files = prioritize_files(files)

        # 3. Extract manifest and readme
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
                # Limit source code bundle size according to config
                if len(source_code_parts) < settings.max_source_files and total_bundle_chars < settings.max_bundle_chars:
                    ext = filepath.split(".")[-1]
                    file_slice = content[: settings.max_chars_per_file]
                    part_str = f"### Archivo: `{filepath}`\n```{ext}\n{file_slice}\n```"
                    source_code_parts.append(part_str)
                    total_bundle_chars += len(part_str)

        file_tree = "\n".join(file_tree_lines)
        source_code_bundle = "\n\n".join(source_code_parts)

        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        # 4. Invoke Senior Architect prompt with Gemini
        full_markdown, tokens_used = await self.llm.generate_full_architecture_docs(
            repo_url=repo_url,
            repo_name=repo_name,
            file_tree=file_tree,
            manifest_content=manifest_content,
            readme_content=readme_content,
            source_code_bundle=source_code_bundle,
        )

        # 5. Extract section titles for table of contents
        sections = []
        for line in full_markdown.splitlines():
            if line.startswith("## "):
                sections.append(line.replace("## ", "").strip())

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"[{job_id}] Finished comprehensive analysis in {duration_ms}ms with {len(sections)} sections and {tokens_used} tokens"
        )

        return AnalyzeResponse(
            markdown=full_markdown,
            tokensUsed=tokens_used,
            durationMs=duration_ms,
            sections=sections if sections else ["Documentación General"],
            filesAnalyzed=repo_result.files_analyzed,
            filesTotal=repo_result.files_total,
            truncated=repo_result.truncated,
        )
