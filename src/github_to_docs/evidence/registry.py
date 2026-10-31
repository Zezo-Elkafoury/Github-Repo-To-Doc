"""Evidence registry: bounded excerpts with traceable provenance.

Every evidence item refers to a file actually included in the analyzed
revision (or to repository metadata). The registry supports adding, retrieving
by ID, and querying by file / symbol / type. Invalid evidence references are
rejected.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from github_to_docs.evidence.redaction import redact_secrets
from github_to_docs.models import EvidenceItem, EvidenceType

# Maximum excerpt length stored as evidence content (bounded to avoid
# excessive context consumption).
MAX_EXCERPT_CHARS = 4000


class EvidenceRegistryError(RuntimeError):
    """Raised for evidence registry failures."""


class InvalidEvidenceReferenceError(EvidenceRegistryError):
    """Raised when an evidence ID does not exist in the registry."""


@dataclass
class EvidenceRegistry:
    """Queryable store of evidence items with provenance."""

    repository_revision: str
    _items: dict[str, EvidenceItem] = field(default_factory=dict)
    _by_file: dict[str, list[str]] = field(default_factory=dict)
    _by_symbol: dict[str, list[str]] = field(default_factory=dict)
    _by_type: dict[EvidenceType, list[str]] = field(default_factory=dict)

    @staticmethod
    def make_evidence_id(
        evidence_type: EvidenceType,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        symbol_name: str | None = None,
    ) -> str:
        """Build a stable, unique evidence ID.

        Includes ``symbol_name`` when provided so that multiple evidence items
        on the same file/line (e.g. a config file and an env var reference)
        do not collide.
        """
        segment = file_path
        if symbol_name:
            segment += f":{symbol_name}"
        if start_line is not None:
            segment += f":{start_line}"
            if end_line is not None and end_line != start_line:
                segment += f"-{end_line}"
        return f"ev:{evidence_type.value}:{segment}"

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _bound(self, content: str) -> str:
        """Bound an excerpt to MAX_EXCERPT_CHARS, marking truncation."""
        marker = "\n... [excerpt truncated for context bounds]"
        if len(content) <= MAX_EXCERPT_CHARS:
            return content
        # Reserve room for the truncation marker so total stays within limit.
        keep = MAX_EXCERPT_CHARS - len(marker)
        if keep < 1:
            keep = 1
        return content[:keep] + marker

    def add(
        self,
        evidence_type: EvidenceType,
        file_path: str,
        content: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        symbol_name: str | None = None,
        redact_secrets_: bool = True,
    ) -> EvidenceItem:
        """Add an evidence item and return it.

        Raises:
            EvidenceRegistryError: if an evidence ID collides.
        """
        evidence_id = self.make_evidence_id(
            evidence_type, file_path, start_line, end_line, symbol_name=symbol_name
        )
        if evidence_id in self._items:
            raise EvidenceRegistryError(f"Evidence ID already exists: {evidence_id}")

        excerpt, was_redacted = redact_secrets(content) if redact_secrets_ else (content, False)
        excerpt = self._bound(excerpt)

        item = EvidenceItem(
            evidence_id=evidence_id,
            repository_revision=self.repository_revision,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            symbol_name=symbol_name,
            evidence_type=evidence_type,
            content=excerpt,
            content_hash=self._content_hash(excerpt),
        )

        self._items[evidence_id] = item
        self._by_file.setdefault(file_path, []).append(evidence_id)
        if symbol_name:
            self._by_symbol.setdefault(symbol_name, []).append(evidence_id)
        self._by_type.setdefault(evidence_type, []).append(evidence_id)

        if was_redacted:
            # Record that redaction occurred without revealing the value.
            pass

        return item

    def get(self, evidence_id: str) -> EvidenceItem:
        """Retrieve an evidence item by ID.

        Raises:
            InvalidEvidenceReferenceError: if the ID is not in the registry.
        """
        if evidence_id not in self._items:
            raise InvalidEvidenceReferenceError(f"Unknown evidence reference: {evidence_id}")
        return self._items[evidence_id]

    def validate_reference(self, evidence_id: str) -> bool:
        """Return True if the evidence ID exists in the registry."""
        return evidence_id in self._items

    def validate_references(self, evidence_ids: list[str]) -> list[str]:
        """Return a list of invalid evidence IDs (empty if all valid)."""
        return [eid for eid in evidence_ids if not self.validate_reference(eid)]

    def by_file(self, file_path: str) -> list[EvidenceItem]:
        return [self._items[eid] for eid in self._by_file.get(file_path, [])]

    def by_symbol(self, symbol_name: str) -> list[EvidenceItem]:
        return [self._items[eid] for eid in self._by_symbol.get(symbol_name, [])]

    def by_type(self, evidence_type: EvidenceType) -> list[EvidenceItem]:
        return [self._items[eid] for eid in self._by_type.get(evidence_type, [])]

    def all(self) -> list[EvidenceItem]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)
