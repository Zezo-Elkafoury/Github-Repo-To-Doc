"""Unit tests for the deterministic inventory builder (offline, no network)."""

from github_to_docs.repository.acquisition import AcquisitionResult, FileContent
from github_to_docs.repository.inventory_builder import build_inventory
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


def test_build_inventory_basic() -> None:
    repo = RepositoryUrl(owner="owner", repo="repo")
    result = AcquisitionResult(
        repository_url=repo,
        revision="abc123",
        default_branch="main",
        repository_size_kb=10,
        files=[
            _make_file("src/main.py", "from fastapi import FastAPI\napp = FastAPI()\n"),
            _make_file("README.md", "# Hello\n"),
            _make_file("requirements.txt", "fastapi>=0.100\n"),
        ],
        skipped_files=["node_modules/pkg/index.js"],
    )

    inventory = build_inventory(result)

    assert inventory.repository_url == "https://github.com/owner/repo"
    assert inventory.revision == "abc123"
    assert inventory.included_files == 3
    assert inventory.excluded_files == 1
    assert inventory.total_files == 4
    assert inventory.readme_path == "README.md"
    assert "src/main.py" in inventory.entry_points
    assert "README.md" in inventory.docs_paths
    assert "requirements.txt" not in inventory.docs_paths
    assert ".git" not in inventory.skipped_files  # not present


def test_build_inventory_python_symbols() -> None:
    repo = RepositoryUrl(owner="o", repo="r")
    result = AcquisitionResult(
        repository_url=repo,
        revision="rev",
        default_branch="main",
        repository_size_kb=1,
        files=[
            _make_file(
                "pkg/mod.py",
                "import os\nfrom sys import path\n\ndef foo():\n    pass\n\nclass Bar:\n    pass\n",
            ),
        ],
    )
    inventory = build_inventory(result)
    names = {s.name for s in inventory.symbols}
    assert "os" in names
    assert "sys" in names
    assert "foo" in names
    assert "Bar" in names
    kinds = {s.kind for s in inventory.symbols}
    assert "function" in kinds
    assert "class" in kinds
    assert "import" in kinds


def test_build_inventory_routes() -> None:
    repo = RepositoryUrl(owner="o", repo="r")
    result = AcquisitionResult(
        repository_url=repo,
        revision="rev",
        default_branch="main",
        repository_size_kb=1,
        files=[
            _make_file(
                "app/main.py",
                '@app.get("/api/users")\ndef list_users():\n    return []\n',
            ),
        ],
    )
    inventory = build_inventory(result)
    assert len(inventory.routes) == 1
    route = inventory.routes[0]
    assert route.method == "GET"
    assert route.path == "/api/users"
    assert route.file_path == "app/main.py"


def test_build_inventory_env_vars() -> None:
    repo = RepositoryUrl(owner="o", repo="r")
    result = AcquisitionResult(
        repository_url=repo,
        revision="rev",
        default_branch="main",
        repository_size_kb=1,
        files=[
            _make_file(
                "src/app.py",
                'DB_URL = os.environ.get("DATABASE_URL")\nSECRET = os.environ["SECRET_KEY"]\n',
            ),
        ],
    )
    inventory = build_inventory(result)
    names = {ev.name for ev in inventory.env_vars}
    assert "DATABASE_URL" in names
    assert "SECRET_KEY" in names


def test_build_inventory_languages() -> None:
    repo = RepositoryUrl(owner="o", repo="r")
    result = AcquisitionResult(
        repository_url=repo,
        revision="rev",
        default_branch="main",
        repository_size_kb=1,
        files=[
            _make_file("a.py", "x = 1\n"),
            _make_file("b.js", "const x = 1;\n"),
            _make_file("c.py", "y = 2\n"),
        ],
    )
    inventory = build_inventory(result)
    assert inventory.languages.get("Python") == 2
    assert inventory.languages.get("JavaScript") == 1
