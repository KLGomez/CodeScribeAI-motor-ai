import base64
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict

from github import Github, GithubException

from app.config import get_settings
from app.core.exceptions import (
    GitHubRateLimitException,
    RepoEmptyException,
    RepoNotFoundException,
)
from app.core.prioritizer import score_filepath

logger = logging.getLogger(__name__)

STRICT_GITHUB_URL_REGEX = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".lock", ".map", ".woff",
    ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".tsbuildinfo",
    ".min.js", ".min.css", ".exe", ".bin", ".pyc", ".iso",
}

SKIP_FILENAMES = {
    "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb",
    "cargo.lock", "poetry.lock", "composer.lock", "gemfile.lock",
    "license", "license.md", "license.txt", ".ds_store",
}

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt",
    "__pycache__", ".venv", "venv", ".idea", ".vscode",
    "coverage", ".nyc_output", ".cache", "public",
}


@dataclass
class RepositoryFilesResult:
    files: Dict[str, str]
    files_analyzed: int
    files_total: int
    truncated: bool


def parse_github_url(url: str) -> tuple[str, str]:
    if not url or not isinstance(url, str):
        raise ValueError("Invalid GitHub URL: URL is empty or not a string")

    # Disallow forbidden characters: credentials, backslashes, colons after scheme, whitespace, non-ascii
    clean_url = url.strip()
    if not clean_url.isascii():
        raise ValueError(f"Invalid GitHub URL: contains non-ASCII characters: {url}")

    if any(ch in clean_url for ch in (" ", "\t", "\n", "\r", "@", "\\")):
        raise ValueError(f"Invalid GitHub URL: contains invalid characters: {url}")

    match = STRICT_GITHUB_URL_REGEX.match(clean_url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")

    owner = match.group(1)
    repo = match.group(2)

    # Disallow directory traversal or dot names
    if owner in (".", "..") or repo in (".", "..") or ".." in owner or ".." in repo:
        raise ValueError(f"Invalid GitHub URL: path traversal detected: {url}")

    return owner, repo


def _is_valid_file_path(path: str, size: int | None, max_kb: int) -> bool:
    parts = path.split("/")
    if any(part.lower() in SKIP_DIRS for part in parts[:-1]):
        return False
    filename = parts[-1].lower()
    if filename in SKIP_FILENAMES:
        return False
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext in SKIP_EXTENSIONS or filename.endswith(".min.js") or filename.endswith(".min.css"):
        return False
    if size is not None and size > max_kb * 1024:
        return False
    return True


def fetch_repository_files(repo_url: str, github_token: str) -> RepositoryFilesResult:
    """
    Fetches file contents from a GitHub repository.
    Prefers the Git Trees API (recursive) to retrieve the entire repo tree in 1 single request.
    Falls back to recursive folder traversal if needed.
    """
    settings = get_settings()

    # Determine token: user token -> server fallback token -> env var GITHUB_TOKEN
    token = github_token if github_token and not github_token.startswith("ghp_demo") else None
    if not token:
        token = settings.github_fallback_token or os.getenv("GITHUB_TOKEN") or None

    g = Github(token)
    owner, repo_name = parse_github_url(repo_url)

    try:
        repo = g.get_repo(f"{owner}/{repo_name}")
    except GithubException as e:
        status_code = getattr(e, "status", None)
        msg = str(e).lower()
        if status_code == 404:
            raise RepoNotFoundException()
        if status_code in (403, 429) or "rate limit" in msg:
            raise GitHubRateLimitException()

        logger.warning(f"Could not connect via token, trying anonymous: {e}")
        try:
            repo = Github().get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            s_code = getattr(exc, "status", None)
            m_str = str(exc).lower()
            if s_code == 404:
                raise RepoNotFoundException()
            if s_code in (403, 429) or "rate limit" in m_str:
                raise GitHubRateLimitException()
            raise ValueError(f"Cannot access repository {owner}/{repo_name}: {exc.data.get('message', str(exc))}")

    # Try Git Trees API first (drastically reduces requests from N to ~1 + blob downloads)
    try:
        return _fetch_via_git_tree(
            repo,
            max_files=settings.max_source_files,
            max_kb=settings.max_file_size_kb,
            max_chars=settings.max_chars_per_file,
        )
    except (RepoNotFoundException, GitHubRateLimitException, RepoEmptyException):
        raise
    except Exception as e:
        logger.warning(f"Git Trees API failed for {owner}/{repo_name} ({e}), falling back to standard traversal")
        files: Dict[str, str] = {}
        _traverse(repo, "", files, settings.max_source_files, settings.max_file_size_kb, settings.max_chars_per_file)
        if not files:
            raise RepoEmptyException()
        return RepositoryFilesResult(
            files=files,
            files_analyzed=len(files),
            files_total=len(files),
            truncated=False,
        )


def _fetch_via_git_tree(repo, max_files: int, max_kb: int, max_chars: int) -> RepositoryFilesResult:
    branch = repo.default_branch or "main"
    try:
        git_tree = repo.get_git_tree(branch, recursive=True)
    except GithubException as e:
        if getattr(e, "status", None) == 404:
            raise RepoNotFoundException()
        if getattr(e, "status", None) in (403, 429) or "rate limit" in str(e).lower():
            raise GitHubRateLimitException()
        raise

    if not git_tree or not git_tree.tree:
        raise RepoEmptyException()

    is_truncated = bool(getattr(git_tree, "truncated", False))
    if is_truncated:
        logger.warning(f"Git tree for repository {repo.full_name} is truncated by GitHub (exceeded 100,000 entries)")

    all_blobs = [item for item in git_tree.tree if item.type == "blob"]
    files_total = len(all_blobs)

    candidate_elements = [
        item for item in all_blobs
        if _is_valid_file_path(item.path, getattr(item, "size", None), max_kb)
    ]

    if not candidate_elements:
        raise RepoEmptyException()

    # Prioritize candidate files using domain heuristics
    candidate_elements.sort(key=lambda item: (score_filepath(item.path), len(item.path)))
    selected_elements = candidate_elements[:max_files]

    files: Dict[str, str] = {}
    for item in selected_elements:
        try:
            blob = repo.get_git_blob(item.sha)
            if blob.encoding == "base64":
                raw_bytes = base64.b64decode(blob.content)
            else:
                raw_bytes = blob.content.encode("utf-8")
            decoded_text = raw_bytes.decode("utf-8", errors="replace")
            files[item.path] = decoded_text[:max_chars]
        except Exception as err:
            logger.debug(f"Failed to fetch blob for {item.path}: {err}")
            try:
                content_file = repo.get_contents(item.path)
                decoded_text = content_file.decoded_content.decode("utf-8", errors="replace")
                files[item.path] = decoded_text[:max_chars]
            except Exception:
                pass

    if not files:
        raise RepoEmptyException()

    return RepositoryFilesResult(
        files=files,
        files_analyzed=len(files),
        files_total=files_total,
        truncated=is_truncated or (files_total > max_files),
    )


def _traverse(
    repo, path: str, files: Dict[str, str], max_files: int, max_kb: int, max_chars: int
) -> None:
    if len(files) >= max_files:
        return
    try:
        contents = repo.get_contents(path)
    except GithubException:
        return

    if not isinstance(contents, list):
        contents = [contents]

    for item in contents:
        if len(files) >= max_files:
            break
        if item.type == "dir":
            dirname = item.path.split("/")[-1]
            if dirname not in SKIP_DIRS:
                _traverse(repo, item.path, files, max_files, max_kb, max_chars)
        elif item.type == "file":
            if _is_valid_file_path(item.path, item.size, max_kb):
                try:
                    decoded = item.decoded_content.decode("utf-8", errors="replace")
                    files[item.path] = decoded[:max_chars]
                except Exception:
                    pass
