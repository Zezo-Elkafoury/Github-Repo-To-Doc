"""Document generation: one section at a time, grounded in evidence."""

from __future__ import annotations

import logging

from github_to_docs.evidence.registry import EvidenceRegistry, InvalidEvidenceReferenceError
from github_to_docs.generation.client import ModelClient
from github_to_docs.graph.plan_schema import (
    DocumentSection,
    PlannedDocument,
)
from github_to_docs.prompts import GENERATION_PROMPT

logger = logging.getLogger(__name__)


class DocumentGenerator:
    """Generates one document section at a time from selected evidence.

    Each generation call receives only the evidence relevant to that section,
    never the whole repository. Output is Markdown with evidence citations.
    """

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def _evidence_excerpts(self, registry: EvidenceRegistry, evidence_ids: list[str]) -> str:
        """Format selected evidence as excerpts keyed by ID."""
        lines: list[str] = []
        for eid in evidence_ids:
            try:
                item = registry.get(eid)
            except (KeyError, InvalidEvidenceReferenceError):
                lines.append(f"{eid}: [EVIDENCE NOT FOUND IN REGISTRY]")
                continue
            lines.append(
                f"[{eid}] ({item.file_path}:{item.start_line}-{item.end_line})\n{item.content}"
            )
        return "\n\n---\n\n".join(lines) if lines else "(no evidence provided)"

    def generate_section(
        self,
        document_name: str,
        section: DocumentSection,
        registry: EvidenceRegistry,
        audience: str = "developers and contributors",
    ) -> str:
        """Generate a single Markdown section grounded in evidence."""
        evidence_text = self._evidence_excerpts(registry, section.required_evidence_ids)

        user = GENERATION_PROMPT.format(
            document_name=document_name,
            section_title=section.title,
            section_purpose=section.purpose,
            facts="\n".join(f"- {f}" for f in section.facts_to_establish) or "(none specified)",
            evidence_excerpts=evidence_text,
            audience=audience,
        )

        content = self.model_client.generate_text(
            system=(
                "You are a careful technical writer. Ground every claim in the "
                "provided evidence, cite evidence IDs, and mark uncertainty."
            ),
            user=user,
        )

        # Basic validation: non-empty output.
        if not content or not content.strip():
            raise ValueError(f"Generated empty section '{section.title}' for {document_name}")

        logger.info(
            "Generated section '%s' for %s (%d chars)",
            section.title,
            document_name,
            len(content),
        )
        return content.strip()

    def generate_document(
        self,
        planned_doc: PlannedDocument,
        registry: EvidenceRegistry,
        audience: str = "developers and contributors",
    ) -> dict[str, str]:
        """Generate all sections of a single document.

        Returns a dict mapping section title -> Markdown content.
        Skips inapplicable documents (returns empty dict).
        """
        if not planned_doc.applicable:
            logger.info(
                "Skipping inapplicable document %s: %s",
                planned_doc.name,
                planned_doc.reason_if_not_applicable or "not applicable",
            )
            return {}

        sections: dict[str, str] = {}
        for section in planned_doc.sections:
            sections[section.title] = self.generate_section(
                document_name=planned_doc.name,
                section=section,
                registry=registry,
                audience=audience,
            )
        return sections
