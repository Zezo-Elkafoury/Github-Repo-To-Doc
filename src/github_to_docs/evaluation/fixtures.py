"""Evaluation benchmark fixtures and metrics for github-to-docs."""

from __future__ import annotations

from datetime import UTC, datetime

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.graph.plan_schema import (
    DocumentationPlan,
    DocumentSection,
    PlannedDocument,
)
from github_to_docs.models import (
    EvidenceType,
    FindingSeverity,
    RunReport,
    RunStatus,
    VerificationFinding,
)

__all__ = [
    "sample_inventory",
    "sample_registry",
    "sample_plan",
    "sample_drafts",
    "sample_findings",
    "sample_run_report",
]


def sample_registry() -> EvidenceRegistry:
    """Evidence registry for a small sample repository (owner/repo)."""
    reg = EvidenceRegistry(repository_revision="abc123")
    reg.add(
        EvidenceType.source_code,
        "src/main.py",
        "def foo():\n    pass\n",
        start_line=1,
        end_line=2,
        symbol_name="foo",
    )
    reg.add(
        EvidenceType.source_code,
        "src/utils.py",
        "def helper():\n    return 1\n",
        start_line=1,
        end_line=2,
        symbol_name="helper",
    )
    reg.add(
        EvidenceType.configuration,
        "pyproject.toml",
        "[project]\nname = \"repo\"\n",
        start_line=1,
        end_line=3,
    )
    return reg


def sample_inventory():
    """Repository inventory for the sample repository."""
    from github_to_docs.repository.inventory import (
        FileEntry,
        RepositoryInventory,
    )

    return RepositoryInventory(
        repository_url="https://github.com/owner/repo",
        revision="abc123",
        default_branch="main",
        total_files=3,
        included_files=3,
        excluded_files=0,
        total_size_bytes=200,
        files=[
            FileEntry(path="src/main.py", size_bytes=80, line_count=2),
            FileEntry(path="src/utils.py", size_bytes=60, line_count=2),
            FileEntry(path="pyproject.toml", size_bytes=60, line_count=3),
        ],
        languages={"Python": 2, "TOML": 1},
        symbols=["foo", "helper"],
        dependencies=[],
        routes=[],
        env_vars=[],
        ci_workflows=[],
        readme_path=None,
        docs_paths=[],
        test_paths=[],
        entry_points=["src/main.py"],
        skipped_files=[],
        analysis_limitations=[],
    )


def sample_plan() -> DocumentationPlan:
    """A documentation plan referencing known and unknown evidence."""
    return DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="Describe the project",
                        facts_to_establish=["it has a foo function"],
                        required_evidence_ids=[
                            "ev:source_code:src/main.py:foo:1-2",
                        ],
                    ),
                    DocumentSection(
                        title="Setup",
                        purpose="Installation steps",
                        facts_to_establish=[],
                        required_evidence_ids=[
                            "ev:configuration:pyproject.toml:1-3",
                        ],
                    ),
                ],
                depends_on=[],
            ),
            PlannedDocument(
                name="API.md",
                applicable=False,
                reason_if_not_applicable="no HTTP routes found",
                sections=[
                    DocumentSection(
                        title="Endpoints",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=[],
                    )
                ],
                depends_on=[],
            ),
        ],
        missing_information=[],
        potential_contradictions=[],
        verification_requirements=["check README exists"],
    )


def sample_drafts() -> dict[str, dict[str, str]]:
    """Generated drafts: README cites valid evidence; API is inapplicable (empty)."""
    return {
        "README.md": {
            "Overview": "# Overview\nThe project has a foo function.\n[ev:source_code:src/main.py:foo:1-2]\n",
            "Setup": "# Setup\nInstall from pyproject.\n[ev:configuration:pyproject.toml:1-3]\n",
        },
        "API.md": {},
    }


def sample_findings() -> list[VerificationFinding]:
    """Verification findings: one warning, no serious errors."""
    return [
        VerificationFinding(
            severity=FindingSeverity.warning,
            document="README.md",
            section="Overview",
            claim="The project has a foo function.",
            evidence_ids=["ev:source_code:src/main.py:foo:1-2"],
            failure_reason="",
            recommended_correction="",
        ),
    ]


def sample_run_report() -> RunReport:
    """A completed RunReport for the sample repository."""
    return RunReport(
        run_id="bench-run-1",
        repository_url="https://github.com/owner/repo",
        repository_revision="abc123",
        status=RunStatus.completed,
        created_at=datetime.now(UTC),
        output_paths=["/tmp/repo/bench-run-1/README.md"],
        passed_checks=["structure validated"],
        failed_checks=[],
        findings=sample_findings(),
        inferences=["foo is the public entry point"],
        missing_information=[],
        skipped_files=[],
        token_usage={"prompt": 120, "completion": 80, "total": 200},
    )


def sample_serious_run_report() -> RunReport:
    """A failed RunReport with serious findings."""
    findings = [
        VerificationFinding(
            severity=FindingSeverity.error,
            document="README.md",
            section="Overview",
            claim="bad claim",
            evidence_ids=[],
            failure_reason="unsupported",
            recommended_correction="fix it",
        )
    ]
    return RunReport(
        run_id="bench-run-2",
        repository_url="https://github.com/owner/repo",
        repository_revision="abc123",
        status=RunStatus.failed,
        created_at=datetime.now(UTC),
        output_paths=[],
        passed_checks=[],
        failed_checks=["unsupported claim"],
        findings=findings,
        inferences=[],
        missing_information=[],
        skipped_files=[],
        token_usage={},
    )
