# AGENTS.md

Notes for coding agents (Claude Code, Codex, Cursor) working in this repo.
People should start with [README.md](README.md).

Hawlak turns a clinician-approved discharge plan into an Arabic voice note in
the patient's dialect, sends it on WhatsApp, collects medicine-box photos and
creates a pharmacist-review event. The AI changes wording and dialect only.

## Who owns what

| Path | Owner | Stack |
|---|---|---|
| `apps/api` | Haya | Python 3.12, FastAPI, SQLAlchemy, Alembic, uv |
| `apps/dashboard` | Retaj | React + TypeScript, Vite |
| `packages/contracts`, `docs/integration-contract.md` | both | Zod |
| `docs/design-system` | both | Tokens and screen references for UI work |

Stay inside the app you were asked to change. Changes to the contract need a
pull request reviewed by both Haya and Retaj.

## Rules

- Synthetic patients and fictional medicines only. Never commit `.env`, real
  phone numbers, patient data or generated audio.
- Clinical content comes only from the approved plan. Nothing reaches a patient
  until its exact script is approved.
- Never log tokens or full phone numbers (last 4 digits only).
- Medicine photos are stored, never interpreted.
- `apps/api` holds no UI code. `apps/dashboard` holds no AI, WhatsApp, database
  or storage code; it only calls the API.
- Write the test first. Work is done when the checks below pass.
- Branches: `haya/<feature>` or `retaj/<feature>`. `main` stays demo-ready.

## Commands

From the repo root:

| Task | Command |
|---|---|
| Start Postgres and MinIO | `docker compose up -d postgres minio minio-init` |
| Run the API (port 3000) | `npm run dev:api` |
| Run the dashboard (port 5173) | `npm run dev -w apps/dashboard` |
| Node checks | `npm run typecheck && npm test && npm run build` |
| API tests | `uv run --directory apps/api pytest` |
| API lint | `uv run --directory apps/api ruff check . && uv run --directory apps/api ruff format --check .` |
| Keyless demo | `uv run --directory apps/api python -m scripts.demo --mock --case abu-mohammed` |

Tests use mocks; no provider keys are needed. Keep `DEMO_PROVIDER_MODE=mock`.
