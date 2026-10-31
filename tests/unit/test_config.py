"""Unit tests for configuration."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from github_to_docs.config import Settings, validate_credentials


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Yield with OpenRouter env vars removed, then restore."""
    before = {
        k: os.environ.get(k)
        for k in (
            "OPENROUTER_API_KEY",
            "OPENROUTER_MODEL",
            "OPENROUTER_BASE_URL",
            "GITHUB_TOKEN",
            "DOCS_OUTPUT_DIR",
        )
    }
    for k in before:
        os.environ.pop(k, None)
    yield
    for k, v in before.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_settings_defaults(clean_env: None) -> None:
    s = Settings()
    assert s.openrouter_api_key is None
    assert s.openrouter_model == "openrouter/auto"
    assert s.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert s.github_token is None
    assert s.docs_output_dir == "output"
    assert s.max_repository_size_mb == 100
    assert s.max_files_to_analyze == 200
    assert s.max_file_size_kb == 512
    assert s.max_revision_attempts == 2
    assert s.request_timeout_seconds == 30


def test_settings_from_env(clean_env: None) -> None:
    os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
    os.environ["OPENROUTER_MODEL"] = "openrouter/test-model"
    os.environ["MAX_FILES_TO_ANALYZE"] = "50"
    s = Settings()
    assert s.openrouter_api_key == "sk-or-test"
    assert s.openrouter_model == "openrouter/test-model"
    assert s.max_files_to_analyze == 50


def test_validate_credentials_missing(clean_env: None) -> None:
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        validate_credentials()


def test_validate_credentials_present(clean_env: None) -> None:
    os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
    # Should not raise.
    validate_credentials()


def test_settings_extra_fields_ignored(clean_env: None) -> None:
    os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
    os.environ["UNKNOWN_SETTING"] = "should-be-ignored"
    s = Settings()
    assert s.openrouter_api_key == "sk-or-test"
