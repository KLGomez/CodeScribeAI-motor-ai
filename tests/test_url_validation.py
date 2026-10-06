import pytest

from app.core.github_client import parse_github_url


def test_valid_github_urls():
    owner, repo = parse_github_url("https://github.com/KLGomez/CodeScribeAI-front")
    assert owner == "KLGomez"
    assert repo == "CodeScribeAI-front"

    owner, repo = parse_github_url("https://github.com/facebook/react.git")
    assert owner == "facebook"
    assert repo == "react"

    owner, repo = parse_github_url("https://github.com/owner-name/repo.name/")
    assert owner == "owner-name"
    assert repo == "repo.name"


def test_invalid_github_urls_embedded_credentials():
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("https://user:password@github.com/KLGomez/repo")


def test_invalid_github_urls_path_traversal():
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("https://github.com/KLGomez/../../etc/passwd")


def test_invalid_github_urls_ip_address():
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("https://192.168.1.1/KLGomez/repo")


def test_invalid_github_urls_different_protocol():
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("http://github.com/KLGomez/repo")

    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("git@github.com:KLGomez/repo.git")


def test_invalid_github_urls_non_ascii_characters():
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("https://github.com/KLGómez/repositorio_español")


def test_invalid_github_urls_dot_directories():
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("https://github.com/./repo")

    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        parse_github_url("https://github.com/owner/..")
