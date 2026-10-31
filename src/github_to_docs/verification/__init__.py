"""Verification package: deterministic + LLM-assisted documentation checks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from github_to_docs.evidence.registry import EvidenceRegistry, InvalidEvidenceReferenceError
from github_to_docs.generation.client import ModelClient
from github_to_docs.models import FindingSeverity, VerificationFinding
from github_to_docs.prompts import VERIFICATION_PROMPT

logger = logging.getLogger(__name__)


class DocumentVerifier:
    """Verifies generated documentation against available evidence.

    Runs deterministic checks first, then LLM-assisted evidence verification.
    Returns structured findings. May conclude evidence is insufficient.
    """

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    # ------------------------------------------------------------------ #
    # Deterministic checks
    # ------------------------------------------------------------------ #

    def verify_deterministic(
        self,
        document_name: str,
        section_title: str,
        content: str,
        inventory_files: list[str],
        evidence_registry: EvidenceRegistry,
    ) -> list[VerificationFinding]:
        """Run deterministic checks on a generated section."""
        findings: list[VerificationFinding] = []

        findings.extend(self._check_local_links(document_name, section_title, content))
        findings.extend(
            self._check_referenced_files(document_name, section_title, content, inventory_files)
        )
        findings.extend(self._check_secret_leakage(document_name, section_title, content))
        findings.extend(self._check_placeholders(document_name, section_title, content))
        findings.extend(
            self._check_evidence_citations(document_name, section_title, content, evidence_registry)
        )

        return findings

    def _check_local_links(
        self, document_name: str, section_title: str, content: str
    ) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
            _link_text, target = m.group(1), m.group(2)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if target.startswith("#"):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            findings.append(
                VerificationFinding(
                    severity=FindingSeverity.warning,
                    document=document_name,
                    section=section_title,
                    claim=f"Local link to '{target}'",
                    evidence_ids=[],
                    failure_reason=(
                        "Local link target cannot be verified to exist "
                        "(static check only; file not confirmed in inventory)."
                    ),
                    recommended_correction=(
                        "Verify the linked file exists in the repository or remove/adjust the link."
                    ),
                )
            )
        return findings

    def _check_referenced_files(
        self,
        document_name: str,
        section_title: str,
        content: str,
        inventory_files: list[str],
    ) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        inventory_set = set(inventory_files)
        for m in re.finditer(
            r"`([A-Za-z0-9_./\-]+\.(?:py|js|ts|json|toml|yaml|yml|cfg|txt|md))`",
            content,
        ):
            ref = m.group(1)
            if ref not in inventory_set:
                findings.append(
                    VerificationFinding(
                        severity=FindingSeverity.error,
                        document=document_name,
                        section=section_title,
                        claim=f"Referenced file '{ref}'",
                        evidence_ids=[],
                        failure_reason=(
                            f"File '{ref}' is not in the analyzed repository inventory."
                        ),
                        recommended_correction=(
                            "Correct the path to an existing file or remove the reference."
                        ),
                    )
                )
        return findings

    def _check_secret_leakage(
        self, document_name: str, section_title: str, content: str
    ) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        from github_to_docs.evidence.redaction import _SECRET_PATTERNS

        for pattern in _SECRET_PATTERNS:
            for _m in pattern.finditer(content):
                findings.append(
                    VerificationFinding(
                        severity=FindingSeverity.severe,
                        document=document_name,
                        section=section_title,
                        claim="Possible secret value in generated documentation",
                        evidence_ids=[],
                        failure_reason=(
                            "A likely secret (API key, token, password) appears "
                            "in the generated output."
                        ),
                        recommended_correction=(
                            "Remove the secret value and replace with [REDACTED]."
                        ),
                    )
                )
        return findings

    def _check_placeholders(
        self, document_name: str, section_title: str, content: str
    ) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        placeholder_patterns = [
            r"\[TODO\]",
            r"\[XXX\]",
            r"\{.*\}",
            r"TBD",
            r"PLACEHOLDER",
            r"<insert.*>",
        ]
        for pat in placeholder_patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                findings.append(
                    VerificationFinding(
                        severity=FindingSeverity.error,
                        document=document_name,
                        section=section_title,
                        claim=f"Placeholder text: {m.group(0)!r}",
                        evidence_ids=[],
                        failure_reason=(
                            "Generated documentation contains an unresolved placeholder."
                        ),
                        recommended_correction=(
                            "Replace the placeholder with evidence-backed content "
                            "or mark as unknown."
                        ),
                    )
                )
        return findings

    def _check_evidence_citations(
        self,
        document_name: str,
        section_title: str,
        content: str,
        evidence_registry: EvidenceRegistry,
    ) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        cited = set(re.findall(r"ev:[^\s\]]+", content))
        for eid in cited:
            if not evidence_registry.validate_reference(eid):
                findings.append(
                    VerificationFinding(
                        severity=FindingSeverity.error,
                        document=document_name,
                        section=section_title,
                        claim=f"Cites unknown evidence {eid}",
                        evidence_ids=[eid],
                        failure_reason=(f"Evidence ID {eid} does not exist in the registry."),
                        recommended_correction=(
                            "Cite a valid evidence ID or remove the unsupported claim."
                        ),
                    )
                )
        return findings

    # ------------------------------------------------------------------ #
    # LLM-assisted verification
    # ------------------------------------------------------------------ #

    def verify_llm(
        self,
        document_name: str,
        section_title: str,
        content: str,
        evidence_registry: EvidenceRegistry,
        evidence_ids: list[str],
    ) -> list[VerificationFinding]:
        """Ask the model to check whether evidence supports each claim."""
        excerpts: list[str] = []
        for eid in evidence_ids:
            try:
                item = evidence_registry.get(eid)
                excerpts.append(f"[{eid}] {item.content}")
            except (KeyError, InvalidEvidenceReferenceError):
                excerpts.append(f"[{eid}] [EVIDENCE NOT FOUND]")

        user = VERIFICATION_PROMPT.format(
            document_name=document_name,
            section_title=section_title,
            generated_content=content,
            evidence_excerpts="\n\n---\n\n".join(excerpts) if excerpts else "(no evidence)",
        )

        try:
            raw = self.model_client.generate_text(
                system=(
                    "You are a meticulous verification agent. Only mark claims "
                    "SUPPORTED when evidence directly backs them."
                ),
                user=user,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM verification failed: %s", exc)
            return []

        findings: list[VerificationFinding] = []
        try:
            data = self._extract_json_list(raw)
            for item in data:
                findings.append(
                    VerificationFinding(
                        severity=FindingSeverity(item.get("severity", "warning")),
                        document=document_name,
                        section=section_title,
                        claim=item.get("claim", ""),
                        evidence_ids=item.get("evidence_ids", []),
                        failure_reason=item.get("failure_reason", ""),
                        recommended_correction=item.get("recommended_correction", ""),
                    )
                )
        except Exception:  # noqa: BLE001
            logger.debug("Could not parse LLM verification output as JSON")

        return findings

    @staticmethod
    def _extract_json_list(raw: str) -> list[dict[str, Any]]:
        text = raw.strip()
        if text.startswith("```"):
            parts = text.split("```", 2)
            if len(parts) >= 3:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict)]

    # ------------------------------------------------------------------ #
    # Combined
    # ------------------------------------------------------------------ #

    def verify_section(
        self,
        document_name: str,
        section_title: str,
        content: str,
        inventory_files: list[str],
        evidence_registry: EvidenceRegistry,
        evidence_ids: list[str],
        use_llm: bool = True,
    ) -> list[VerificationFinding]:
        """Run deterministic + optional LLM verification on a section."""
        findings = self.verify_deterministic(
            document_name, section_title, content, inventory_files, evidence_registry
        )
        if use_llm:
            findings.extend(
                self.verify_llm(
                    document_name, section_title, content, evidence_registry, evidence_ids
                )
            )
        return findings

    @staticmethod
    def has_serious_findings(findings: list[VerificationFinding]) -> bool:
        """Return True if any finding is error or severe severity."""
        return any(f.severity in {FindingSeverity.error, FindingSeverity.severe} for f in findings)

    @staticmethod
    def findings_summary(findings: list[VerificationFinding]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        return counts


__all__ = ["DocumentVerifier"]
