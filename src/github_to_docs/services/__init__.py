"""Application service shared by CLI and FastAPI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from github_to_docs.config import settings, validate_credentials
from github_to_docs.generation.client import create_model_client
from github_to_docs.generation.generator import DocumentGenerator
from github_to_docs.generation.planner import DocumentationPlanner
from github_to_docs.graph.workflow import build_graph
from github_to_docs.models import RunReport, RunStatus
from github_to_docs.verification import DocumentVerifier


class AppService:
    """Thin application service coordinating the LangGraph workflow.

    Builds the real model-backed graph by default. Dependencies can be
    injected for testing (offline, faked model).
    """

    def __init__(
        self,
        output_dir: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        planner=None,
        generator=None,
        verifier=None,
    ) -> None:
        self.output_dir = output_dir or settings.docs_output_dir
        self.provider = provider or settings.model_provider
        self.model = model
        self._planner = planner
        self._generator = generator
        self._verifier = verifier

    def _build_dependencies(self):
        """Build real model-backed dependencies (or use injected ones)."""
        if self._planner is None:
            model_client = create_model_client(
                provider=self.provider,
                model=self.model,
            )
            self._planner = DocumentationPlanner(model_client)
            self._generator = DocumentGenerator(model_client)
            self._verifier = DocumentVerifier(model_client)
        return self._planner, self._generator, self._verifier

    def _failed_report(
        self,
        repo_url: str,
        run_id: str,
        reason: str,
        revision: str | None = None,
        errors: list[str] | None = None,
        findings: list | None = None,
        output_paths: list[str] | None = None,
        skipped_files: list[str] | None = None,
        token_usage: dict | None = None,
    ) -> RunReport:
        return RunReport(
            run_id=run_id,
            repository_url=repo_url,
            repository_revision=revision,
            status=RunStatus.failed,
            created_at=datetime.now(UTC),
            output_paths=output_paths or [],
            passed_checks=[],
            failed_checks=list(errors or []) + [reason],
            findings=list(findings or []),
            inferences=[],
            missing_information=[],
            skipped_files=list(skipped_files or []),
            token_usage=token_usage or {},
        )

    def generate(self, repo_url: str) -> RunReport:
        """Generate documentation for a repository using the LangGraph workflow.

        Returns a :class:`RunReport` summarising the run. On any failure the
        report carries ``status=failed`` with the error recorded in
        ``failed_checks`` — it never raises.
        """
        run_id = str(uuid.uuid4())

        # Validate model credentials early so failure is explicit.
        try:
            validate_credentials(self.provider)
        except RuntimeError as exc:
            return self._failed_report(repo_url, run_id, str(exc))

        planner, generator, verifier = self._build_dependencies()
        graph = build_graph(planner, generator, verifier).compile()

        initial_state = {
            "run_id": run_id,
            "repo_url": repo_url,
            "provider": self.provider,
            "max_revision_attempts": settings.max_revision_attempts,
            "output_dir": self.output_dir,
            "errors": [],
        }

        try:
            final = graph.invoke(initial_state)
        except Exception as exc:  # noqa: BLE001
            return self._failed_report(repo_url, run_id, str(exc))

        run_report = final.get("run_report")
        if run_report is not None:
            return run_report

        # Graph stopped before finalize_output (e.g. validation/acquire failed).
        return self._failed_report(
            repo_url,
            run_id,
            "Graph did not complete finalization.",
            revision=final.get("revision"),
            errors=list(final.get("errors", [])),
            findings=list(final.get("findings", [])),
            output_paths=list(final.get("output_paths", [])),
            skipped_files=list(final.get("skipped_files", [])),
            token_usage=final.get("token_usage", {}),
        )


__all__ = ["AppService"]
