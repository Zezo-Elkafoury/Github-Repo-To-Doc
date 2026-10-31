"""Repository exclusion rules and size/file limits."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Default directory names to skip during acquisition/analysis.
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "build",
    "dist",
    "target",
    ".next",
    "out",
    ".gradle",
}

# Default file extensions to skip (binary/generated assets).
DEFAULT_EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".obj",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".webp",
    ".mp4",
    ".mp3",
    ".wav",
    ".avi",
    ".mov",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".wasm",
    ".eot",
    ".ttf",
    ".woff",
    ".woff2",
    ".class",
    ".jar",
    ".lock",
}

# Manifests we always want to read regardless of extension (small text files).
ALWAYS_INCLUDE_FILENAMES = {
    "README.md",
    "README.rst",
    "README.txt",
    "README",
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
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
}

DEFAULT_MAX_FILE_SIZE_KB = 512
DEFAULT_MAX_FILES = 200
DEFAULT_MAX_REPO_SIZE_MB = 100


@dataclass
class ExclusionRules:
    """Configurable rules for which files/directories to exclude."""

    excluded_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_DIRS))
    excluded_extensions: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_EXTENSIONS))
    always_include_filenames: set[str] = field(
        default_factory=lambda: set(ALWAYS_INCLUDE_FILENAMES)
    )
    max_file_size_kb: int = DEFAULT_MAX_FILE_SIZE_KB
    max_files: int = DEFAULT_MAX_FILES

    def should_exclude_dir(self, dir_name: str) -> bool:
        return dir_name in self.excluded_dirs or dir_name.startswith(".")

    def should_exclude_file(self, path: str, size_kb: float) -> bool:
        """Return True if the file should be excluded.

        Always-include filenames are never excluded by extension, but are still
        subject to the file-size limit.
        """
        base = os.path.basename(path)
        if base in self.always_include_filenames:
            return size_kb > self.max_file_size_kb
        _, ext = os.path.splitext(base)
        if ext.lower() in self.excluded_extensions:
            return True
        if size_kb > self.max_file_size_kb:
            return True
        return False


def is_text_likely(content: bytes) -> bool:
    """Heuristic: return True if bytes look like text (not binary)."""
    if not content:
        return True
    # A file with NUL bytes is treated as binary.
    if b"\x00" in content:
        return False
    text_chars = bytearray(b"".join(bytes([i]) for i in range(32, 127)) + b"\n\r\t\f\b")
    # Count bytes that are not common text characters.
    nontext = sum(1 for b in content if b not in text_chars)
    return nontext / max(len(content), 1) < 0.30
