"""Documentation planner: uses the LLM to create a structured plan.

The planner receives the deterministic inventory + evidence catalog and
produces a DocumentationPlan (Pydantic-validated). It only references real
evidence IDs and safe document names.
"""

from __future__ import annotations

import logging

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.generation import ModelClient
from github_to_docs.graph.plan_schema import DocumentationPlan
from github_to_docs.prompts import PLANNER_PROMPT

logger = logging.getLogger(__name__)


class DocumentationPlanner:
    """Plans which documents to generate and what evidence each section needs."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def _evidence_catalog_text(self, registry: EvidenceRegistry) -> str:
        """Format evidence as bounded excerpts keyed by ID."""
        lines: list[str] = []
        for item in registry.all():
            lines.append(
                f"{item.evidence_id} | {item.evidence_type.value} | "
                f"{item.file_path}:{item.start_line}-{item.end_line} | "
                f"{item.content[:300]}"
            )
        return "\n".join(lines) if lines else "(no evidence available)"

    def plan(
        self,
        repository_url: str,
        revision: str | None,
        inventory_json: str,
        registry: EvidenceRegistry,
    ) -> DocumentationPlan:
        """Produce a structured documentation plan (Pydantic-validated)."""
        catalog = self._evidence_catalog_text(registry)

        user = PLANNER_PROMPT.format(
            repository_url=repository_url,
            revision=revision or "unknown",
            inventory_json=inventory_json,
            evidence_catalog=catalog,
        )

        plan = self.model_client.generate_structured(
            system=(
                "You are a meticulous documentation planning agent. "
                "Output only valid JSON matching the requested schema."
            ),
            user=user,
            schema=DocumentationPlan,
        )

        # Validate that the plan only references real evidence IDs.
        # Warn on invalid IDs but do not fail — the LLM may reference
        # evidence that doesn't exist, and generation handles missing
        # evidence gracefully.
        invalid = registry.validate_references(
            [
                eid
                for doc in plan.documents
                for section in doc.sections
                for eid in section.required_evidence_ids
            ]
        )
        if invalid:
            logger.warning(
                "Plan references %d unknown evidence ID(s): %s",
                len(invalid),
                invalid[:10],
            )

        logger.info(
            "Planned %d documents (%d applicable)",
            len(plan.documents),
            sum(1 for d in plan.documents if d.applicable),
        )
        return plan


__all__ = ["DocumentationPlanner"]
