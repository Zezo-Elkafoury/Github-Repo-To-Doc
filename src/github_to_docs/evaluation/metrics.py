"""Evaluation metrics for documentation generation runs.

All metrics are deterministic and require no network or model calls, so they
can be computed offline against fixtures or real run artifacts.
"""

from __future__ import annotations

import re
from typing import Any

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.graph.plan_schema import DocumentationPlan
from github_to_docs.models import FindingSeverity, RunReport

_EVIDENCE_ID_RE = re.compile(r"ev:[A-Za-z_]+:[^\s\]]+")


def extract_evidence_ids(content: str) -> list[str]:
    """Extract all evidence reference IDs appearing in generated content."""
    return _EVIDENCE_ID_RE.findall(content or "")


def evidence_citation_precision(
    drafts: dict[str, dict[str, str]], registry: EvidenceRegistry
) -> float:
    """Fraction of cited evidence IDs that exist in the registry.

    Measures whether generated documents only reference real evidence.
    Returns 1.0 when nothing is cited (vacuously precise).
    """
    cited: list[str] = []
    for sections in drafts.values():
        for content in sections.values():
            cited.extend(extract_evidence_ids(content))
    if not cited:
        return 1.0
    valid = sum(1 for eid in cited if registry.validate_reference(eid))
    return valid / len(cited)


def evidence_citation_recall(
    plan: DocumentationPlan,
    drafts: dict[str, dict[str, str]],
    registry: EvidenceRegistry,
) -> float:
    """Fraction of required evidence IDs (from the plan) that are cited.

    Measures whether generated documents cover the evidence the plan said they
    needed. Returns 1.0 when nothing is required (vacuously complete).
    """
    required: list[str] = []
    for doc in plan.documents:
        if not doc.applicable:
            continue
        for section in doc.sections:
            required.extend(section.required_evidence_ids)
    if not required:
        return 1.0
    cited: set[str] = set()
    for sections in drafts.values():
        for content in sections.values():
            cited.update(extract_evidence_ids(content))
    covered = sum(1 for eid in required if eid in cited)
    return covered / len(required)


def section_coverage(
    plan: DocumentationPlan, drafts: dict[str, dict[str, str]]
) -> float:
    """Fraction of applicable planned sections that have non-empty draft content."""
    total = 0
    covered = 0
    for doc in plan.documents:
        if not doc.applicable:
            continue
        doc_sections = drafts.get(doc.name, {})
        for section in doc.sections:
            total += 1
            content = doc_sections.get(section.title, "")
            if content and content.strip():
                covered += 1
    if total == 0:
        return 1.0
    return covered / total


def serious_finding_count(report: RunReport) -> int:
    """Count of error/severity-level verification findings."""
    return sum(
        1
        for f in report.findings
        if f.severity in {FindingSeverity.error, FindingSeverity.severe}
    )


def finding_severity_distribution(report: RunReport) -> dict[str, int]:
    """Count of findings grouped by severity."""
    dist: dict[str, int] = {}
    for f in report.findings:
        dist[f.severity.value] = dist.get(f.severity.value, 0) + 1
    return dist


def run_passed(report: RunReport) -> bool:
    """True if the run completed with no serious verification findings."""
    return report.status == "completed" and serious_finding_count(report) == 0


def token_usage_total(report: RunReport) -> int:
    """Total token usage across prompt/completion/etc.

    Uses the ``total`` key when present; otherwise sums all numeric values.
    """
    usage = report.token_usage or {}
    if "total" in usage:
        return int(usage["total"])
    return sum(int(v) for v in usage.values() if isinstance(v, (int, float)))


def benchmark(
    report: RunReport,
    plan: DocumentationPlan,
    drafts: dict[str, dict[str, str]],
    registry: EvidenceRegistry,
) -> dict[str, Any]:
    """Compute the full evaluation benchmark for a single run.

    Returns a dict of metric name -> value suitable for reporting or assertion.
    """
    return {
        "run_id": report.run_id,
        "repository_url": report.repository_url,
        "repository_revision": report.repository_revision,
        "status": report.status.value,
        "run_passed": run_passed(report),
        "evidence_citation_precision": evidence_citation_precision(drafts, registry),
        "evidence_citation_recall": evidence_citation_recall(plan, drafts, registry),
        "section_coverage": section_coverage(plan, drafts),
        "serious_finding_count": serious_finding_count(report),
        "finding_severity_distribution": finding_severity_distribution(report),
        "finding_count": len(report.findings),
        "failed_check_count": len(report.failed_checks),
        "output_path_count": len(report.output_paths),
        "token_usage_total": token_usage_total(report),
        "skipped_file_count": len(report.skipped_files),
    }


__all__ = [
    "extract_evidence_ids",
    "evidence_citation_precision",
    "evidence_citation_recall",
    "section_coverage",
    "serious_finding_count",
    "finding_severity_distribution",
    "run_passed",
    "token_usage_total",
    "benchmark",
]
