"""LangGraph workflow nodes for the documentation pipeline.

Each node is a pure function (plus injected dependencies) that reads from and
writes to the shared GraphState. Nodes are deterministic except where they call
the model client.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC
from typing import Any

from github_to_docs.config import settings
from github_to_docs.evidence.extraction import extract_evidence
from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.generation.generator import DocumentGenerator
from github_to_docs.graph.plan_schema import DocumentationPlan
from github_to_docs.models import VerificationFinding
from github_to_docs.output import ensure_output_dir, write_document
from github_to_docs.repository.acquisition import AcquisitionResult, RepositoryAcquirer
from github_to_docs.repository.inventory import RepositoryInventory
from github_to_docs.repository.inventory_builder import build_inventory
from github_to_docs.repository.url import parse_repository_url
from github_to_docs.verification import DocumentVerifier

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# State helpers
# --------------------------------------------------------------------------- #


def _get(state: dict, key: str, default: Any = None) -> Any:
    return state.get(key, default)


def _set(state: dict, key: str, value: Any) -> None:
    state[key] = value


# --------------------------------------------------------------------------- #
# Node 1: Validate request
# --------------------------------------------------------------------------- #


def validate_request(state: dict) -> dict:
    """Validate the URL, options, configured limits, and model settings.

    Fails early for unsupported repositories or invalid input.
    """
    repo_url = state.get("repo_url")
    if not repo_url:
        state["errors"] = list(_get(state, "errors", [])) + ["Repository URL is required."]
        state["status"] = "failed"
        return state

    try:
        repo = parse_repository_url(repo_url)
    except Exception as exc:  # noqa: BLE001
        state["errors"] = list(_get(state, "errors", [])) + [str(exc)]
        state["status"] = "failed"
        return state

    # Validate model credentials are configured.
    from github_to_docs.config import validate_credentials

    try:
        validate_credentials(_get(state, "provider"))
    except Exception as exc:  # noqa: BLE001
        state["errors"] = list(_get(state, "errors", [])) + [str(exc)]
        state["status"] = "failed"
        return state

    _set(state, "repository_url", repo.normalized)
    _set(state, "repo_owner", repo.owner)
    _set(state, "repo_name", repo.repo)
    _set(state, "status", "running")
    _set(state, "revision_count", 0)
    _set(state, "errors", list(_get(state, "errors", [])))
    _set(state, "output_paths", [])
    _set(state, "token_usage", {})
    return state


# --------------------------------------------------------------------------- #
# Node 2: Acquire repository
# --------------------------------------------------------------------------- #


def acquire_repository(state: dict) -> dict:
    """Retrieve the approved repository snapshot and record the revision."""
    repo_url = _get(state, "repository_url")
    max_files = int(_get(state, "max_files", settings.max_files_to_analyze))

    try:
        with RepositoryAcquirer(max_files=max_files) as acquirer:
            result: AcquisitionResult = acquirer.acquire(repo_url)
    except Exception as exc:  # noqa: BLE001
        state["errors"] = list(_get(state, "errors", [])) + [
            f"Repository acquisition failed: {exc}"
        ]
        state["status"] = "failed"
        return state

    _set(state, "acquisition_result", result)
    _set(state, "revision", result.revision)
    _set(
        state,
        "repository_metadata",
        {
            "default_branch": result.default_branch,
            "repository_size_kb": result.repository_size_kb,
        },
    )
    _set(state, "status", "acquired")
    return state


# --------------------------------------------------------------------------- #
# Node 3: Inspect repository
# --------------------------------------------------------------------------- #


def inspect_repository(state: dict) -> dict:
    """Build the deterministic inventory and evidence registry."""
    if _get(state, "status") == "failed":
        return state

    result: AcquisitionResult = _get(state, "acquisition_result")

    try:
        inventory: RepositoryInventory = build_inventory(result)
        registry: EvidenceRegistry = extract_evidence(result, inventory)
    except Exception as exc:  # noqa: BLE001
        state["errors"] = list(_get(state, "errors", [])) + [f"Repository inspection failed: {exc}"]
        state["status"] = "failed"
        return state

    _set(state, "inventory", inventory)
    _set(state, "evidence_registry", registry)
    _set(state, "skipped_files", list(result.skipped_files))
    _set(state, "analysis_limitations", list(result.analysis_limitations))
    _set(state, "status", "inspected")
    return state


# --------------------------------------------------------------------------- #
# Node 4: Plan documentation
# --------------------------------------------------------------------------- #


def plan_documentation(state: dict, planner) -> dict:
    """Use the LLM to create a structured documentation plan."""
    if _get(state, "status") == "failed":
        return state

    inventory: RepositoryInventory = _get(state, "inventory")
    registry: EvidenceRegistry = _get(state, "evidence_registry")

    import json

    inventory_json = json.dumps(
        {
            "total_files": inventory.total_files,
            "included_files": inventory.included_files,
            "excluded_files": inventory.excluded_files,
            "languages": inventory.languages,
            "readme_path": inventory.readme_path,
            "docs_paths": inventory.docs_paths,
            "test_paths": inventory.test_paths,
            "entry_points": inventory.entry_points,
            "route_count": len(inventory.routes),
            "ci_workflows": inventory.ci_workflows,
            "env_var_count": len(inventory.env_vars),
            "symbol_count": len(inventory.symbols),
            "dependency_count": len(inventory.dependencies),
        }
    )

    try:
        plan: DocumentationPlan = planner.plan(
            repository_url=_get(state, "repository_url"),
            revision=_get(state, "revision"),
            inventory_json=inventory_json,
            registry=registry,
        )
    except Exception as exc:  # noqa: BLE001
        state["errors"] = list(_get(state, "errors", [])) + [
            f"Documentation planning failed: {exc}"
        ]
        state["status"] = "failed"
        return state

    _set(state, "plan", plan)
    _set(state, "drafts", {})
    _set(state, "section_findings", {})

    # Validate that every section's required evidence IDs exist in the registry.
    # Log a warning for invalid IDs but do not fail the run — the LLM may
    # reference evidence that doesn't exist, and generation handles missing
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

    _set(state, "status", "planned")
    return state


# --------------------------------------------------------------------------- #
# Node 5: Prepare evidence (deterministic selection)
# --------------------------------------------------------------------------- #


def prepare_evidence(state: dict) -> dict:
    """Select relevant evidence for each planned section (deterministic)."""
    if _get(state, "status") == "failed":
        return state

    plan: DocumentationPlan = _get(state, "plan")
    registry: EvidenceRegistry = _get(state, "evidence_registry")

    # Validate evidence references and warn on invalid IDs, but do not fail
    # the run — missing evidence is handled gracefully during generation.
    invalid: list[str] = []
    for doc in plan.documents:
        if not doc.applicable:
            continue
        for section in doc.sections:
            invalid.extend(registry.validate_references(section.required_evidence_ids))

    if invalid:
        logger.warning(
            "Plan references %d unknown evidence ID(s): %s",
            len(invalid),
            invalid[:10],
        )

    _set(state, "evidence_validated", True)
    _set(state, "status", "evidence_prepared")
    return state


# --------------------------------------------------------------------------- #
# Node 6: Generate documentation
# --------------------------------------------------------------------------- #


def generate_documentation(state: dict, generator: DocumentGenerator) -> dict:
    """Generate one document or small independent group at a time.

    If a targeted revision is in progress (state has current_document /
    current_section), only that section is regenerated.
    """
    if _get(state, "status") == "failed":
        return state

    plan: DocumentationPlan = _get(state, "plan")
    registry: EvidenceRegistry = _get(state, "evidence_registry")
    drafts: dict = _get(state, "drafts", {})

    current_doc = _get(state, "current_document")
    current_section = _get(state, "current_section")

    docs_to_generate = plan.documents
    if current_doc:
        docs_to_generate = [d for d in plan.documents if d.name == current_doc]

    for planned_doc in docs_to_generate:
        if not planned_doc.applicable:
            continue

        sections_to_generate = planned_doc.sections
        if current_doc and current_section:
            sections_to_generate = [s for s in planned_doc.sections if s.title == current_section]

        doc_sections: dict[str, str] = drafts.get(planned_doc.name, {})
        for section in sections_to_generate:
            try:
                content = generator.generate_section(
                    document_name=planned_doc.name,
                    section=section,
                    registry=registry,
                    audience="developers and contributors",
                )
                doc_sections[section.title] = content
            except Exception as exc:  # noqa: BLE001
                state["errors"] = list(_get(state, "errors", [])) + [
                    f"Generation failed for {planned_doc.name}/{section.title}: {exc}"
                ]
                state["status"] = "failed"
                return state
        drafts[planned_doc.name] = doc_sections

    # Clear targeted revision markers.
    _set(state, "current_document", None)
    _set(state, "current_section", None)
    _set(state, "drafts", drafts)
    _set(state, "status", "generated")
    return state


# --------------------------------------------------------------------------- #
# Node 7: Verify documentation
# --------------------------------------------------------------------------- #


def verify_documentation(state: dict, verifier: DocumentVerifier) -> dict:
    """Run deterministic + LLM-assisted checks on generated sections."""
    if _get(state, "status") == "failed":
        return state

    plan: DocumentationPlan = _get(state, "plan")
    registry: EvidenceRegistry = _get(state, "evidence_registry")
    inventory: RepositoryInventory = _get(state, "inventory")
    drafts: dict = _get(state, "drafts", {})
    section_findings: dict = _get(state, "section_findings", {})

    if inventory is None:
        state["errors"] = list(_get(state, "errors", [])) + ["No inventory available for verification."]
        state["status"] = "failed"
        return state

    inventory_files = [f.path for f in inventory.files]

    all_findings: list = []
    any_serious = False

    for planned_doc in plan.documents:
        if not planned_doc.applicable:
            continue
        doc_findings: list = []
        for section in planned_doc.sections:
            content = drafts.get(planned_doc.name, {}).get(section.title, "")
            # Collect evidence IDs cited in this section.
            import re

            cited = set(re.findall(r"ev:[^\s\]]+", content))

            findings = verifier.verify_section(
                document_name=planned_doc.name,
                section_title=section.title,
                content=content,
                inventory_files=inventory_files,
                evidence_registry=registry,
                evidence_ids=list(cited),
            )
            doc_findings.extend(findings)
            all_findings.extend(findings)
            section_findings[f"{planned_doc.name}::{section.title}"] = findings
            if DocumentVerifier.has_serious_findings(findings):
                any_serious = True

    _set(state, "findings", all_findings)
    _set(state, "section_findings", section_findings)
    _set(state, "any_serious_findings", any_serious)
    _set(state, "status", "verified")
    return state


# --------------------------------------------------------------------------- #
# Node 8: Conditional revision or finalize
# --------------------------------------------------------------------------- #


def should_revise(state: dict) -> str:
    """LangGraph conditional edge: revise or finalize."""
    max_attempts = int(_get(state, "max_revision_attempts", settings.max_revision_attempts))
    revision_count = int(_get(state, "revision_count", 0))
    any_serious = bool(_get(state, "any_serious_findings", False))

    if any_serious and revision_count < max_attempts:
        return "revise"
    return "finalize"


def select_revision_target(state: dict) -> dict:
    """Pick the first section with serious findings for targeted revision.

    Does NOT regenerate all documents — only the failing section.
    """
    if _get(state, "status") == "failed":
        return state

    section_findings: dict = _get(state, "section_findings", {})
    for key, findings in section_findings.items():
        if DocumentVerifier.has_serious_findings(findings):
            doc_name, section_title = key.split("::", 1)
            _set(state, "current_document", doc_name)
            _set(state, "current_section", section_title)
            # Build targeted feedback for the generator.
            feedback = "\n".join(
                f"- {f.claim}: {f.failure_reason}. {f.recommended_correction}"
                for f in findings
            )
            _set(state, "revision_feedback", feedback)
            _set(
                state,
                "revision_count",
                int(_get(state, "revision_count", 0)) + 1,
            )
            _set(state, "status", "revising")
            return state

    # No serious findings found but should_revise returned revise — finalize.
    _set(state, "status", "finalizing")
    return state


# --------------------------------------------------------------------------- #
# Node 9: Finalize output
# --------------------------------------------------------------------------- #


def finalize_output(state: dict) -> dict:
    """Write documents atomically, produce report, mark complete."""
    from datetime import datetime

    from github_to_docs.models import RunReport, RunStatus

    if _get(state, "status") == "failed":
        return state

    plan: DocumentationPlan = _get(state, "plan")
    if plan is None:
        state["errors"] = list(_get(state, "errors", [])) + [
            "No documentation plan available to finalize."
        ]
        state["status"] = "failed"
        return state
    drafts: dict = _get(state, "drafts", {})
    findings: list = _get(state, "findings", [])
    repo_name = _get(state, "repo_name")
    run_id = _get(state, "run_id") or str(uuid.uuid4())
    base_dir = _get(state, "output_dir", settings.docs_output_dir)

    try:
        output_dir = ensure_output_dir(base_dir, repo_name, run_id)
    except Exception as exc:  # noqa: BLE001
        state["errors"] = list(_get(state, "errors", [])) + [
            f"Output directory creation failed: {exc}"
        ]
        state["status"] = "failed"
        return state

    output_paths: list[str] = []
    passed_checks: list[str] = []
    failed_checks: list[str] = []

    for planned_doc in plan.documents:
        if not planned_doc.applicable:
            continue
        doc_sections = drafts.get(planned_doc.name, {})
        if not doc_sections:
            continue
        # Combine sections into one document. Deduplicate section titles and
        # skip sections with empty content to avoid duplicate/empty headers.
        parts: list[str] = []
        written_titles: set[str] = set()
        for section in planned_doc.sections:
            title = section.title
            if title in written_titles:
                continue
            content = doc_sections.get(title, "")
            if not content or not content.strip():
                continue
            written_titles.add(title)
            parts.append(f"## {title}\n\n{content.strip()}\n")
        if not parts:
            continue
        full_doc = f"# {planned_doc.name}\n\n" + "\n".join(parts)
        try:
            path = write_document(output_dir, planned_doc.name, full_doc)
            output_paths.append(path)
            passed_checks.append(f"{planned_doc.name} written")
        except Exception as exc:  # noqa: BLE001
            failed_checks.append(f"{planned_doc.name}: {exc}")

    # Write DOCUMENTATION_REPORT.md
    report_lines: list[str] = [
        "# Documentation Report",
        f"Repository: {_get(state, 'repository_url')}",
        f"Revision: {_get(state, 'revision')}",
        f"Run ID: {run_id}",
        f"Status: {_get(state, 'status')}",
        "",
        "## Generated Documents",
    ]
    BS = "\\"
    for p in output_paths:
        report_lines.append(f"- {p.replace(BS, '/')}")
    # Only surface non-info findings in the report (info findings are just
    # confirmations and add noise).
    reportable_findings = [
        f for f in findings if f.severity.value in ("warning", "error", "severe")
    ]

    report_lines.extend(
        [
            "",
            "## Verification Summary",
            f"Total findings: {len(reportable_findings)}",
            f"Serious findings: {sum(1 for f in reportable_findings if f.severity.value in ('error', 'severe'))}",
            "",
            "## Findings",
        ]
    )
    for f in reportable_findings:
        report_lines.append(
            f"- [{f.severity.value}] {f.document}::{f.section or 'general'}: {f.claim} — {f.failure_reason}"
        )
    report_lines.extend(
        [
            "",
            "## Limitations",
        ]
    )
    for lim in _get(state, "analysis_limitations", []):
        report_lines.append(f"- {lim}")
    for skipped in _get(state, "skipped_files", []):
        report_lines.append(f"- Skipped: {skipped}")

    report_path = write_document(output_dir, "DOCUMENTATION_REPORT.md", "\n".join(report_lines))
    output_paths.append(report_path)

    _set(state, "output_paths", output_paths)
    _set(state, "run_id", run_id)
    _set(state, "status", "completed")

    report = RunReport(
        run_id=run_id,
        repository_url=_get(state, "repository_url"),
        repository_revision=_get(state, "revision"),
        status=RunStatus.completed,
        created_at=datetime.now(UTC),
        output_paths=output_paths,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        findings=[
            VerificationFinding(
                severity=f.severity,
                document=f.document,
                section=f.section,
                claim=f.claim,
                evidence_ids=f.evidence_ids,
                failure_reason=f.failure_reason,
                recommended_correction=f.recommended_correction,
            )
            for f in findings
        ],
        inferences=list(_get(state, "inferences", [])),
        missing_information=list(_get(state, "missing_information", [])),
        skipped_files=list(_get(state, "skipped_files", [])),
        token_usage=_get(state, "token_usage", {}),
    )
    _set(state, "run_report", report)
    return state


__all__ = [
    "validate_request",
    "acquire_repository",
    "inspect_repository",
    "plan_documentation",
    "prepare_evidence",
    "generate_documentation",
    "verify_documentation",
    "should_revise",
    "select_revision_target",
    "finalize_output",
]
