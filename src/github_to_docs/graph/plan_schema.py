"""Documentation planning Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DocumentSection(BaseModel):
    """A planned section of a single document."""

    title: str = Field(..., description="Section heading.")
    purpose: str = Field(..., description="What fact this section must establish.")
    facts_to_establish: list[str] = Field(
        default_factory=list,
        description="Concrete facts the section must state.",
    )
    required_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that support the facts in this section.",
    )


class PlannedDocument(BaseModel):
    """A single planned output document."""

    name: str = Field(
        ...,
        description="Output filename, e.g. README.md, ARCHITECTURE.md.",
    )
    applicable: bool = Field(
        ...,
        description="Whether this document applies to the repository.",
    )
    reason_if_not_applicable: str | None = Field(
        default=None,
        description="Explanation when the document is not applicable.",
    )
    sections: list[DocumentSection] = Field(default_factory=list)
    depends_on: list[str] = Field(
        default_factory=list,
        description="Document names this document depends on.",
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        # Reject path traversal and absolute paths in document names.
        bad = {"..", "/", "\\"}
        if any(b in v for b in bad):
            raise ValueError(f"Document name must not contain path separators: {v}")
        return v


class DocumentationPlan(BaseModel):
    """Structured plan for which documents to generate and what evidence to cite."""

    documents: list[PlannedDocument] = Field(default_factory=list)
    missing_information: list[str] = Field(
        default_factory=list,
        description="Facts that could not be determined from available evidence.",
    )
    potential_contradictions: list[str] = Field(
        default_factory=list,
        description="Conflicts between evidence sources to preserve for verification.",
    )
    verification_requirements: list[str] = Field(
        default_factory=list,
        description="Checks the verifier should perform.",
    )
