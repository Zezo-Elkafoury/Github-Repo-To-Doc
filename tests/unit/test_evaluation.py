"""Unit tests for the evaluation benchmark fixtures and metrics (offline)."""

from __future__ import annotations

from github_to_docs.evaluation import (
    benchmark,
    evidence_citation_precision,
    evidence_citation_recall,
    extract_evidence_ids,
    finding_severity_distribution,
    run_passed,
    sample_drafts,
    sample_plan,
    sample_registry,
    sample_run_report,
    sample_serious_run_report,
    section_coverage,
    serious_finding_count,
    token_usage_total,
)
from github_to_docs.models import FindingSeverity, VerificationFinding


def test_extract_evidence_ids():
    content = "# Overview\nSee [ev:source_code:src/main.py:foo:1-2] and [ev:configuration:pyproject.toml:1-3]\n"
    ids = extract_evidence_ids(content)
    assert "ev:source_code:src/main.py:foo:1-2" in ids
    assert "ev:configuration:pyproject.toml:1-3" in ids


def test_extract_evidence_ids_empty():
    assert extract_evidence_ids("no citations here") == []
    assert extract_evidence_ids("") == []


def test_evidence_citation_precision_all_valid():
    reg = sample_registry()
    drafts = sample_drafts()
    assert evidence_citation_precision(drafts, reg) == 1.0


def test_evidence_citation_precision_invalid():
    reg = sample_registry()
    drafts = {"README.md": {"Overview": "# x [ev:source_code:nonexistent.py:bar:1-2]\n"}}
    assert evidence_citation_precision(drafts, reg) == 0.0


def test_evidence_citation_precision_nothing_cited():
    reg = sample_registry()
    assert evidence_citation_precision({"README.md": {}}, reg) == 1.0


def test_evidence_citation_recall_all_covered():
    reg = sample_registry()
    plan = sample_plan()
    drafts = sample_drafts()
    assert evidence_citation_recall(plan, drafts, reg) == 1.0


def test_evidence_citation_recall_missing():
    reg = sample_registry()
    plan = sample_plan()
    # Draft that omits the pyproject citation.
    drafts = {
        "README.md": {
            "Overview": "# Overview [ev:source_code:src/main.py:foo:1-2]\n",
            "Setup": "# Setup\n",
        },
        "API.md": {},
    }
    assert evidence_citation_recall(plan, drafts, reg) == 0.5


def test_section_coverage_all_covered():
    plan = sample_plan()
    drafts = sample_drafts()
    assert section_coverage(plan, drafts) == 1.0


def test_section_coverage_partial():
    plan = sample_plan()
    drafts = {
        "README.md": {"Overview": "# Overview\n"},
        "API.md": {},
    }
    # README has 2 sections, only Overview covered -> 1/2; API inapplicable -> skipped.
    assert section_coverage(plan, drafts) == 0.5


def test_section_coverage_no_applicable():
    plan = sample_plan()
    inapplicable = type(plan)(
        documents=[
            type(plan.documents[0])(
                name="API.md",
                applicable=False,
                reason_if_not_applicable="no routes",
                sections=[
                    type(plan.documents[0].sections[0])(
                        title="Endpoints",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=[],
                    )
                ],
                depends_on=[],
            )
        ]
    )
    assert section_coverage(inapplicable, {}) == 1.0


def test_serious_finding_count_none():
    report = sample_run_report()
    assert serious_finding_count(report) == 0


def test_serious_finding_count_some():
    finding = VerificationFinding(
        severity=FindingSeverity.error,
        document="README.md",
        section="Overview",
        claim="bad",
        evidence_ids=[],
        failure_reason="unsupported",
        recommended_correction="fix",
    )
    report = sample_run_report()
    report.findings.append(finding)
    assert serious_finding_count(report) == 1


def test_run_passed_completed_no_serious():
    assert run_passed(sample_run_report()) is True


def test_run_passed_failed():
    assert run_passed(sample_serious_run_report()) is False


def test_token_usage_total():
    report = sample_run_report()
    assert token_usage_total(report) == 200


def test_token_usage_total_empty():
    report = sample_run_report()
    report.token_usage = {}
    assert token_usage_total(report) == 0


def test_finding_severity_distribution():
    report = sample_run_report()
    dist = finding_severity_distribution(report)
    assert dist == {"warning": 1}


def test_benchmark_full():
    report = sample_run_report()
    plan = sample_plan()
    drafts = sample_drafts()
    reg = sample_registry()
    result = benchmark(report, plan, drafts, reg)
    assert result["run_id"] == "bench-run-1"
    assert result["status"] == "completed"
    assert result["run_passed"] is True
    assert result["evidence_citation_precision"] == 1.0
    assert result["evidence_citation_recall"] == 1.0
    assert result["section_coverage"] == 1.0
    assert result["serious_finding_count"] == 0
    assert result["finding_count"] == 1
    assert result["token_usage_total"] == 200


def test_benchmark_serious_run():
    report = sample_serious_run_report()
    plan = sample_plan()
    drafts = {"README.md": {}}
    reg = sample_registry()
    result = benchmark(report, plan, drafts, reg)
    assert result["run_passed"] is False
    assert result["serious_finding_count"] == 1
    assert result["status"] == "failed"
