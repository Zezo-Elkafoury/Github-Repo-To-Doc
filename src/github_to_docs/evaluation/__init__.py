"""Evaluation benchmark package."""

from github_to_docs.evaluation.fixtures import (
    sample_drafts,
    sample_findings,
    sample_inventory,
    sample_plan,
    sample_registry,
    sample_run_report,
    sample_serious_run_report,
)
from github_to_docs.evaluation.metrics import (
    benchmark,
    evidence_citation_precision,
    evidence_citation_recall,
    extract_evidence_ids,
    finding_severity_distribution,
    run_passed,
    section_coverage,
    serious_finding_count,
    token_usage_total,
)

__all__ = [
    "sample_drafts",
    "sample_findings",
    "sample_inventory",
    "sample_plan",
    "sample_registry",
    "sample_serious_run_report",
    "sample_run_report",
    "benchmark",
    "evidence_citation_precision",
    "evidence_citation_recall",
    "extract_evidence_ids",
    "finding_severity_distribution",
    "run_passed",
    "section_coverage",
    "serious_finding_count",
    "token_usage_total",
]
