"""Application configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration for the documentation agent.

    All values are sourced from environment variables (or a `.env` file when
    present via python-dotenv). Real credentials must never be committed.
    """

    model_provider: str = Field(
        default="openrouter",
        description="Model provider: 'openrouter' or 'nim'.",
    )
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key (required when model_provider='openrouter').",
    )
    openrouter_model: str = Field(
        default="openrouter/auto",
        description="Model used for planning/generation/verification via OpenRouter.",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter OpenAI-compatible base URL.",
    )
    nim_api_key: str | None = Field(
        default=None,
        description="NVIDIA NIM API key (required when model_provider='nim').",
    )
    nim_model: str = Field(
        default="meta/llama-3.1-8b-instruct",
        description="NVIDIA NIM model used for planning/generation/verification.",
    )
    nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="NVIDIA NIM OpenAI-compatible base URL.",
    )
    github_token: str | None = Field(
        default=None,
        description="Optional GitHub token for private repos / higher rate limits.",
    )
    docs_output_dir: str = Field(
        default="output",
        description="Base directory for generated documentation.",
    )
    max_repository_size_mb: int = Field(
        default=100,
        description="Maximum repository size in MB.",
    )
    max_files_to_analyze: int = Field(
        default=200,
        description="Maximum number of files to analyze per repo.",
    )
    max_file_size_kb: int = Field(
        default=512,
        description="Maximum individual file size in KB.",
    )
    max_revision_attempts: int = Field(
        default=2,
        description="Maximum revision attempts after initial generation.",
    )
    request_timeout_seconds: int = Field(
        default=30,
        description="HTTP request timeout in seconds.",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()


def validate_credentials(provider: str | None = None) -> None:
    """Raise a clear error if model credentials are missing.

    Called before any model-backed stage runs so failure happens early with a
    user-facing message rather than an opaque provider error. Reads current
    environment via a fresh settings instance so it picks up variables set
    after module import.

    Args:
        provider: The model provider to validate credentials for. Defaults to
            ``settings.model_provider`` ("openrouter" or "nim").
    """
    settings = Settings()
    provider = provider or settings.model_provider
    if provider == "nim":
        if not settings.nim_api_key:
            raise RuntimeError(
                "NIM_API_KEY is not set. Provide a real NVIDIA NIM API key "
                "(e.g. from https://build.nvidia.com) or set the environment "
                "variable before running generation."
            )
    else:
        if not settings.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and "
                "provide a real OpenRouter API key, or set the environment "
                "variable before running generation."
            )
