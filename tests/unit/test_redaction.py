"""Unit tests for secret redaction (offline, no network)."""

from github_to_docs.evidence.redaction import redact_secrets


def test_redacts_api_key_assignment() -> None:
    text = 'API_KEY = "sk-live-1234567890abcdef"\n'
    redacted, was_redacted = redact_secrets(text)
    assert was_redacted
    assert "sk-live-1234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted
    assert "API_KEY" in redacted


def test_redacts_password() -> None:
    text = "password=supersecret123"
    redacted, was_redacted = redact_secrets(text)
    assert was_redacted
    assert "supersecret123" not in redacted


def test_redacts_bearer_token() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    redacted, was_redacted = redact_secrets(text)
    assert was_redacted
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted


def test_no_redaction_when_no_secret() -> None:
    text = "def hello():\n    return 'world'\n"
    redacted, was_redacted = redact_secrets(text)
    assert not was_redacted
    assert redacted == text


def test_empty_text() -> None:
    redacted, was_redacted = redact_secrets("")
    assert not was_redacted
    assert redacted == ""
