from typing import Dict, List, Tuple

MANIFEST_FILES = {
    "readme.md", "readme.rst", "package.json", "pyproject.toml",
    "cargo.toml", "go.mod", "pom.xml", "dockerfile", "docker-compose.yml"
}

CONFIG_KEYWORDS = {"config", "settings", "tsconfig", "eslint", "postcss", ".env.example"}
SOURCE_DIRS = {"src/", "app/", "lib/", "components/", "pages/", "features/", "services/", "modules/"}


def _score(filepath: str) -> int:
    path_lower = filepath.lower()
    name = path_lower.split("/")[-1]

    # 1. README and primary manifest first
    if name in MANIFEST_FILES:
        return 0

    # 2. Real application source code gets highest priority
    if any(sd in path_lower for sd in SOURCE_DIRS) and not any(k in name for k in CONFIG_KEYWORDS):
        return 1

    # 3. Main root entry points
    if name in {"index.html", "main.ts", "index.ts", "main.py", "app.py"}:
        return 2

    # 4. Config files
    if any(k in name for k in CONFIG_KEYWORDS):
        return 3

    # 5. Other files
    return 4


def score_filepath(filepath: str) -> int:
    return _score(filepath)


def prioritize_files(files: Dict[str, str]) -> List[Tuple[str, str]]:
    """
    Sorts files so manifests and core application source code are analyzed first,
    leaving configuration boilerplate at the end.
    """
    return sorted(files.items(), key=lambda x: (_score(x[0]), len(x[0])))
