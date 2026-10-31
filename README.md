# GitHub-to-Docs Agent

AI engineering portfolio project that generates accurate, repository-specific
technical documentation from a GitHub URL.

## Status

Milestone 1 (project foundation) complete. See `docs/` for architecture and
evaluation plans as they are added.

## Stack

- Python 3.11+
- LangGraph, LangChain, OpenRouter (OpenAI-compatible)
- Pydantic, FastAPI, Typer, httpx
- pytest, ruff

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# or: source .venv/bin/activate  # macOS/Linux

pip install -e ".[dev]"
cp .env.example .env
# edit .env with your OPENROUTER_API_KEY
```

## CLI

```bash
github-to-docs generate https://github.com/owner/repository
```

Options: `--output`, `--model`, `--max-files`, `--verbose`.

## FastAPI

```bash
uvicorn github_to_docs.api.main:app --reload
```

Endpoints: `GET /health`, `POST /v1/documentation/generate`.

## Tests

Default suite runs offline with mocked models (no paid API call required):

```bash
pytest
```

An opt-in real-model integration test exists and never runs in CI by default.
