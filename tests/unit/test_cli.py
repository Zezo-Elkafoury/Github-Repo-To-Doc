"""Unit tests for the CLI (offline, no network)."""

from __future__ import annotations

from typer.testing import CliRunner

from github_to_docs.cli.main import app
from github_to_docs.models import RunStatus
from github_to_docs.services import AppService


class FakeAppService(AppService):
    """AppService that bypasses graph execution for CLI testing."""

    def __init__(self, report=None, should_fail=False) -> None:
        super().__init__()
        self._report = report
        self.should_fail = should_fail
        self.called_repo_url: str | None = None

    def generate(self, repo_url: str):
        self.called_repo_url = repo_url
        if self.should_fail:
            return self._error_report(repo_url)
        return self._report

    def _error_report(self, repo_url: str):
        from github_to_docs.models import RunStatus

        return type(
            "Report",
            (),
            {
                "status": RunStatus.failed,
                "run_id": "run-1",
                "repository_url": repo_url,
                "repository_revision": None,
                "output_paths": [],
                "failed_checks": ["boom"],
                "findings": [],
                "passed_checks": [],
                "skipped_files": [],
            },
        )()


class _Report:
    def __init__(self, status=RunStatus.completed, run_id="run-1", output_paths=None):
        self.status = status
        self.run_id = run_id
        self.repository_url = "https://github.com/owner/repo"
        self.repository_revision = "abc123"
        self.output_paths = output_paths or ["/tmp/repo/run-1/README.md"]
        self.failed_checks = []
        self.passed_checks = []
        self.findings = []
        self.skipped_files = []


runner = CliRunner(mix_stderr=False)


def test_cli_generate_success(monkeypatch):
    report = _Report()
    monkeypatch.setattr(
        "github_to_docs.cli.main.AppService", lambda **kw: FakeAppService(report=report)
    )
    result = runner.invoke(app, ["https://github.com/owner/repo"], catch_exceptions=False)
    assert result.exit_code == 0, result.output + result.stderr
    assert "Generation complete." in result.output
    assert report.run_id in result.output


def test_cli_generate_failure(monkeypatch):
    report = _Report(status="failed", output_paths=[])
    report.failed_checks = ["OPENROUTER_API_KEY is not set"]
    monkeypatch.setattr(
        "github_to_docs.cli.main.AppService", lambda **kw: FakeAppService(report=report)
    )
    result = runner.invoke(app, ["https://github.com/owner/repo"], catch_exceptions=False)
    assert result.exit_code == 1, result.output + result.stderr
    assert "Generation failed." in result.output + result.stderr
    assert "OPENROUTER_API_KEY is not set" in result.output + result.stderr


def test_cli_generate_uses_options(monkeypatch):
    captured = {}

    class CapService(FakeAppService):
        def __init__(self, output_dir=None, model=None, provider=None):
            captured["output_dir"] = output_dir
            captured["model"] = model
            captured["provider"] = provider
            super().__init__(report=_Report())

    monkeypatch.setattr("github_to_docs.cli.main.AppService", CapService)
    result = runner.invoke(
        app,
        [
            "https://github.com/owner/repo",
            "--output",
            "/custom/out",
            "--model",
            "custom-model",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output + result.stderr
    assert captured["output_dir"] == "/custom/out"
    assert captured["model"] == "custom-model"
    assert captured["provider"] is None


def test_cli_generate_uses_provider(monkeypatch):
    captured = {}

    class CapService(FakeAppService):
        def __init__(self, output_dir=None, model=None, provider=None):
            captured["output_dir"] = output_dir
            captured["model"] = model
            captured["provider"] = provider
            super().__init__(report=_Report())

    monkeypatch.setattr("github_to_docs.cli.main.AppService", CapService)
    result = runner.invoke(
        app,
        [
            "https://github.com/owner/repo",
            "--provider",
            "nim",
            "--model",
            "meta/llama-3.1-8b-instruct",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output + result.stderr
    assert captured["provider"] == "nim"
    assert captured["model"] == "meta/llama-3.1-8b-instruct"


def test_cli_generate_warnings_displayed(monkeypatch):
    report = _Report()
    report.failed_checks = ["Warning: something minor"]
    monkeypatch.setattr(
        "github_to_docs.cli.main.AppService", lambda **kw: FakeAppService(report=report)
    )
    result = runner.invoke(app, ["https://github.com/owner/repo"], catch_exceptions=False)
    assert result.exit_code == 0, result.output + result.stderr
    assert "Warnings/errors:" in result.output
