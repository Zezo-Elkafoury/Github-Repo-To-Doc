"""Deterministic repository inventory data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileEntry:
    """Metadata for a single included file."""

    path: str
    size_bytes: int
    language: str | None = None
    is_manifest: bool = False
    is_test: bool = False
    is_documentation: bool = False
    is_config: bool = False
    is_entry_point: bool = False
    line_count: int | None = None


@dataclass
class CodeSymbol:
    """A statically discovered code symbol."""

    name: str
    kind: str  # "function", "class", "import", "variable"
    file_path: str
    line: int | None = None


@dataclass
class DependencyFinding:
    """A discovered dependency / lockfile entry."""

    name: str
    source_file: str
    version_constraint: str | None = None
    is_dev: bool = False


@dataclass
class RouteDeclaration:
    """A statically discovered API route."""

    method: str
    path: str
    file_path: str
    line: int | None = None
    handler: str | None = None


@dataclass
class EnvVarReference:
    """An environment variable referenced in source or config."""

    name: str
    file_path: str
    line: int | None = None


@dataclass
class RepositoryInventory:
    """Deterministic inventory of an analyzed repository."""

    repository_url: str
    revision: str | None = None
    default_branch: str | None = None
    total_files: int = 0
    included_files: int = 0
    excluded_files: int = 0
    total_size_bytes: int = 0
    files: list[FileEntry] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    symbols: list[CodeSymbol] = field(default_factory=list)
    dependencies: list[DependencyFinding] = field(default_factory=list)
    routes: list[RouteDeclaration] = field(default_factory=list)
    env_vars: list[EnvVarReference] = field(default_factory=list)
    ci_workflows: list[str] = field(default_factory=list)
    readme_path: str | None = None
    docs_paths: list[str] = field(default_factory=list)
    test_paths: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    analysis_limitations: list[str] = field(default_factory=list)
