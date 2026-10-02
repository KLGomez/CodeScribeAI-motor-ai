import base64
import logging
import os
import re
from typing import Dict
from github import Github, GithubException
from app.config import get_settings
from app.core.prioritizer import score_filepath

logger = logging.getLogger(__name__)

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".lock", ".map", ".woff",
    ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".tsbuildinfo",
    ".min.js", ".min.css",
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


def parse_github_url(url: str) -> tuple[str, str]:
    match = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner = match.group(1)
    repo = re.sub(r"\.git$", "", match.group(2).rstrip("/"))
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


def fetch_repository_files(repo_url: str, github_token: str) -> Dict[str, str]:
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
        logger.warning(f"Could not connect via token, trying anonymous: {e}")
        try:
            repo = Github().get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            raise ValueError(f"Cannot access repository {owner}/{repo_name}: {exc.data.get('message', str(exc))}")

    # Try Git Trees API first (drastically reduces requests from N to ~1 + downloads)
    try:
        return _fetch_via_git_tree(repo, settings.max_files_per_repo, settings.max_file_size_kb)
    except Exception as e:
        logger.warning(f"Git Trees API failed for {owner}/{repo_name} ({e}), falling back to standard traversal")
        files: Dict[str, str] = {}
        _traverse(repo, "", files, settings.max_files_per_repo, settings.max_file_size_kb)
        return files


def _fetch_via_git_tree(repo, max_files: int, max_kb: int) -> Dict[str, str]:
    branch = repo.default_branch or "main"
    git_tree = repo.get_git_tree(branch, recursive=True)
    if not git_tree or not git_tree.tree:
        return {}

    candidate_elements = []
    for item in git_tree.tree:
        if item.type == "blob" and _is_valid_file_path(item.path, getattr(item, "size", None), max_kb):
            candidate_elements.append(item)

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
            files[item.path] = raw_bytes.decode("utf-8", errors="replace")
        except Exception as err:
            logger.debug(f"Failed to fetch blob for {item.path}: {err}")
            try:
                content_file = repo.get_contents(item.path)
                files[item.path] = content_file.decoded_content.decode("utf-8", errors="replace")
            except Exception:
                pass

    return files


def _traverse(
    repo, path: str, files: Dict[str, str], max_files: int, max_kb: int
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
                _traverse(repo, item.path, files, max_files, max_kb)
        elif item.type == "file":
            if _is_valid_file_path(item.path, item.size, max_kb):
                try:
                    files[item.path] = item.decoded_content.decode("utf-8", errors="replace")
                except Exception:
                    pass
