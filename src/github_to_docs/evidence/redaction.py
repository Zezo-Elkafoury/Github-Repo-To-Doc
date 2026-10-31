"""Secret redaction for untrusted repository content.

Repository content is treated as untrusted data. Likely secrets (API keys,
tokens, passwords) are redacted before content reaches the model or is stored
as evidence. The redaction reports that a value was removed without
reproducing it.
"""

from __future__ import annotations

import re

# Patterns that indicate a likely secret value. These are intentionally broad
# to err on the side of redacting too much rather than too little.
_SECRET_PATTERNS = [
    # Generic key/token assignments: API_KEY = "..." or apiKey: "..."
    re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
        r"private[_-]?key|password|passwd|pwd|client[_-]?secret|"
        r"signing[_-]?key|session[_-]?token)\s*[:=]\s*[\"']?([^\"'\s;}]+)[\"']?",
    ),
    # Bearer tokens.
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/]+={0,2}"),
    # Generic hex/long tokens (32+ chars of hex or base64-like).
    re.compile(r"[A-Za-z0-9+/]{32,}={0,2}"),
]

REDACTION_MARKER = "[REDACTED]"


def redact_secrets(text: str) -> tuple[str, bool]:
    """Redact likely secret values from ``text``.

    Returns a tuple of ``(redacted_text, was_redacted)``. The redacted text
    replaces secret values with ``[REDACTED]`` but never reproduces the
    original value.
    """
    if not text:
        return text, False

    redacted = text
    was_redacted = False

    for pattern in _SECRET_PATTERNS:
        new_text, n = pattern.subn(lambda m: _replace_match(m), redacted)
        if n > 0:
            was_redacted = True
        redacted = new_text

    return redacted, was_redacted


def _replace_match(match: re.Match) -> str:
    """Replace a matched secret with the redaction marker.

    For key=value patterns, keep the key but redact the value. For standalone
    tokens, replace the whole match.
    """
    groups = match.groups()
    # If there's a named key group, preserve the key and redact the value.
    if groups and groups[0]:
        key = groups[0]
        # Find the value portion: everything after the first : or =.
        # Reconstruct as KEY = [REDACTED]
        sep = " = "
        if ":" in match.group(0):
            sep = ": "
        return f"{key}{sep}{REDACTION_MARKER}"
    return REDACTION_MARKER
