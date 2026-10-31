"""FastAPI application exposing the documentation generation service."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from github_to_docs.services import AppService

app = FastAPI(
    title="GitHub-to-Docs API",
    description="Generate evidence-grounded documentation from GitHub repositories.",
    version="0.1.0",
)


class GenerateRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL.")
    output_dir: str | None = Field(
        None, description="Base output directory (overrides DOCS_OUTPUT_DIR)."
    )
    model: str | None = Field(
        None, description="Model name (overrides OPENROUTER_MODEL / NIM_MODEL)."
    )
    provider: str | None = Field(
        None, description="Model provider: 'openrouter' or 'nim' (overrides MODEL_PROVIDER)."
    )


class GenerateResponse(BaseModel):
    run_id: str
    repository_url: str
    repository_revision: str | None = None
    status: str
    output_paths: list[str] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    findings_count: int = 0
    findings: list[dict[str, Any]] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)


@app.get("/health", response_model=dict[str, str])
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/v1/documentation/generate", response_model=GenerateResponse)
async def generate_documentation(request: GenerateRequest) -> GenerateResponse:
    """Generate documentation for a GitHub repository."""
    svc = AppService(output_dir=request.output_dir, model=request.model, provider=request.provider)
    report = svc.generate(request.repo_url)

    findings = [
        {
            "severity": f.severity.value,
            "document": f.document,
            "section": f.section,
            "claim": f.claim,
            "failure_reason": f.failure_reason,
            "recommended_correction": f.recommended_correction,
        }
        for f in report.findings
    ]

    return GenerateResponse(
        run_id=report.run_id,
        repository_url=report.repository_url,
        repository_revision=report.repository_revision,
        status=report.status.value,
        output_paths=report.output_paths,
        passed_checks=report.passed_checks,
        failed_checks=report.failed_checks,
        findings_count=len(report.findings),
        findings=findings,
        skipped_files=report.skipped_files,
    )


__all__ = ["app"]
