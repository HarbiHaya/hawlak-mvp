# Hawlak MVP

Hawlak turns a clinician-approved discharge plan into an Arabic WhatsApp voice
note, collects medicine-box photos, and creates a pharmacist review task.

This repository is a synthetic local prototype. It is not approved for real
patients or real clinical data. OpenAI may adapt wording and Saudi dialect only;
it cannot add or change clinical facts. A human must approve the exact script
before audio is generated or sent.

## Repository layout

| Path | Purpose |
|---|---|
| `apps/api` | FastAPI backend, provider integrations, persistence and tests |
| `apps/dashboard` | Retaj's React/Vite dashboard workspace and handoff |
| `packages/contracts` | Shared Zod event contract |
| `fixtures` | Synthetic أبو محمد demo input and expected event |
| `docs/integration-contract.md` | Dashboard/API contract |
| `docs/live-demo-runbook.md` | Controlled phone rehearsal |
| `docs/setup` | WhatsApp provider setup |
| `docs/design-system` | Brand tokens and screen references for the dashboard |

The backend owns OpenAI, ElevenLabs, WhatsApp, webhooks and media storage. The
dashboard calls authenticated backend routes and never receives provider or
storage credentials.

## Stack

- Python 3.12, FastAPI, Pydantic, SQLAlchemy and Alembic
- PostgreSQL 17 and an isolated MinIO/S3-compatible bucket
- OpenAI Responses API with Structured Outputs
- ElevenLabs v4 with a native Saudi Arabic voice and OGG/Opus output
- Meta WhatsApp Cloud API or Twilio WhatsApp Sandbox
- TypeScript/Zod shared contracts; React/Vite dashboard

## Local setup

Requirements: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/),
Node.js 22 and npm. Install ffmpeg so `ffprobe` can validate generated audio.

```bash
cp .env.example .env
docker compose up -d postgres minio minio-init
npm ci
npm run dev:api
```

Fill `.env` with local credentials before using live providers. Keep
`DEMO_PROVIDER_MODE=mock` for normal development. Never commit `.env`.

The API runs at `http://127.0.0.1:3000`; interactive documentation is at
`http://127.0.0.1:3000/docs`. MinIO is isolated to S3 port `19000` and console
port `19001`.

Check the runtime:

```bash
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/health/storage
```

If this repository is under macOS Documents/iCloud, keep the Python environment
outside the synced folder:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv"
```

## Verification

Run every check before opening a pull request:

```bash
npm ci
npm run typecheck
npm test
npm run build

UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv" \
  uv run --directory apps/api ruff check .
UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv" \
  uv run --directory apps/api ruff format --check .
UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv" \
  uv run --directory apps/api pytest
```

GitHub Actions runs the same Node and Python checks.

## Synthetic demo

Run the complete local workflow without provider keys, Docker or network:

```bash
UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv" \
  uv run --directory apps/api python -m scripts.demo --mock --case abu-mohammed
```

The fixture is intentionally fictional and is not clinically reviewed. For a
controlled live test-number rehearsal, follow
[`docs/live-demo-runbook.md`](docs/live-demo-runbook.md).

## Dashboard handoff

Retaj should start with [`apps/dashboard/README.md`](apps/dashboard/README.md)
and [`docs/integration-contract.md`](docs/integration-contract.md). The backend
already provides:

- a validated Hijazi, Najdi and Southern Saudi dialect catalog;
- synthetic case creation and exact-script approval;
- pharmacist review-event polling;
- authenticated medicine-photo retrieval;
- idempotent review outcomes.

The shared event contract and offline fixture let dashboard work begin without
OpenAI, ElevenLabs, WhatsApp, PostgreSQL or MinIO running.

## Collaboration rules

- `main` stays demo-ready; use `haya/<feature>` and `retaj/<feature>` branches.
- Use pull requests for shared contract changes.
- Never commit tokens, real phone numbers, patient data, generated media or
  local database volumes.
- Keep AI, WhatsApp and media logic out of `apps/dashboard`.
- Keep dashboard UI code out of `apps/api`.
- Preserve exact-script human approval and deterministic clinical-fact checks.

The architecture source and rendered SVG are in `docs/architecture/`.
