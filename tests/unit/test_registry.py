"""Unit tests for the evidence registry (offline, no network)."""

import pytest

from github_to_docs.evidence.registry import (
    EvidenceRegistry,
    InvalidEvidenceReferenceError,
)
from github_to_docs.models import EvidenceType


def _registry() -> EvidenceRegistry:
    return EvidenceRegistry(repository_revision="rev123")


def test_add_and_get() -> None:
    reg = _registry()
    item = reg.add(
        EvidenceType.source_code,
        "src/main.py",
        "def foo():\n    pass\n",
        start_line=1,
        end_line=2,
        symbol_name="foo",
    )
    assert item.evidence_id == "ev:source_code:src/main.py:foo:1-2"
    assert item.repository_revision == "rev123"
    assert item.file_path == "src/main.py"
    assert item.symbol_name == "foo"
    assert (
        item.content_hash == __import__("hashlib").sha256(item.content.encode("utf-8")).hexdigest()
    )

    fetched = reg.get(item.evidence_id)
    assert fetched.evidence_id == item.evidence_id


def test_invalid_reference_rejected() -> None:
    reg = _registry()
    with pytest.raises(InvalidEvidenceReferenceError):
        reg.get("ev:source_code:nope.py:1-2")


def test_validate_references() -> None:
    reg = _registry()
    item = reg.add(EvidenceType.configuration, "README.md", "# hi")
    valid = reg.validate_references([item.evidence_id, "ev:nope:x:1-2"])
    assert valid == ["ev:nope:x:1-2"]


def test_evidence_id_collision_rejected() -> None:
    reg = _registry()
    reg.add(EvidenceType.source_code, "a.py", "x", start_line=1, end_line=1)
    with pytest.raises(__import__("builtins").RuntimeError):
        reg.add(EvidenceType.source_code, "a.py", "y", start_line=1, end_line=1)


def test_bounding_truncates_long_excerpt() -> None:
    reg = _registry()
    # Text with spaces won't match the secret token pattern, so it reaches
    # the bounding step intact.
    long_text = ("word " * 2000).strip()  # ~10000 chars
    item = reg.add(EvidenceType.documentation, "README.md", long_text)
    assert len(item.content) <= 4000
    assert "truncated" in item.content


def test_by_file_by_type_by_symbol() -> None:
    reg = _registry()
    reg.add(
        EvidenceType.source_code,
        "src/a.py",
        "def foo():\n    pass",
        start_line=1,
        end_line=2,
        symbol_name="foo",
    )
    reg.add(
        EvidenceType.source_code,
        "src/a.py",
        "def bar():\n    pass",
        start_line=5,
        end_line=6,
        symbol_name="bar",
    )
    reg.add(EvidenceType.test, "tests/test_a.py", "assert True", start_line=1, end_line=1)

    assert len(reg.by_file("src/a.py")) == 2
    assert len(reg.by_file("tests/test_a.py")) == 1
    assert len(reg.by_symbol("foo")) == 1
    assert len(reg.by_type(EvidenceType.source_code)) == 2
    assert len(reg.by_type(EvidenceType.test)) == 1
    assert len(reg) == 3


def test_make_evidence_id_line_range() -> None:
    eid = EvidenceRegistry.make_evidence_id(EvidenceType.api_declaration, "app/main.py", 4, 6)
    assert eid == "ev:api_declaration:app/main.py:4-6"


def test_make_evidence_id_single_line() -> None:
    eid = EvidenceRegistry.make_evidence_id(EvidenceType.configuration, ".env.example", 3)
    assert eid == "ev:configuration:.env.example:3"
