"""Security and reliability tests (offline, no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from github_to_docs.config import validate_credentials
from github_to_docs.evidence.redaction import redact_secrets
from github_to_docs.services import AppService


class _RaisingGraph:
    """Fake compiled graph whose invoke always raises."""

    def compile(self):
        return self

    def invoke(self, initial_state):
        raise RuntimeError("graph exploded")


def test_validate_credentials_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        validate_credentials()


def test_validate_credentials_no_raise_when_key_present(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    validate_credentials()  # should not raise


def test_validate_credentials_nim_missing(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="NIM_API_KEY"):
        validate_credentials(provider="nim")


def test_validate_credentials_nim_present(monkeypatch):
    monkeypatch.setenv("NIM_API_KEY", "nim-test-key")
    validate_credentials(provider="nim")  # should not raise


def test_validate_credentials_defaults_to_settings_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "nim")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    # Reload settings to pick up env - create fresh Settings inside call.
    with pytest.raises(RuntimeError, match="NIM_API_KEY"):
        validate_credentials()


def test_app_service_never_raises_on_missing_credentials(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    svc = AppService()
    report = svc.generate("https://github.com/owner/repo")
    assert report.status == "failed"
    assert report.failed_checks


def test_app_service_never_raises_on_graph_exception(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    def fake_build_graph(planner, generator, verifier):
        return _RaisingGraph()

    monkeypatch.setattr(
        "github_to_docs.services.build_graph", fake_build_graph
    )
    svc = AppService(
        planner=SimpleNamespace(),
        generator=SimpleNamespace(),
        verifier=SimpleNamespace(),
    )
    report = svc.generate("https://github.com/owner/repo")
    assert report.status == "failed"
    assert "graph exploded" in report.failed_checks


def test_app_service_returns_report_on_success(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    class FakeReport:
        status = "completed"
        run_id = "run-1"
        repository_url = "https://github.com/owner/repo"
        repository_revision = "abc123"
        output_paths = [str(tmp_path / "README.md")]
        failed_checks = []
        passed_checks = []
        findings = []
        skipped_files = []
        token_usage = {}

    def fake_build_graph(planner, generator, verifier):
        return SimpleNamespace(
            compile=lambda: SimpleNamespace(
                invoke=lambda state: {"run_report": FakeReport()}
            )
        )

    monkeypatch.setattr(
        "github_to_docs.services.build_graph", fake_build_graph
    )
    svc = AppService(
        output_dir=str(tmp_path),
        planner=SimpleNamespace(),
        generator=SimpleNamespace(),
        verifier=SimpleNamespace(),
    )
    report = svc.generate("https://github.com/owner/repo")
    assert report.status == "completed"
    assert report.run_id == "run-1"


def test_redacts_bare_long_hex_token():
    text = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
    redacted, was_redacted = redact_secrets(text)
    assert was_redacted
    assert "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" not in redacted
    assert "[REDACTED]" in redacted


def test_redacted_value_never_reproduced():
    secret = "sk-live-1234567890abcdef"
    text = f'password = "{secret}"'
    redacted, _ = redact_secrets(text)
    assert secret not in redacted
