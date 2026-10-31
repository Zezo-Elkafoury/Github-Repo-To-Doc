"""Unit tests for evidence extraction from inventory (offline, no network)."""

from github_to_docs.evidence.extraction import extract_evidence
from github_to_docs.repository.acquisition import AcquisitionResult, FileContent
from github_to_docs.repository.inventory import (
    CodeSymbol,
    EnvVarReference,
    FileEntry,
    RepositoryInventory,
    RouteDeclaration,
)
from github_to_docs.repository.url import RepositoryUrl


def _make_file(path: str, content: str) -> FileContent:
    data = content.encode("utf-8")
    return FileContent(
        path=path,
        content=data,
        sha="x" * 64,
        size=len(data),
        download_url=f"https://example.com/{path}",
    )


def test_extract_evidence_basic() -> None:
    repo = RepositoryUrl(owner="owner", repo="repo")
    result = AcquisitionResult(
        repository_url=repo,
        revision="abc123",
        default_branch="main",
        repository_size_kb=10,
        files=[
            _make_file("README.md", "# Hello\n"),
            _make_file("src/main.py", "def foo():\n    pass\n"),
        ],
    )
    inventory = RepositoryInventory(
        repository_url="https://github.com/owner/repo",
        revision="abc123",
        default_branch="main",
        total_files=2,
        included_files=2,
        excluded_files=0,
        total_size_bytes=0,
        files=[
            FileEntry(path="README.md", size_bytes=9, is_documentation=True, line_count=1),
            FileEntry(path="src/main.py", size_bytes=20, line_count=2),
        ],
        symbols=[
            CodeSymbol("foo", "function", "src/main.py", 1),
        ],
        routes=[
            RouteDeclaration("GET", "/api/users", "src/main.py", 1),
        ],
        env_vars=[
            EnvVarReference("DATABASE_URL", "src/main.py", 1),
        ],
        ci_workflows=[],
    )

    registry = extract_evidence(result, inventory)

    assert registry.repository_revision == "abc123"
    assert len(registry) >= 1
    # All evidence references must be valid.
    for eid in [i.evidence_id for i in registry.all()]:
        assert registry.validate_reference(eid)


def test_extract_evidence_redacts_secret() -> None:
    repo = RepositoryUrl(owner="o", repo="r")
    result = AcquisitionResult(
        repository_url=repo,
        revision="rev",
        default_branch="main",
        repository_size_kb=1,
        files=[
            _make_file(
                "config.py",
                'API_KEY = "sk-secret-value"\n',
            ),
        ],
    )
    inventory = RepositoryInventory(
        repository_url="https://github.com/o/r",
        revision="rev",
        default_branch="main",
        total_files=1,
        included_files=1,
        excluded_files=0,
        total_size_bytes=0,
        files=[
            FileEntry(path="config.py", size_bytes=22, is_config=True, line_count=1),
        ],
        symbols=[],
        routes=[],
        env_vars=[
            EnvVarReference("API_KEY", "config.py", 1),
        ],
    )

    registry = extract_evidence(result, inventory)
    # The secret value must not appear in any evidence content.
    for item in registry.all():
        assert "sk-secret-value" not in item.content
