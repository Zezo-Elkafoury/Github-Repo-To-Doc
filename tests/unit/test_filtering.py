"""Unit tests for repository filtering rules."""

from github_to_docs.repository.filtering import (
    DEFAULT_EXCLUDED_DIRS,
    ExclusionRules,
    is_text_likely,
)


def test_excluded_dirs_defaults() -> None:
    assert ".git" in DEFAULT_EXCLUDED_DIRS
    assert "node_modules" in DEFAULT_EXCLUDED_DIRS
    assert "__pycache__" in DEFAULT_EXCLUDED_DIRS


def test_should_exclude_dir() -> None:
    rules = ExclusionRules()
    assert rules.should_exclude_dir(".git")
    assert rules.should_exclude_dir("node_modules")
    assert rules.should_exclude_dir(".mypy_cache")
    assert not rules.should_exclude_dir("src")
    assert not rules.should_exclude_dir("app")


def test_hidden_dirs_excluded() -> None:
    rules = ExclusionRules()
    assert rules.should_exclude_dir(".hidden_dir")


def test_should_exclude_file_by_extension() -> None:
    rules = ExclusionRules()
    assert rules.should_exclude_file("lib/foo.pyc", 1.0)
    assert rules.should_exclude_file("image.png", 1.0)
    assert rules.should_exclude_file("archive.zip", 1.0)
    assert not rules.should_exclude_file("src/main.py", 1.0)
    assert not rules.should_exclude_file("README.md", 1.0)


def test_always_include_not_excluded_by_extension() -> None:
    rules = ExclusionRules()
    # .lock is excluded by default, but poetry.lock is always included.
    assert not rules.should_exclude_file("poetry.lock", 1.0)
    assert not rules.should_exclude_file("package-lock.json", 1.0)


def test_oversized_file_excluded_even_when_always_include() -> None:
    rules = ExclusionRules(max_file_size_kb=10)
    # 1 MB > 10 KB limit.
    assert rules.should_exclude_file("README.md", 1024.0)


def test_is_text_likely() -> None:
    assert is_text_likely(b"hello world\n")
    assert is_text_likely(b"")
    assert not is_text_likely(b"\x00binary\x00")
    assert is_text_likely(b"#!/usr/bin/env python\nprint('hi')\n")
