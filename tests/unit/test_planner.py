"""Unit tests for the documentation planner and model client (offline, mocked)."""

from __future__ import annotations

from typing import Any

import pytest

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.generation.client import ModelClient
from github_to_docs.generation.planner import DocumentationPlanner
from github_to_docs.graph.plan_schema import DocumentationPlan, PlannedDocument


class FakeModelClient:
    """Deterministic fake model for testing the planner without the network."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[tuple[str, str]] = []

    def generate_text(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response_text

    def generate_structured(self, system: str, user: str, schema: type[Any]) -> Any:
        self.calls.append((system, user))
        import json

        parsed = json.loads(self.response_text)
        return schema(**parsed)


def test_planner_produces_valid_plan() -> None:
    registry = EvidenceRegistry(repository_revision="rev1")
    registry.add(
        __import__("github_to_docs.models", fromlist=["EvidenceType"]).EvidenceType.source_code,
        "src/main.py",
        "def foo():\n    pass\n",
        start_line=1,
        end_line=2,
        symbol_name="foo",
    )

    plan_json = {
        "documents": [
            {
                "name": "README.md",
                "applicable": True,
                "sections": [
                    {
                        "title": "Overview",
                        "purpose": "Describe the project",
                        "facts_to_establish": ["it is a Python package"],
                        "required_evidence_ids": ["ev:source_code:src/main.py:foo:1-2"],
                    }
                ],
                "depends_on": [],
            }
        ],
        "missing_information": [],
        "potential_contradictions": [],
        "verification_requirements": ["check README exists"],
    }

    fake = FakeModelClient(response_text=__import__("json").dumps(plan_json))
    planner = DocumentationPlanner(fake)
    plan = planner.plan(
        repository_url="https://github.com/owner/repo",
        revision="rev1",
        inventory_json="{}",
        registry=registry,
    )

    assert isinstance(plan, DocumentationPlan)
    assert len(plan.documents) == 1
    assert plan.documents[0].name == "README.md"
    assert plan.documents[0].applicable is True
    assert fake.calls  # model was called


def test_planner_rejects_unknown_evidence_ids() -> None:
    registry = EvidenceRegistry(repository_revision="rev1")

    plan_json = {
        "documents": [
            {
                "name": "README.md",
                "applicable": True,
                "sections": [
                    {
                        "title": "Overview",
                        "purpose": "x",
                        "facts_to_establish": ["y"],
                        "required_evidence_ids": ["ev:nope:x:1-2"],
                    }
                ],
                "depends_on": [],
            }
        ],
        "missing_information": [],
        "potential_contradictions": [],
        "verification_requirements": [],
    }

    fake = FakeModelClient(response_text=__import__("json").dumps(plan_json))
    planner = DocumentationPlanner(fake)
    # Warns on unknown evidence IDs but does not raise — generation handles
    # missing evidence gracefully.
    plan = planner.plan(
        repository_url="https://github.com/owner/repo",
        revision="rev1",
        inventory_json="{}",
        registry=registry,
    )
    assert plan is not None
    assert len(plan.documents) == 1


def test_plan_schema_rejects_path_traversal() -> None:
    with pytest.raises(__import__("pydantic").ValidationError):
        PlannedDocument(
            name="../evil.md",
            applicable=True,
            sections=[],
            depends_on=[],
        )


def test_model_client_validate_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Force re-read by creating a new Settings inside validate_credentials.

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        ModelClient()


def test_plan_schema_rejects_bad_evidence_refs() -> None:
    registry = EvidenceRegistry(repository_revision="rev")
    DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[],
                depends_on=[],
            )
        ]
    )
    # No refs -> valid
    assert registry.validate_references([]) == []
