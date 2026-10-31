"""Deterministic repository inventory builder.

Inspects acquired file contents statically (AST for Python, simple heuristics
for other languages) and produces a structured :class:`RepositoryInventory`.
No repository code is executed.
"""

from __future__ import annotations

import ast
import os
import re

from github_to_docs.repository.acquisition import AcquisitionResult
from github_to_docs.repository.inventory import (
    CodeSymbol,
    EnvVarReference,
    FileEntry,
    RepositoryInventory,
    RouteDeclaration,
)

# Common manifest filenames.
MANIFEST_FILENAMES = {
    "pyproject.toml",
    "setup.cfg",
    "requirements.txt",
    "requirements.in",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
}

DOCUMENTATION_FILENAMES = {
    "readme.md",
    "readme.rst",
    "readme.txt",
    "readme",
}

CI_DIR = ".github/workflows"


def _language_for_path(path: str) -> str:
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    mapping = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".jsx": "JavaScript",
        ".tsx": "TypeScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C/C++",
        ".cs": "C#",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".r": "R",
        ".dart": "Dart",
        ".lua": "Lua",
        ".sh": "Shell",
        ".sql": "SQL",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
        ".md": "Markdown",
        ".dockerfile": "Docker",
        "Dockerfile": "Docker",
    }
    base = os.path.basename(path)
    if base == "Dockerfile" or base.startswith("Dockerfile."):
        return "Docker"
    return mapping.get(ext, "Unknown")


def _is_test_path(path: str) -> bool:
    base = os.path.basename(path).lower()
    parts = [p.lower() for p in path.split("/")]
    test_indicators = {"test", "tests", "__tests__", "__pycache__"}
    if any(p in test_indicators for p in parts):
        return True
    if (
        base.startswith("test_")
        or base.endswith("_test.py")
        or base.endswith(".test.js")
        or base.endswith(".test.ts")
    ):
        return True
    return False


def _is_doc_path(path: str) -> bool:
    return os.path.basename(path).lower() in DOCUMENTATION_FILENAMES or path.lower().startswith(
        "docs/"
    )


def _is_config_path(path: str) -> bool:
    base = os.path.basename(path).lower()
    config_names = {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "package.json",
        "tsconfig.json",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        ".env",
        ".env.example",
        "Makefile",
        "Cargo.toml",
        "go.mod",
        "poetry.lock",
        "Pipfile",
    }
    if base in config_names:
        return True
    if base.startswith(".") and base not in {".gitignore", ".gitattributes"}:
        return True
    return False


def _is_entry_point(path: str) -> bool:
    base = os.path.basename(path).lower()
    return base in {"main.py", "app.py", "index.js", "index.ts", "main.go", "main.rs", "main.java"}


def _parse_python_symbols(path: str, content: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError:
        return symbols
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append(CodeSymbol(node.name, "function", path, node.lineno))
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(CodeSymbol(node.name, "function", path, node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(CodeSymbol(node.name, "class", path, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols.append(CodeSymbol(alias.name, "import", path, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                symbols.append(CodeSymbol(node.module, "import", path, node.lineno))
    return symbols


# Very lightweight route detection for FastAPI/Flask-style decorators.
_ROUTE_RE = re.compile(
    r"@(?:app|router|bp|blueprint)\.(get|post|put|delete|patch|options|head)\s*\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)

_ENV_VAR_RE = re.compile(
    r"os\.environ\.(?:get|getenv)\s*\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']"
    r"|os\.environ\s*\[\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\]"
    r"|getenv\s*\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']",
    re.IGNORECASE,
)


def build_inventory(result: AcquisitionResult) -> RepositoryInventory:
    """Build a deterministic inventory from an acquisition result."""
    inventory = RepositoryInventory(
        repository_url=result.repository_url.normalized,
        revision=result.revision,
        default_branch=result.default_branch,
        total_files=len(result.files) + len(result.skipped_files),
        included_files=len(result.files),
        excluded_files=len(result.skipped_files),
        total_size_bytes=sum(f.size for f in result.files),
        skipped_files=list(result.skipped_files),
        analysis_limitations=list(result.analysis_limitations),
    )

    for fc in result.files:
        path = fc.path
        text = fc.content.decode("utf-8", errors="replace")
        language = _language_for_path(path)

        entry = FileEntry(
            path=path,
            size_bytes=fc.size,
            language=language,
            line_count=text.count("\n") + 1 if text else 0,
        )
        entry.is_manifest = os.path.basename(path) in MANIFEST_FILENAMES
        entry.is_test = _is_test_path(path)
        entry.is_documentation = _is_doc_path(path)
        entry.is_config = _is_config_path(path)
        entry.is_entry_point = _is_entry_point(path)

        inventory.files.append(entry)
        inventory.languages[language] = inventory.languages.get(language, 0) + 1

        if entry.is_documentation:
            inventory.docs_paths.append(path)
            if os.path.basename(path).lower() in {
                "readme.md",
                "readme",
                "readme.rst",
                "readme.txt",
            }:
                inventory.readme_path = path
        if entry.is_test:
            inventory.test_paths.append(path)
        if entry.is_entry_point:
            inventory.entry_points.append(path)

        # Python symbols.
        if language == "Python":
            inventory.symbols.extend(_parse_python_symbols(path, text))

        # Route declarations (lightweight regex, not execution).
        for m in _ROUTE_RE.finditer(text):
            method = m.group(1).upper()
            route_path = m.group(2)
            inventory.routes.append(RouteDeclaration(method, route_path, path, None, None))

        # Env var references.
        for m in _ENV_VAR_RE.finditer(text):
            name = m.group(1) or m.group(2) or m.group(3)
            if name:
                inventory.env_vars.append(EnvVarReference(name, path, None))

        # CI workflows.
        if path.startswith(CI_DIR) and path.lower().endswith((".yml", ".yaml")):
            inventory.ci_workflows.append(path)

    # Deduplicate env vars by (name, file).
    seen_env: set[tuple[str, str]] = set()
    deduped_env: list[EnvVarReference] = []
    for ev in inventory.env_vars:
        key = (ev.name, ev.file_path)
        if key not in seen_env:
            seen_env.add(key)
            deduped_env.append(ev)
    inventory.env_vars = deduped_env

    return inventory
