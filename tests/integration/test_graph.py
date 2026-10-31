"""Integration tests for the LangGraph workflow (offline, mocked model)."""

from __future__ import annotations

import pytest

from github_to_docs.evidence.registry import EvidenceRegistry
from github_to_docs.graph.nodes import (
    acquire_repository,
    finalize_output,
    generate_documentation,
    inspect_repository,
    plan_documentation,
    prepare_evidence,
    select_revision_target,
    should_revise,
    validate_request,
    verify_documentation,
)
from github_to_docs.graph.plan_schema import (
    DocumentationPlan,
    DocumentSection,
    PlannedDocument,
)
from github_to_docs.graph.workflow import build_graph
from github_to_docs.repository.acquisition import AcquisitionResult, FileContent
from github_to_docs.repository.inventory import FileEntry, RepositoryInventory
from github_to_docs.repository.url import RepositoryUrl


class FakePlanner:
    def __init__(self, plan: DocumentationPlan) -> None:
        self._plan = plan
        self.called = False

    def plan(self, repository_url, revision, inventory_json, registry):
        self.called = True
        return self._plan


class FakeGenerator:
    def __init__(self, sections: dict[str, dict[str, str]]) -> None:
        # sections: {doc_name: {section_title: content}}
        self.sections = sections
        self.calls: list[tuple[str, str]] = []

    def generate_section(
        self, document_name, section, registry, audience="developers and contributors"
    ):
        self.calls.append((document_name, section.title))
        return self.sections.get(document_name, {}).get(section.title, f"# {section.title}\n")

    def generate_document(self, planned_doc, registry, audience="developers and contributors"):
        return self.sections.get(planned_doc.name, {})


class FakeVerifier:
    def __init__(self, findings_by_section: dict[str, list] | None = None) -> None:
        self.findings_by_section = findings_by_section or {}
        self.calls: list[tuple[str, str]] = []

    def verify_section(
        self,
        document_name,
        section_title,
        content,
        inventory_files,
        evidence_registry,
        evidence_ids,
        use_llm=True,
    ):
        self.calls.append((document_name, section_title))
        key = f"{document_name}::{section_title}"
        return self.findings_by_section.get(key, [])

    def verify_deterministic(
        self, document_name, section_title, content, inventory_files, evidence_registry
    ):
        return self.findings_by_section.get(f"{document_name}::{section_title}", [])

    def verify_llm(self, document_name, section_title, content, evidence_registry, evidence_ids):
        return []

    @staticmethod
    def has_serious_findings(findings):
        from github_to_docs.models import FindingSeverity

        return any(f.severity in {FindingSeverity.error, FindingSeverity.severe} for f in findings)


def _make_state(run_id="run1", repo_url="https://github.com/owner/repo", output_dir=None):
    return {
        "run_id": run_id,
        "repo_url": repo_url,
        "max_revision_attempts": 2,
        "output_dir": output_dir or "output",
        "errors": [],
    }


def _set_api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")


def _make_acquisition_result():
    repo = RepositoryUrl(owner="owner", repo="repo")
    fc = FileContent(
        path="src/main.py",
        content=b"def foo():\n    pass\n",
        sha="x" * 64,
        size=20,
        download_url="https://example.com/src/main.py",
    )
    return AcquisitionResult(
        repository_url=repo,
        revision="abc123",
        default_branch="main",
        repository_size_kb=10,
        files=[fc],
    )


def _make_inventory():
    return RepositoryInventory(
        repository_url="https://github.com/owner/repo",
        revision="abc123",
        default_branch="main",
        total_files=1,
        included_files=1,
        excluded_files=0,
        total_size_bytes=20,
        files=[FileEntry(path="src/main.py", size_bytes=20, line_count=2)],
        languages={"Python": 1},
        symbols=[],
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


def _make_registry():
    reg = EvidenceRegistry(repository_revision="abc123")
    reg.add(
        __import__("github_to_docs.models", fromlist=["EvidenceType"]).EvidenceType.source_code,
        "src/main.py",
        "def foo():\n    pass\n",
        start_line=1,
        end_line=1,
        symbol_name="foo",
    )
    return reg


def test_validate_request_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_api_key(monkeypatch)
    state = _make_state()
    result = validate_request(state)
    assert result["status"] == "running"
    assert result["repository_url"] == "https://github.com/owner/repo"
    assert result["repo_owner"] == "owner"
    assert result["repo_name"] == "repo"


def test_validate_request_bad_url():
    state = _make_state(repo_url="https://evil.com/x/y")
    result = validate_request(state)
    assert result["status"] == "failed"
    assert result["errors"]


def test_acquire_repository_records_revision():
    state = _make_state()
    state["repository_url"] = "https://github.com/owner/repo"
    # Monkeypatch acquirer to avoid network.
    import github_to_docs.graph.nodes as nodes_mod

    original = nodes_mod.RepositoryAcquirer

    class FakeAcquirer:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def acquire(self, repo_url):
            return _make_acquisition_result()

    nodes_mod.RepositoryAcquirer = FakeAcquirer
    try:
        result = acquire_repository(state)
    finally:
        nodes_mod.RepositoryAcquirer = original

    assert result["status"] == "acquired"
    assert result["revision"] == "abc123"


def test_inspect_repository_builds_inventory():
    state = _make_state()
    state["acquisition_result"] = _make_acquisition_result()
    result = inspect_repository(state)
    assert result["status"] == "inspected"
    assert result["inventory"].revision == "abc123"
    assert result["evidence_registry"] is not None


def test_plan_documentation_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_api_key(monkeypatch)
    state = _make_state()
    state["inventory"] = _make_inventory()
    state["evidence_registry"] = _make_registry()
    plan = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=["ev:source_code:src/main.py:foo:1"],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    planner = FakePlanner(plan)
    result = plan_documentation(state, planner)
    assert result["status"] == "planned"
    assert planner.called


def test_plan_rejects_unknown_evidence():
    state = _make_state()
    state["inventory"] = _make_inventory()
    state["evidence_registry"] = EvidenceRegistry(repository_revision="abc123")
    # No evidence registered, but plan references one.
    plan = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=["ev:nope:x:1-2"],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    planner = FakePlanner(plan)
    result = plan_documentation(state, planner)
    assert result["status"] == "planned"
    assert planner.called


def test_prepare_evidence_validates_refs():
    state = _make_state()
    state["plan"] = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=["ev:source_code:src/main.py:foo:1"],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    state["evidence_registry"] = _make_registry()
    result = prepare_evidence(state)
    assert result["status"] == "evidence_prepared"


def test_generate_documentation():
    state = _make_state()
    state["plan"] = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=[],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    state["evidence_registry"] = _make_registry()
    state["drafts"] = {}
    gen = FakeGenerator({"README.md": {"Overview": "# Overview content\n"}})
    result = generate_documentation(state, gen)
    assert result["status"] == "generated"
    assert result["drafts"]["README.md"]["Overview"] == "# Overview content\n"


def test_generate_skips_inapplicable():
    state = _make_state()
    state["plan"] = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="API.md",
                applicable=False,
                reason_if_not_applicable="no routes",
                sections=[],
                depends_on=[],
            )
        ],
    )
    state["evidence_registry"] = _make_registry()
    state["drafts"] = {}
    gen = FakeGenerator({})
    result = generate_documentation(state, gen)
    assert result["status"] == "generated"
    assert gen.calls == []  # no model calls for inapplicable


def test_verify_no_serious_findings():
    state = _make_state()
    state["plan"] = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=[],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    state["inventory"] = _make_inventory()
    state["evidence_registry"] = _make_registry()
    state["drafts"] = {"README.md": {"Overview": "# Overview\n"}}
    verifier = FakeVerifier({})
    result = verify_documentation(state, verifier)
    assert result["status"] == "verified"
    assert result["any_serious_findings"] is False


def test_verify_serious_findings():
    from github_to_docs.models import FindingSeverity, VerificationFinding

    finding = VerificationFinding(
        severity=FindingSeverity.error,
        document="README.md",
        section="Overview",
        claim="bad claim",
        evidence_ids=[],
        failure_reason="unsupported",
        recommended_correction="fix it",
    )
    state = _make_state()
    state["plan"] = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=[],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    state["inventory"] = _make_inventory()
    state["evidence_registry"] = _make_registry()
    state["drafts"] = {"README.md": {"Overview": "# Overview\n"}}
    verifier = FakeVerifier({"README.md::Overview": [finding]})
    result = verify_documentation(state, verifier)
    assert result["status"] == "verified"
    assert result["any_serious_findings"] is True


def test_should_revise_when_serious_and_attempts_remain():
    state = _make_state()
    state["revision_count"] = 0
    state["any_serious_findings"] = True
    assert should_revise(state) == "revise"


def test_should_finalize_when_no_serious():
    state = _make_state()
    state["revision_count"] = 0
    state["any_serious_findings"] = False
    assert should_revise(state) == "finalize"


def test_should_finalize_when_attempts_exhausted():
    state = _make_state()
    state["revision_count"] = 2
    state["max_revision_attempts"] = 2
    state["any_serious_findings"] = True
    assert should_revise(state) == "finalize"


def test_select_revision_target_picks_failing_section():
    from github_to_docs.models import FindingSeverity, VerificationFinding

    finding = VerificationFinding(
        severity=FindingSeverity.error,
        document="README.md",
        section="Overview",
        claim="bad",
        evidence_ids=[],
        failure_reason="unsupported",
        recommended_correction="fix",
    )
    state = _make_state()
    state["revision_count"] = 0
    state["section_findings"] = {
        "README.md::Overview": [finding],
        "API.md::Endpoints": [],
    }
    result = select_revision_target(state)
    assert result["current_document"] == "README.md"
    assert result["current_section"] == "Overview"
    assert result["revision_count"] == 1


def test_finalize_output_writes_documents(tmp_path):
    import os

    state = _make_state(output_dir=str(tmp_path))
    state["run_id"] = "run1"
    state["repo_name"] = "repo"
    state["revision"] = "abc123"
    state["repository_url"] = "https://github.com/owner/repo"
    state["plan"] = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="x",
                        facts_to_establish=[],
                        required_evidence_ids=[],
                    )
                ],
                depends_on=[],
            )
        ],
    )
    state["drafts"] = {"README.md": {"Overview": "# Overview\n"}}
    state["findings"] = []
    state["skipped_files"] = []
    state["analysis_limitations"] = []
    state["inferences"] = []
    state["missing_information"] = []

    result = finalize_output(state)
    assert result["status"] == "completed"
    assert len(result["output_paths"]) >= 1
    # Verify README was written.
    readme_path = os.path.join(str(tmp_path), "repo", "run1", "README.md")
    assert os.path.exists(readme_path)
    report_path = os.path.join(str(tmp_path), "repo", "run1", "DOCUMENTATION_REPORT.md")
    assert os.path.exists(report_path)


def test_compiled_graph_end_to_end(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Run the full compiled graph with fake dependencies."""
    _set_api_key(monkeypatch)
    import os

    plan = DocumentationPlan(
        documents=[
            PlannedDocument(
                name="README.md",
                applicable=True,
                sections=[
                    DocumentSection(
                        title="Overview",
                        purpose="Describe project",
                        facts_to_establish=["it has a foo function"],
                        required_evidence_ids=["ev:source_code:src/main.py:foo:1"],
                    )
                ],
                depends_on=[],
            )
        ],
    )

    planner = FakePlanner(plan)
    gen = FakeGenerator(
        {"README.md": {"Overview": "# Overview\n[ev:source_code:src/main.py:foo:1]\n"}}
    )
    verifier = FakeVerifier({})  # no findings → finalize

    graph = build_graph(planner, gen, verifier).compile()

    initial_state = {
        "run_id": "test-run",
        "repo_url": "https://github.com/owner/repo",
        "max_revision_attempts": 2,
        "output_dir": str(tmp_path),
        "errors": [],
    }

    # Monkeypatch acquisition + inspection to avoid network.
    import github_to_docs.graph.nodes as nodes_mod

    original_acquirer = nodes_mod.RepositoryAcquirer

    class FakeAcquirer:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def acquire(self, repo_url):
            return _make_acquisition_result()

    nodes_mod.RepositoryAcquirer = FakeAcquirer
    try:
        final = graph.invoke(initial_state)
    finally:
        nodes_mod.RepositoryAcquirer = original_acquirer

    assert final["status"] == "completed"
    assert final["run_id"] == "test-run"
    assert len(final["output_paths"]) >= 1
    assert os.path.exists(os.path.join(str(tmp_path), "repo", "test-run", "README.md"))
