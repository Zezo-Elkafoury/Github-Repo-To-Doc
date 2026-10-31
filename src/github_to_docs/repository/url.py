"""GitHub repository URL parsing, validation, and normalization.

Only ``https://github.com/owner/repository`` forms are accepted. Credentials,
unexpected ports, SSH-style URLs, and non-GitHub hosts are rejected to avoid
SSRF and unsafe redirects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ALLOWED_HOSTS = {"github.com", "www.github.com"}

# https://github.com/owner/repo  (optional trailing /.git)
_URL_RE = re.compile(
    r"^https://(?P<host>github\.com|www\.github\.com)/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:/)?(?:\.git)?$"
)

# Credentials anywhere in the URL (user:pass@host or user@host)
_CREDENTIAL_RE = re.compile(r"@|://[^/@]+:[^/@]+@")


class InvalidRepositoryUrlError(ValueError):
    """Raised when a repository URL is malformed or unsupported."""


@dataclass(frozen=True)
class RepositoryUrl:
    """A validated, normalized GitHub repository URL."""

    owner: str
    repo: str
    host: str = "github.com"
    branch: str | None = None

    @property
    def normalized(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.repo}"

    @property
    def api_repo(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_repository_url(url: str) -> RepositoryUrl:
    """Parse and validate a GitHub repository URL.

    Raises:
        InvalidRepositoryUrlError: if the URL is malformed, uses an unsupported
            scheme/host, carries credentials, or specifies an unexpected port.
    """
    if not isinstance(url, str) or not url.strip():
        raise InvalidRepositoryUrlError("Repository URL must be a non-empty string.")

    url = url.strip()

    # Reject credentials explicitly before parsing.
    if _CREDENTIAL_RE.search(url):
        raise InvalidRepositoryUrlError("Repository URL must not contain credentials.")

    # Reject anything with an explicit port.
    if re.search(r"://[^/]+:\d+", url):
        raise InvalidRepositoryUrlError("Repository URL must not specify a port.")

    match = _URL_RE.match(url)
    if match is None:
        raise InvalidRepositoryUrlError(
            "Unsupported repository URL. Use https://github.com/owner/repository."
        )

    host = match.group("host")
    if host not in _ALLOWED_HOSTS:
        raise InvalidRepositoryUrlError(f"Unsupported host: {host}")

    # Normalize host to github.com.
    normalized_host = "github.com"
    owner = match.group("owner")
    repo = match.group("repo")

    # Guard against path-traversal-looking segments.
    for segment in (owner, repo):
        if segment in {".", ".."} or segment.startswith("-"):
            raise InvalidRepositoryUrlError(f"Invalid path segment: {segment}")

    return RepositoryUrl(owner=owner, repo=repo, host=normalized_host)
