from typing import Dict, List, Tuple

PRIORITY_FILES = {
    "readme.md", "readme.rst", "readme.txt",
    "package.json", "pyproject.toml", "cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "dockerfile",
    "docker-compose.yml", "makefile",
}

CONFIG_KEYWORDS = {".config.", "settings.", "config.", ".env.example"}
TEST_KEYWORDS = {"test", "spec", "__tests__", "fixture", "mock", "seed"}


def _score(filepath: str) -> int:
    name = filepath.lower().split("/")[-1]
    if name in PRIORITY_FILES:
        return 0
    if any(k in name for k in CONFIG_KEYWORDS):
        return 1
    if any(k in filepath.lower() for k in TEST_KEYWORDS):
        return 3
    return 2


def prioritize_files(files: Dict[str, str]) -> List[Tuple[str, str]]:
    """
    Returns files sorted by relevance:
    0 = README / manifest  →  1 = config  →  2 = source  →  3 = tests
    """
    return sorted(files.items(), key=lambda x: _score(x[0]))
