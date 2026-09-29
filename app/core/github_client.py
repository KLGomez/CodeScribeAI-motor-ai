import re
from typing import Dict
from github import Github, GithubException
from app.config import get_settings

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".lock", ".map", ".woff",
    ".woff2", ".ttf", ".eot", ".mp4", ".mp3",
}

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt",
    "__pycache__", ".venv", "venv", ".idea", ".vscode",
    "coverage", ".nyc_output", ".cache",
}


def parse_github_url(url: str) -> tuple[str, str]:
    match = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner = match.group(1)
    repo = re.sub(r"\.git$", "", match.group(2).rstrip("/"))
    return owner, repo


def fetch_repository_files(repo_url: str, github_token: str) -> Dict[str, str]:
    """
    Fetches file contents from a GitHub repository via the REST API.
    Returns {filepath: content} for all text files under the limits.
    """
    settings = get_settings()
    g = Github(github_token)
    owner, repo_name = parse_github_url(repo_url)

    try:
        repo = g.get_repo(f"{owner}/{repo_name}")
    except GithubException as e:
        raise ValueError(f"Cannot access {owner}/{repo_name}: {e.data}")

    files: Dict[str, str] = {}
    _traverse(repo, "", files, settings.max_files_per_repo, settings.max_file_size_kb)
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
            ext = "." + item.name.rsplit(".", 1)[-1].lower() if "." in item.name else ""
            if ext in SKIP_EXTENSIONS:
                continue
            if item.size > max_kb * 1024:
                continue
            try:
                files[item.path] = item.decoded_content.decode("utf-8", errors="replace")
            except Exception:
                pass
