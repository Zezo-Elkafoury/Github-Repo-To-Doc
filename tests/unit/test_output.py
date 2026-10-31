"""Unit tests for safe output writing (offline, no network)."""

import os

import pytest

from github_to_docs.output import ensure_output_dir, write_document


def test_write_document_creates_file(tmp_path) -> None:
    path = write_document(str(tmp_path), "README.md", "# Hello\n")
    assert os.path.exists(path)
    assert os.path.basename(path) == "README.md"
    with open(path, encoding="utf-8") as f:
        assert f.read() == "# Hello\n"


def test_write_document_atomic_no_temp_left(tmp_path) -> None:
    write_document(str(tmp_path), "API.md", "# API\n")
    remaining = [f for f in os.listdir(tmp_path) if f.startswith(".tmp_")]
    assert remaining == [], f"Temp files left behind: {remaining}"


def test_write_document_path_traversal_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="path separators"):
        write_document(str(tmp_path), "../evil.md", "x")


def test_write_document_absolute_path_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        write_document(str(tmp_path), "/etc/passwd", "x")


def test_write_document_executable_rejected(tmp_path) -> None:
    for bad in ("setup.py", "run.sh", "malware.bat"):
        with pytest.raises(ValueError, match="executable"):
            write_document(str(tmp_path), bad, "x")


def test_ensure_output_dir_containment(tmp_path) -> None:
    out = ensure_output_dir(str(tmp_path), "owner_repo", "run1")
    assert out == os.path.abspath(os.path.join(str(tmp_path), "owner_repo", "run1"))
    assert os.path.isdir(out)


def test_ensure_output_dir_bad_segment() -> None:
    with pytest.raises(ValueError):
        ensure_output_dir("/tmp", "..", "run1")
    with pytest.raises(ValueError):
        ensure_output_dir("/tmp", "owner/repo", "run1")
    with pytest.raises(ValueError):
        ensure_output_dir("/tmp", "owner", "../run1")
