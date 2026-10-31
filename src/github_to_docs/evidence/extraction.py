"""Evidence extraction from a deterministic repository inventory.

Builds :class:`EvidenceItem` records from acquired file contents and the
static inventory. Every excerpt carries provenance (revision, file path, line
range, symbol) and is bounded. Likely secrets are redacted.
"""

from __future__ import annotations

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.models import EvidenceType
from github_to_docs.repository.acquisition import AcquisitionResult
from github_to_docs.repository.inventory import (
    RepositoryInventory,
)


def extract_evidence(
    result: AcquisitionResult,
    inventory: RepositoryInventory,
) -> EvidenceRegistry:
    """Extract evidence from an acquisition result and inventory.

    Each evidence item refers to a real file in the analyzed revision with an
    accurate line range where available.
    """
    registry = EvidenceRegistry(repository_revision=result.revision or "unknown")

    content_by_path = {fc.path: fc.content.decode("utf-8", errors="replace") for fc in result.files}

    # --- File-level evidence (manifests, docs, config) ------------------- #
    for entry in inventory.files:
        path = entry.path
        text = content_by_path.get(path, "")

        if entry.is_manifest:
            registry.add(
                EvidenceType.dependency_manifest,
                path,
                text,
                start_line=1,
                end_line=entry.line_count or 1,
            )
        if entry.is_documentation:
            registry.add(
                EvidenceType.documentation,
                path,
                text,
                start_line=1,
                end_line=entry.line_count or 1,
            )
        if entry.is_config:
            registry.add(
                EvidenceType.configuration,
                path,
                text,
                start_line=1,
                end_line=entry.line_count or 1,
            )
        if entry.is_test:
            registry.add(
                EvidenceType.test,
                path,
                text,
                start_line=1,
                end_line=entry.line_count or 1,
            )

    # --- Code symbols --------------------------------------------------- #
    for symbol in inventory.symbols:
        text = content_by_path.get(symbol.file_path, "")
        start = symbol.line or 1
        # Bounded excerpt around the symbol (a few lines).
        excerpt = _symbol_excerpt(text, start)
        registry.add(
            EvidenceType.source_code,
            symbol.file_path,
            excerpt,
            start_line=start,
            end_line=start,
            symbol_name=symbol.name,
        )

    # --- Route declarations -------------------------------------------- #
    for route in inventory.routes:
        text = content_by_path.get(route.file_path, "")
        start = route.line or 1
        excerpt = _line_excerpt(text, start)
        registry.add(
            EvidenceType.api_declaration,
            route.file_path,
            excerpt,
            start_line=start,
            end_line=start,
            symbol_name=f"{route.method} {route.path}",
        )

    # --- Env var references -------------------------------------------- #
    for ev in inventory.env_vars:
        text = content_by_path.get(ev.file_path, "")
        start = ev.line or 1
        excerpt = _line_excerpt(text, start)
        registry.add(
            EvidenceType.configuration,
            ev.file_path,
            excerpt,
            start_line=start,
            end_line=start,
            symbol_name=ev.name,
        )

    # --- CI workflows --------------------------------------------------- #
    for path in inventory.ci_workflows:
        text = content_by_path.get(path, "")
        registry.add(
            EvidenceType.ci_workflow,
            path,
            text,
            start_line=1,
            end_line=1,
        )

    # --- Repository metadata ------------------------------------------ #
    registry.add(
        EvidenceType.repository_metadata,
        ".repository-metadata",
        f"repository_url={inventory.repository_url}\n"
        f"revision={inventory.revision or 'unknown'}\n"
        f"default_branch={inventory.default_branch or 'unknown'}\n"
        f"total_files={inventory.total_files}\n"
        f"included_files={inventory.included_files}\n"
        f"excluded_files={inventory.excluded_files}\n",
        start_line=1,
        end_line=1,
    )

    return registry


def _symbol_excerpt(text: str, start_line: int) -> str:
    """Return a bounded excerpt centered on start_line (1-indexed)."""
    return _line_excerpt(text, start_line, context=3)


def _line_excerpt(text: str, start_line: int, context: int = 1) -> str:
    lines = text.splitlines()
    if not lines:
        return ""
    start = max(1, start_line - context)
    end = min(len(lines), start_line + context)
    return "\n".join(lines[start - 1 : end])
