"""Unit tests for documentation verification (offline, mocked model)."""

from __future__ import annotations

from typing import Any

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.models import FindingSeverity
from github_to_docs.verification import DocumentVerifier


class FakeModelClient:
    def __init__(self, response: str = "[]") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate_text(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response

    def generate_structured(self, system: str, user: str, schema: type[Any]) -> Any:
        raise NotImplementedError


def _registry() -> EvidenceRegistry:
    reg = EvidenceRegistry(repository_revision="rev1")
    reg.add(
        __import__("github_to_docs.models", fromlist=["EvidenceType"]).EvidenceType.source_code,
        "src/main.py",
        "def foo():\n    pass\n",
        start_line=1,
        end_line=2,
        symbol_name="foo",
    )
    return reg


def test_detects_secret_leakage() -> None:
    reg = _registry()
    verifier = DocumentVerifier(FakeModelClient())
    findings = verifier.verify_deterministic(
        document_name="README.md",
        section_title="Setup",
        content="API_KEY = sk-live-1234567890abcdef.",
        inventory_files=["src/main.py"],
        evidence_registry=reg,
    )
    severe = [f for f in findings if f.severity == FindingSeverity.severe]
    assert len(severe) >= 1
    assert "secret" in severe[0].claim.lower()


def test_detects_placeholder() -> None:
    reg = _registry()
    verifier = DocumentVerifier(FakeModelClient())
    findings = verifier.verify_deterministic(
        document_name="README.md",
        section_title="Usage",
        content="Run `python {COMMAND}` to start. [TODO] add details.",
        inventory_files=["src/main.py"],
        evidence_registry=reg,
    )
    assert any("TODO" in f.claim for f in findings)


def test_detects_unknown_evidence_citation() -> None:
    reg = _registry()
    verifier = DocumentVerifier(FakeModelClient())
    findings = verifier.verify_deterministic(
        document_name="README.md",
        section_title="Overview",
        content="See [ev:nonexistent:file.py:1] for details.",
        inventory_files=["src/main.py"],
        evidence_registry=reg,
    )
    assert any("unknown evidence" in f.claim for f in findings)


def test_detects_referenced_file_not_in_inventory() -> None:
    reg = _registry()
    verifier = DocumentVerifier(FakeModelClient())
    findings = verifier.verify_deterministic(
        document_name="README.md",
        section_title="Setup",
        content="Edit `config/missing.yml` to configure.",
        inventory_files=["src/main.py", "README.md"],
        evidence_registry=reg,
    )
    assert any("missing.yml" in f.claim for f in findings)


def test_no_findings_for_clean_content() -> None:
    reg = _registry()
    verifier = DocumentVerifier(FakeModelClient())
    findings = verifier.verify_deterministic(
        document_name="README.md",
        section_title="Overview",
        content="This project uses `src/main.py`. See [ev:source_code:src/main.py:foo:1-2].",
        inventory_files=["src/main.py", "README.md"],
        evidence_registry=reg,
    )
    assert findings == []


def test_has_serious_findings() -> None:
    from github_to_docs.models import VerificationFinding

    error_finding = VerificationFinding(
        severity=FindingSeverity.error,
        document="README.md",
        section="S",
        claim="c",
        evidence_ids=[],
        failure_reason="r",
        recommended_correction="fix",
    )
    info_finding = VerificationFinding(
        severity=FindingSeverity.info,
        document="README.md",
        section="S",
        claim="c",
        evidence_ids=[],
        failure_reason="r",
        recommended_correction="fix",
    )
    assert DocumentVerifier.has_serious_findings([error_finding]) is True
    assert DocumentVerifier.has_serious_findings([info_finding]) is False
    assert DocumentVerifier.has_serious_findings([]) is False


def test_llm_verification_returns_empty_on_bad_json() -> None:
    reg = _registry()
    fake = FakeModelClient(response="not json at all")
    verifier = DocumentVerifier(fake)
    findings = verifier.verify_llm(
        document_name="README.md",
        section_title="S",
        content="some content",
        evidence_registry=reg,
        evidence_ids=[],
    )
    assert findings == []
    assert fake.calls
