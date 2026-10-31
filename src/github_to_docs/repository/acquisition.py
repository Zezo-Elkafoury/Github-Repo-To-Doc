"""Repository acquisition via the GitHub API.

Responsibilities:
- Fetch repository metadata and record the exact commit SHA / revision.
- Retrieve file contents through the GitHub API contents endpoint.
- Enforce repository-size, file-count, and file-size limits.
- Handle rate limits, missing repositories, and network errors without
  silently switching to another repository or branch.
- Never execute repository code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx

from github_to_docs.config import settings
from github_to_docs.repository.errors import (
    NetworkError,
    RepositoryNotFoundError,
    RepositoryRateLimitedError,
    RepositoryTooLargeError,
)
from github_to_docs.repository.filtering import (
    DEFAULT_MAX_FILE_SIZE_KB,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_REPO_SIZE_MB,
    ExclusionRules,
    is_text_likely,
)
from github_to_docs.repository.url import RepositoryUrl, parse_repository_url

# GitHub REST API endpoint for repo contents.
CONTENTS_API = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
REPO_API = "https://api.github.com/repos/{owner}/{repo}"

# Default branch to walk if none specified.
DEFAULT_REF = "HEAD"

# Maximum bytes we will fetch for a single file via the API.
MAX_FILE_FETCH_BYTES = DEFAULT_MAX_FILE_SIZE_KB * 1024


@dataclass
class FileContent:
    """Fetched file content with provenance."""

    path: str
    content: bytes
    sha: str
    size: int
    download_url: str | None = None


@dataclass
class AcquisitionResult:
    """Result of acquiring a repository snapshot."""

    repository_url: RepositoryUrl
    revision: str  # commit SHA
    default_branch: str
    repository_size_kb: int
    files: list[FileContent] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    analysis_limitations: list[str] = field(default_factory=list)


class RepositoryAcquirer:
    """Retrieves repository metadata and file contents via the GitHub API."""

    def __init__(
        self,
        token: str | None = None,
        timeout_seconds: int | None = None,
        max_files: int = DEFAULT_MAX_FILES,
        max_file_size_kb: int = DEFAULT_MAX_FILE_SIZE_KB,
        max_repository_size_mb: int = DEFAULT_MAX_REPO_SIZE_MB,
        rules: ExclusionRules | None = None,
    ) -> None:
        self.token = token or settings.github_token
        self.timeout_seconds = timeout_seconds or settings.request_timeout_seconds
        self.max_files = max_files
        self.max_file_size_kb = max_file_size_kb
        self.max_repository_size_mb = max_repository_size_mb
        self.rules = rules or ExclusionRules(max_file_size_kb=max_file_size_kb, max_files=max_files)
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=False,  # avoid unsafe redirects
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RepositoryAcquirer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def acquire(self, repo_url: str) -> AcquisitionResult:
        """Acquire a repository snapshot.

        Raises:
            RepositoryNotFoundError: if the repo does not exist or is inaccessible.
            RepositoryRateLimitedError: if GitHub API rate limit is hit.
            RepositoryTooLargeError: if the repo exceeds size limits.
            NetworkError: on transport failures.
        """
        repo = parse_repository_url(repo_url)

        # Fetch repository metadata first to record the revision and size.
        metadata = self._get_repo_metadata(repo)
        revision = metadata["commit_sha"]
        default_branch = metadata.get("default_branch") or repo.branch or DEFAULT_REF
        repo_size_kb = metadata.get("size_kb", 0)

        if repo_size_kb > self.max_repository_size_mb * 1024:
            raise RepositoryTooLargeError(
                f"Repository size {repo_size_kb} KB exceeds limit {self.max_repository_size_mb} MB."
            )

        # Walk the file tree and collect contents.
        result = AcquisitionResult(
            repository_url=repo,
            revision=revision,
            default_branch=default_branch,
            repository_size_kb=repo_size_kb,
        )

        self._walk_tree(repo, default_branch, result, path="")

        return result

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get(self, path: str) -> httpx.Response:
        try:
            response = self._client.get(path)
        except httpx.RequestError as exc:
            raise NetworkError(f"GitHub API request failed: {exc}") from exc
        return response

    def _get_repo_metadata(self, repo: RepositoryUrl) -> dict:
        response = self._get(f"/repos/{repo.api_repo}")
        status = response.status_code

        if status == 404:
            raise RepositoryNotFoundError(
                f"Repository not found or inaccessible: {repo.normalized}"
            )
        if status == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "0")
            if remaining == "0":
                raise RepositoryRateLimitedError(
                    "GitHub API rate limit exceeded. Set GITHUB_TOKEN for higher limits."
                )
            raise RepositoryNotFoundError(f"Repository access forbidden: {repo.normalized}")
        if status >= 400:
            raise NetworkError(f"GitHub API returned HTTP {status} for {repo.normalized}")

        data = response.json()
        # The default branch's latest commit SHA is recorded as the revision.
        default_branch = data.get("default_branch")
        commit_sha = data.get("default_branch_commit", {}).get("sha")
        # Fall back to the repo's own SHA field if present.
        if not commit_sha:
            commit_sha = data.get("sha")
        if not commit_sha:
            # Fetch the default branch ref to pin an immutable revision.
            commit_sha = self._fetch_branch_sha(repo, default_branch or "main")

        return {
            "commit_sha": commit_sha,
            "default_branch": default_branch,
            "size_kb": data.get("size", 0),  # GitHub reports size in KB
        }

    def _fetch_branch_sha(self, repo: RepositoryUrl, branch: str) -> str:
        response = self._get(f"/repos/{repo.api_repo}/git/ref/heads/{branch}")
        if response.status_code == 404:
            # Try "main" then "master" as a last resort without changing repo.
            for fallback in ("main", "master"):
                if fallback == branch:
                    continue
                fb = self._get(f"/repos/{repo.api_repo}/git/ref/heads/{fallback}")
                if fb.status_code == 200:
                    return fb.json().get("object", {}).get("sha", "")
            raise RepositoryNotFoundError(f"Could not resolve a branch for {repo.normalized}")
        if response.status_code >= 400:
            raise NetworkError(
                f"GitHub API returned HTTP {response.status_code} resolving branch {branch}"
            )
        return response.json().get("object", {}).get("sha", "")

    def _walk_tree(
        self,
        repo: RepositoryUrl,
        ref: str,
        result: AcquisitionResult,
        path: str = "",
        depth: int = 0,
    ) -> None:
        """Recursively walk the repository tree via the contents API.

        The ``ref`` is pinned to the recorded revision so we never follow a
        moving branch pointer mid-walk.
        """
        if depth > 25:
            result.analysis_limitations.append(
                f"Directory depth limit reached at {path or '.'}; deeper files skipped."
            )
            return

        if len(result.files) >= self.max_files:
            result.analysis_limitations.append(
                f"Max files ({self.max_files}) reached; remaining files skipped."
            )
            return

        response = self._get(f"/repos/{repo.api_repo}/contents/{path}?ref={ref}")
        status = response.status_code

        if status == 404:
            # Path may be a file rather than a dir when called at top-level.
            if path:
                result.skipped_files.append(path)
            return
        if status == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "0")
            if remaining == "0":
                raise RepositoryRateLimitedError("GitHub API rate limit exceeded during tree walk.")
            raise NetworkError(f"GitHub API returned HTTP 403 for {path or '.'}")
        if status >= 400:
            raise NetworkError(f"GitHub API returned HTTP {status} for {path or '.'}")

        items = response.json()
        if not isinstance(items, list):
            # Single file response (top-level path pointed to a file).
            items = [items]

        for item in items:
            if len(result.files) >= self.max_files:
                result.analysis_limitations.append(
                    f"Max files ({self.max_files}) reached; remaining files skipped."
                )
                break

            item_type = item.get("type")
            item_path = item.get("path", "")
            item_size = item.get("size", 0)

            if item_type == "dir":
                dir_name = item_path.rsplit("/", 1)[-1]
                if self.rules.should_exclude_dir(dir_name):
                    result.skipped_files.append(item_path)
                    continue
                self._walk_tree(repo, ref, result, item_path, depth + 1)
                continue

            if item_type != "file":
                result.skipped_files.append(item_path)
                continue

            # Apply exclusion rules.
            size_kb = item_size / 1024.0
            if self.rules.should_exclude_file(item_path, size_kb):
                result.skipped_files.append(item_path)
                continue

            content = self._fetch_file_content(item.get("download_url"), item_path)
            if content is None:
                result.skipped_files.append(item_path)
                continue

            result.files.append(content)

    def _fetch_file_content(self, download_url: str | None, path: str) -> FileContent | None:
        """Fetch a single file's content by its download URL.

        Returns None if the file cannot be fetched or is binary/oversized.
        """
        if not download_url:
            return None

        # Use a fresh request to the raw download URL (still within github.com).
        try:
            response = self._client.get(download_url)
        except httpx.RequestError as exc:
            raise NetworkError(f"Failed to download {path}: {exc}") from exc

        if response.status_code != 200:
            return None

        content = response.content
        size = len(content)

        if size > MAX_FILE_FETCH_BYTES:
            return None

        if not is_text_likely(content):
            return None

        # Validate that the content is decodable as UTF-8 without keeping
        # an unused variable; the original bytes are preserved below.
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return None

        return FileContent(
            path=path,
            content=content,
            sha=hashlib.sha256(content).hexdigest(),
            size=size,
            download_url=download_url,
        )
