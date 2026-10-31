"""CLI entry point using Typer."""

from __future__ import annotations

import typer

from github_to_docs.config import settings
from github_to_docs.services import AppService

app = typer.Typer(
    name="github-to-docs",
    help="Generate evidence-grounded documentation from a GitHub repository.",
)


@app.command()
def generate(
    repo_url: str = typer.Argument(..., help="GitHub repository URL."),
    output: str = typer.Option(
        None, "--output", "-o", help="Base output directory (overrides DOCS_OUTPUT_DIR)."
    ),
    model: str = typer.Option(
        None, "--model", help="Model name (overrides OPENROUTER_MODEL / NIM_MODEL)."
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        help="Model provider: 'openrouter' or 'nim' (overrides MODEL_PROVIDER).",
    ),
    max_files: int = typer.Option(None, "--max-files", help="Maximum files to analyze."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose progress output."),
) -> None:
    """Generate documentation for a GitHub repository."""
    svc = AppService(output_dir=output, model=model, provider=provider)
    typer.echo(f"Repository: {repo_url}")
    typer.echo(f"Provider: {provider or settings.model_provider}")
    typer.echo(f"Model: {model or 'default'}")
    typer.echo(f"Output dir: {output or settings.docs_output_dir}")

    report = svc.generate(repo_url)

    if report.status == "failed":
        typer.secho("Generation failed.", fg=typer.colors.RED, err=True)
        for check in report.failed_checks:
            typer.echo(f"  - {check}", err=True)
        raise typer.Exit(code=1)

    typer.secho("Generation complete.", fg=typer.colors.GREEN)
    typer.echo(f"Run ID: {report.run_id}")
    typer.echo(f"Status: {report.status.value}")
    if report.output_paths:
        typer.echo("Generated documents:")
        for path in report.output_paths:
            typer.echo(f"  - {path}")
    if report.failed_checks:
        typer.secho("Warnings/errors:", fg=typer.colors.YELLOW)
        for check in report.failed_checks:
            typer.echo(f"  - {check}")
    if report.findings:
        typer.echo(f"Verification findings: {len(report.findings)}")
        for f in report.findings:
            typer.echo(f"  [{f.severity.value}] {f.document}::{f.section or 'general'}: {f.claim}")


if __name__ == "__main__":
    app()
