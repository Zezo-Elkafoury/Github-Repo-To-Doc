"""Safe output writing: atomic writes with path containment.

All generated files are written into a controlled output directory. Path
traversal and unsafe filenames are rejected.
"""

from __future__ import annotations

import os
import tempfile

_OUTPUT_DIR_TOKEN = object()


def ensure_output_dir(base_dir: str, repository_name: str, run_id: str) -> str:
    """Create and return the run output directory.

    Path is contained within base_dir; repository_name and run_id are validated
    to contain no path separators.
    """
    _safe_segment(repository_name, "repository_name")
    _safe_segment(run_id, "run_id")

    output_dir = os.path.abspath(os.path.join(base_dir, repository_name, run_id))
    # Containment check: resolved path must start with the resolved base dir.
    base_abs = os.path.abspath(base_dir)
    if not (output_dir == base_abs or output_dir.startswith(base_abs + os.sep)):
        raise ValueError(f"Output path escapes base directory: {output_dir}")

    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _safe_segment(value: str, name: str) -> None:
    if not value or value in {".", ".."}:
        raise ValueError(f"{name} must be a non-empty, non-dot segment")
    if "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"{name} must not contain path separators or null bytes")


def write_document(output_dir: str, filename: str, content: str) -> str:
    """Atomically write a document into output_dir.

    Returns the absolute path written. Rejects path traversal in filename.
    """
    _safe_segment(filename, "filename")
    # Disallow reserved names and extensions that could be executable.
    lower = filename.lower()
    if lower.endswith((".py", ".sh", ".bat", ".exe", ".dll", ".so")):
        raise ValueError(f"Refusing to write executable file type: {filename}")

    target = os.path.abspath(os.path.join(output_dir, filename))
    output_dir_abs = os.path.abspath(output_dir)
    if not (target == output_dir_abs or target.startswith(output_dir_abs + os.sep)):
        raise ValueError(f"Document path escapes output directory: {target}")

    # Atomic write: temp file in same dir, then replace.
    fd, tmp_path = tempfile.mkstemp(dir=output_dir, prefix=".tmp_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return target
