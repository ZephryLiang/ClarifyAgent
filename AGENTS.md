# AGENTS.md

## Cursor Cloud specific instructions

### Project layout
`ClarifyAgent` (求职 Agent) is an agentic job-seeking assistant. Two services:
- `backend/` — FastAPI + agent harness (Python, `requires-python >=3.10`). REST + SSE at `http://127.0.0.1:8000` (`/docs` for OpenAPI).
- `frontend/` — React + Vite + TS + Tailwind SPA at `http://127.0.0.1:5173` (dev server proxies `/api` → `:8000`, see `frontend/vite.config.ts`).

Standard commands live in `README.md` (快速开始 / 开发与质量) and CI in `.github/workflows/ci.yml`. Prefer those; notes below only cover non-obvious caveats.

### Key caveat: the code lives on a feature branch, not `main`
The `main` branch contains only a placeholder `README.md`. The actual application code is on the `cursor/job-seeker-agent-ed2e` branch. Branch off of that (not `main`) when working on the app.

### Running services (dev)
Python deps are installed into a virtualenv at `/workspace/.venv` (the update script creates/refreshes it). Always invoke backend tools via that venv, e.g. `/workspace/.venv/bin/uvicorn`, `/workspace/.venv/bin/pytest`.

- Backend dev server: from `backend/`, `/workspace/.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Frontend dev server: from `frontend/`, `npm run dev`
- Start the backend before (or alongside) the frontend so the `/api` proxy resolves.

### Offline / no-secrets mode (important)
The app **degrades gracefully with zero API keys** — with no LLM provider configured (`/api/status` → `"llm_enabled": false`), every feature runs on deterministic offline engines and the full UI/API still works. No secrets are required to run, test, or demo. To enable real LLM calls, set provider keys (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`) as env vars; routing priority is controlled by `JOBSEEKER_PROVIDER_PRIORITY`. See `backend/app/config.py`.

### Lint / type / test
From `backend/`: `/workspace/.venv/bin/ruff check app tests`, `/workspace/.venv/bin/mypy app`, `/workspace/.venv/bin/pytest -q`.
Note: `mypy app` currently reports 2 pre-existing errors (`_client` attribute inferred as `None` in `app/gateway/openai_adapter.py` and `anthropic_adapter.py`); these are not caused by environment setup.

### Local state
Backend writes a SQLite DB (`backend/jobseeker.db`) and Obsidian exports (`backend/exports/`) on use; both are git-ignored. Safe to delete to reset state.
