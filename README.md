# GitHub-to-Docs Agent

AI-powered documentation agent that generates accurate, evidence-grounded technical documentation from any public GitHub repository URL.

Built as a portfolio project demonstrating LangGraph orchestration, LLM provider abstraction, structured output validation, and safe artifact generation.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Repository Analysis** | Validates GitHub URLs, acquires repository snapshots, builds file inventories, and extracts code symbols with line-level provenance |
| 📝 **Evidence-Grounded Generation** | Every documentation claim is backed by cited evidence IDs pointing to specific files and line ranges |
| 🔄 **LangGraph Workflow** | Deterministic pipeline: Validate → Acquire → Inspect → Plan → Prepare Evidence → Generate → Verify → (Revise) → Finalize |
| ✅ **LLM Verification** | Generated docs are verified against source evidence; serious findings trigger targeted section revision |
| 🤖 **Multi-Provider LLM** | OpenRouter and NVIDIA NIM providers with a shared interface — swap providers via env var or CLI flag |
| 🛡️ **Secret Redaction** | API keys, tokens, and passwords are redacted from evidence before reaching the model |
| 🖥️ **CLI + FastAPI** | Typer CLI for local use; FastAPI service with `GET /health` and `POST /v1/documentation/generate` |
| 🧪 **122 Tests** | Offline test suite with mocked models — no paid API calls required |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLI  or  FastAPI                           │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
                      ┌──────────────────┐
                      │   AppService     │
                      └──────────┬───────┘
                                 ▼
        ┌──────────────────────────────────────────────────────┐
        │  LangGraph StateGraph (planner / generator / verifier) │
        └──────────┬──────────────┬──────────────┬──────────────┘
                   ▼              ▼              ▼
              Validate → Acquire → Inspect → Plan → Prepare → Generate → Verify → (Revise) → Finalize
                   ▲                                                          │
                   └────────────────────────── targeted revision ─────────────┘
                                 ▼
                          ┌──────────┐
                          │ Output:  │
                          │ README.md│
                          │ Report   │
                          └──────────┘
```

### Key design decisions

- **Provider-agnostic model client**: `OpenRouterModelClient` and `NimModelClient` share the same `generate_text` / `generate_structured` interface, so planner, generator, and verifier never import a provider directly
- **Never-raise service layer**: `AppService.generate()` catches all failures and returns a `RunReport` with `status=failed` — the CLI and API never crash
- **Bounded retries with exponential backoff**: Transient model failures (502, 503, 504, timeout) are retried with jitter; auth errors fail fast
- **Atomic file writes**: Documents are written via temp-file + `os.replace` to avoid partial/corrupt output on interruption
- **Path containment**: Output paths are validated to prevent path traversal; executable file types (`.py`, `.sh`, `.bat`) are refused

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- An OpenRouter API key (https://openrouter.ai) **or** NVIDIA NIM API key (https://build.nvidia.com)

### Install

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env
```

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### Configure

Edit `.env` with your provider credentials:

```ini
MODEL_PROVIDER=openrouter        # or "nim"
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openrouter/auto

# NVIDIA NIM (alternative provider)
NIM_API_KEY=...
NIM_MODEL=meta/llama-3.1-8b-instruct
NIM_BASE_URL=https://integrate.api.nvidia.com/v1

DOCS_OUTPUT_DIR=output
```

### Run via CLI

```powershell
# OpenRouter (default provider)
github-to-docs https://github.com/owner/repository

# NVIDIA NIM
github-to-docs https://github.com/owner/repository --provider nim --model meta/llama-3.1-8b-instruct

# Custom output directory
github-to-docs https://github.com/owner/repository --output ./my-docs --verbose
```

Output is written to `<output>/<repo>/<run_id>/README.md` plus a `DOCUMENTATION_REPORT.md`.

### Run via FastAPI

```powershell
uvicorn github_to_docs.api.main:app --reload
```

```bash
# Health check
curl http://localhost:8000/health

# Generate documentation
curl -X POST http://localhost:8000/v1/documentation/generate \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repository", "provider": "openrouter"}'
```

## 🧪 Testing

All tests run offline with mocked models — no paid API calls required:

```powershell
pytest
```

Run with coverage:

```powershell
pytest --cov=github_to_docs
```

Run lint:

```powershell
ruff check src/ tests/
```

**Test summary:** 122 tests passing, 0 ruff violations.

## 📊 Example Output

Running against a Streamlit data-analysis repo produces:

```
# README.md

## Project Overview

The repository hosts a Streamlit web application for data analysis and automation.
[ev:documentation:README.md:1-98]

## Key Features

- **Missing Value Handling**: The app includes `handle_missing_values()` ... [ev:source_code:app.py:handle_missing_values:276]
- **Categorical Encoding**: Uses `LabelEncoder` ... [ev:source_code:app.py:encode_categorical_data:290]

## Installation Requirements

streamlit, pandas, numpy, matplotlib, seaborn, scikit-learn [ev:dependency_manifest:requirements.txt:1-7]
```

And `DOCUMENTATION_REPORT.md` contains run metadata, verification summary, and any findings.

## 🎯 Portfolio Highlights

For interview discussions, these are the engineered parts worth walking through:

1. **LangGraph orchestration** — Stateful cyclic workflow with conditional revision edges; not just a linear LLM chain
2. **Structured output validation** — Pydantic `DocumentationPlan` and `VerificationFinding` schemas reject invalid LLM output at parse time
3. **Evidence traceability** — Every generated claim cites a bounded evidence excerpt with file, line range, and symbol
4. **Defensive service layer** — `AppService` never raises; all failure modes produce a machine-readable `RunReport`
5. **Multi-provider abstraction** — OpenRouter and NVIDIA NIM behind a common interface; adding a new provider is one class + one factory case
6. **Security-conscious defaults** — Secret redaction, path containment, executable-file rejection, URL allow-listing (GitHub only)

## 📁 Project Structure

```
github-to-docs/
├── pyproject.toml          # Package config, entry point, dependencies
├── .env.example            # Copy to .env and fill in real keys
├── README.md
├── src/
│   └── github_to_docs/
│       ├── cli/main.py          # Typer CLI
│       ├── api/main.py          # FastAPI service
│       ├── services/__init__.py # AppService (orchestrates graph)
│       ├── generation/          # Model clients + planner + generator
│       ├── graph/               # LangGraph workflow + nodes + state
│       ├── verification/        # Deterministic + LLM verification
│       ├── evidence/            # Registry + redaction + extraction
│       ├── repository/          # URL validation + acquisition + inventory
│       ├── output.py            # Atomic, path-contained writing
│       ├── config.py            # Pydantic settings + credential validation
│       └── models.py            # RunReport, VerificationFinding, etc.
└── tests/
    ├── unit/                    # 122 offline tests with mocked models
    └── integration/             # Graph end-to-end tests
```

## 🛣️ Roadmap

- [ ] GitHub App / OAuth authentication for private repositories
- [ ] Multi-document output (API.md, architecture.md, contributing.md)
- [ ] Web UI for browsing generated documentation
- [ ] CI/CD integration (documentation on every push)
- [ ] Evaluation dashboard comparing model providers

## 📄 License

MIT

---

Built with LangGraph, LangChain, FastAPI, Typer, and Pydantic.
