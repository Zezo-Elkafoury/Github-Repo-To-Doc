"""Unit tests for GitHub URL validation and normalization."""

import pytest

from github_to_docs.repository.url import (
    InvalidRepositoryUrlError,
    parse_repository_url,
)


def test_valid_url() -> None:
    parsed = parse_repository_url("https://github.com/owner/repo")
    assert parsed.owner == "owner"
    assert parsed.repo == "repo"
    assert parsed.host == "github.com"
    assert parsed.normalized == "https://github.com/owner/repo"
    assert parsed.api_repo == "owner/repo"


def test_url_with_git_suffix() -> None:
    parsed = parse_repository_url("https://github.com/owner/repo.git")
    assert parsed.repo == "repo"
    assert parsed.normalized == "https://github.com/owner/repo"


def test_url_with_trailing_slash() -> None:
    parsed = parse_repository_url("https://github.com/owner/repo/")
    assert parsed.repo == "repo"


def test_www_host_normalized() -> None:
    parsed = parse_repository_url("https://www.github.com/owner/repo")
    assert parsed.host == "github.com"


def test_empty_url_rejected() -> None:
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url("")
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url("   ")


def test_credentials_rejected() -> None:
    for url in (
        "https://user:pass@github.com/owner/repo",
        "https://user@github.com/owner/repo",
    ):
        with pytest.raises(InvalidRepositoryUrlError):
            parse_repository_url(url)


def test_port_rejected() -> None:
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url("https://github.com:8443/owner/repo")


def test_bad_scheme_rejected() -> None:
    for url in (
        "git://github.com/owner/repo",
        "ssh://git@github.com/owner/repo",
        "http://github.com/owner/repo",
        "ftp://github.com/owner/repo",
    ):
        with pytest.raises(InvalidRepositoryUrlError):
            parse_repository_url(url)


def test_bad_host_rejected() -> None:
    for url in (
        "https://gitlab.com/owner/repo",
        "https://bitbucket.org/owner/repo",
        "https://evil.com/owner/repo",
        "https://github.com.evil.com/owner/repo",
    ):
        with pytest.raises(InvalidRepositoryUrlError):
            parse_repository_url(url)


def test_path_traversal_segments_rejected() -> None:
    for url in (
        "https://github.com/./repo",
        "https://github.com/.. /repo",
        "https://github.com/owner/..",
        "https://github.com/-owner/repo",
    ):
        with pytest.raises(InvalidRepositoryUrlError):
            parse_repository_url(url)


def test_invalid_is_value_error_subclass() -> None:
    assert issubclass(InvalidRepositoryUrlError, ValueError)
