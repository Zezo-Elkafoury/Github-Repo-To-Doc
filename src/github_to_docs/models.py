"""Shared Pydantic schemas for run state, evidence, plans, and findings."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EvidenceType(StrEnum):
    source_code = "source_code"
    dependency_manifest = "dependency_manifest"
    configuration = "configuration"
    documentation = "documentation"
    test = "test"
    ci_workflow = "ci_workflow"
    api_declaration = "api_declaration"
    repository_metadata = "repository_metadata"


class EvidenceItem(BaseModel):
    """A bounded excerpt of observed repository content with provenance."""

    evidence_id: str
    repository_revision: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol_name: str | None = None
    evidence_type: EvidenceType
    content: str
    content_hash: str


class FindingSeverity(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"
    severe = "severe"


class VerificationFinding(BaseModel):
    """A structured verification finding."""

    severity: FindingSeverity
    document: str
    section: str | None = None
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    failure_reason: str
    recommended_correction: str


class RunReport(BaseModel):
    """Machine-readable summary of a completed run."""

    run_id: str
    repository_url: str
    repository_revision: str | None = None
    status: RunStatus
    created_at: datetime
    output_paths: list[str] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    findings: list[VerificationFinding] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
    token_usage: dict = Field(default_factory=dict)
