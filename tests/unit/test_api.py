"""Unit tests for the FastAPI API (offline, no network)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from github_to_docs.api.main import app
from github_to_docs.models import RunStatus
from github_to_docs.services import AppService


class FakeAppService(AppService):
    """AppService that returns a fixed report for API testing."""

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
        from github_to_docs.models import FindingSeverity, VerificationFinding

        class R:
            run_id = "run-1"
            repository_url = repo_url
            repository_revision = None
            status = RunStatus.failed
            output_paths = []
            passed_checks = []
            failed_checks = ["boom"]
            findings = [
                VerificationFinding(
                    severity=FindingSeverity.error,
                    document="README.md",
                    section="Overview",
                    claim="bad",
                    evidence_ids=[],
                    failure_reason="unsupported",
                    recommended_correction="fix",
                )
            ]
            skipped_files = []

        return R()


class _Report:
    def __init__(self, status=RunStatus.completed, run_id="run-1", output_paths=None):
        self.status = status
        self.run_id = run_id
        self.repository_url = "https://github.com/owner/repo"
        self.repository_revision = "abc123"
        self.output_paths = output_paths or ["/tmp/repo/run-1/README.md"]
        self.passed_checks = ["structure validated"]
        self.failed_checks = []
        self.findings = []
        self.skipped_files = []


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_generate_success(monkeypatch):
    report = _Report()
    monkeypatch.setattr(
        "github_to_docs.api.main.AppService", lambda **kw: FakeAppService(report=report)
    )
    response = client.post(
        "/v1/documentation/generate",
        json={"repo_url": "https://github.com/owner/repo"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == "run-1"
    assert body["repository_url"] == "https://github.com/owner/repo"
    assert body["status"] == "completed"
    assert body["output_paths"] == ["/tmp/repo/run-1/README.md"]
    assert body["passed_checks"] == ["structure validated"]
    assert body["failed_checks"] == []
    assert body["findings_count"] == 0


def test_generate_failure_returns_200(monkeypatch):
    report = _Report(status=RunStatus.failed, output_paths=[])
    report.failed_checks = ["boom"]
    monkeypatch.setattr(
        "github_to_docs.api.main.AppService", lambda **kw: FakeAppService(report=report)
    )
    response = client.post(
        "/v1/documentation/generate",
        json={"repo_url": "https://github.com/owner/repo"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_checks"] == ["boom"]


def test_generate_findings_serialized(monkeypatch):
    from github_to_docs.models import FindingSeverity, VerificationFinding

    report = _Report()
    report.findings = [
        VerificationFinding(
            severity=FindingSeverity.error,
            document="README.md",
            section="Overview",
            claim="bad",
            evidence_ids=[],
            failure_reason="unsupported",
            recommended_correction="fix",
        )
    ]
    monkeypatch.setattr(
        "github_to_docs.api.main.AppService", lambda **kw: FakeAppService(report=report)
    )
    response = client.post(
        "/v1/documentation/generate",
        json={"repo_url": "https://github.com/owner/repo"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["findings_count"] == 1
    assert body["findings"][0]["severity"] == "error"
    assert body["findings"][0]["claim"] == "bad"


def test_generate_rejects_missing_repo_url():
    response = client.post("/v1/documentation/generate", json={})
    assert response.status_code == 422  # Pydantic validation
