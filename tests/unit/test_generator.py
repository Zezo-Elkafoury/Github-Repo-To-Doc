"""Unit tests for document generation (offline, mocked model)."""

from __future__ import annotations

from typing import Any

import pytest

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.generation.generator import DocumentGenerator
from github_to_docs.graph.plan_schema import DocumentSection, PlannedDocument


class FakeModelClient:
    def __init__(self, response: str = "# Section content\n") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate_text(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response

    def generate_structured(self, system: str, user: str, schema: type[Any]) -> Any:
        raise NotImplementedError


def _registry_with_evidence() -> EvidenceRegistry:
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


def test_generate_section_cites_evidence() -> None:
    reg = _registry_with_evidence()
    fake = FakeModelClient(response="# Overview\n\nSee [ev:source_code:src/main.py:foo:1-2]\n")
    gen = DocumentGenerator(fake)

    section = DocumentSection(
        title="Overview",
        purpose="Describe the project",
        facts_to_establish=["it has a foo function"],
        required_evidence_ids=["ev:source_code:src/main.py:foo:1-2"],
    )

    content = gen.generate_section(document_name="README.md", section=section, registry=reg)

    assert "ev:source_code:src/main.py:foo:1-2" in content
    assert len(fake.calls) == 1


def test_generate_section_rejects_empty_output() -> None:
    reg = _registry_with_evidence()
    fake = FakeModelClient(response="")
    gen = DocumentGenerator(fake)

    section = DocumentSection(
        title="Overview",
        purpose="x",
        facts_to_establish=[],
        required_evidence_ids=[],
    )

    with pytest.raises(ValueError, match="empty"):
        gen.generate_section(document_name="README.md", section=section, registry=reg)


def test_generate_document_skips_inapplicable() -> None:
    reg = _registry_with_evidence()
    fake = FakeModelClient()
    gen = DocumentGenerator(fake)

    doc = PlannedDocument(
        name="API.md",
        applicable=False,
        reason_if_not_applicable="no HTTP routes found",
        sections=[
            DocumentSection(
                title="Endpoints",
                purpose="x",
                facts_to_establish=[],
                required_evidence_ids=[],
            )
        ],
        depends_on=[],
    )

    result = gen.generate_document(doc, reg)

    assert result == {}
    assert fake.calls == []  # model not called for inapplicable doc


def test_generate_document_all_sections() -> None:
    reg = _registry_with_evidence()
    fake = FakeModelClient(response="# Section\n")
    gen = DocumentGenerator(fake)

    doc = PlannedDocument(
        name="README.md",
        applicable=True,
        sections=[
            DocumentSection(
                title="Overview",
                purpose="x",
                facts_to_establish=[],
                required_evidence_ids=["ev:source_code:src/main.py:foo:1-2"],
            ),
            DocumentSection(
                title="Setup",
                purpose="y",
                facts_to_establish=[],
                required_evidence_ids=[],
            ),
        ],
        depends_on=[],
    )

    result = gen.generate_document(doc, reg)

    assert set(result.keys()) == {"Overview", "Setup"}
    assert len(fake.calls) == 2
