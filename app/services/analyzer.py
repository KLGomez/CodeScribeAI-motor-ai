import logging
import re
import time
from typing import List
from app.core.github_client import fetch_repository_files
from app.core.prioritizer import prioritize_files
from app.services.llm_service import LLMService
from app.schemas.response import AnalyzeResponse

logger = logging.getLogger(__name__)

MANIFEST_NAMES = {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml"}
README_NAMES = {"readme.md", "readme.rst", "readme.txt"}


class AnalyzerService:
    def __init__(self):
        self.llm = LLMService()

    async def analyze(self, repo_url: str, github_token: str, job_id: str) -> AnalyzeResponse:
        start_time = time.time()
        logger.info(f"[{job_id}] Starting comprehensive architectural analysis for: {repo_url}")

        # 1. Fetch files from GitHub (lockfiles and build noise already excluded)
        files = fetch_repository_files(repo_url, github_token)
        logger.info(f"[{job_id}] Fetched {len(files)} relevant files")

        if not files:
            raise ValueError(f"No valid source files found in {repo_url} or repository empty")

        # 2. Prioritize files (source code first, configs last)
        ordered_files = prioritize_files(files)

        # 3. Extract manifest and readme
        manifest_content = ""
        readme_content = ""
        file_tree_lines = []
        source_code_parts = []

        for filepath, content in ordered_files:
            file_tree_lines.append(filepath)
            name_lower = filepath.lower().split("/")[-1]

            if name_lower in MANIFEST_NAMES and not manifest_content:
                manifest_content = content
            elif name_lower in README_NAMES and not readme_content:
                readme_content = content
            else:
                # Include source code file in bundle (up to 6,000 chars per file)
                ext = filepath.split(".")[-1]
                source_code_parts.append(
                    f"### Archivo: `{filepath}`\n```{ext}\n{content[:6000]}\n```"
                )

        file_tree = "\n".join(file_tree_lines)
        source_code_bundle = "\n\n".join(source_code_parts[:20]) # Top 20 source files

        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        # 4. Invoke Senior Architect prompt with Gemini 3.8 Flash
        full_markdown = await self.llm.generate_full_architecture_docs(
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
        logger.info(f"[{job_id}] Finished comprehensive analysis in {duration_ms}ms with {len(sections)} sections")

        return AnalyzeResponse(
            markdown=full_markdown,
            tokensUsed=0,
            durationMs=duration_ms,
            sections=sections if sections else ["Documentación General"],
        )
