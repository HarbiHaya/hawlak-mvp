# Hawlak MVP

Hawlak turns an existing discharge document into an insurer-approved follow-up
journey: one minimized WhatsApp voice note, approved medication images with
`1`/`2` replies, scheduled conversational calls, and caregiver status.

This repository is a synthetic local prototype. It is not approved for real
patients or real clinical data. OpenAI may adapt wording and Saudi dialect only;
it cannot add or change clinical facts. A human must approve the exact script
before audio is generated or sent.

## Repository layout

| Path | Purpose |
|---|---|
| `apps/api` | FastAPI backend, provider integrations, persistence and tests |
| `apps/dashboard` | Bilingual hospital, insurer and caregiver workspaces |
| `apps/agent` | Constrained LiveKit call agent and authenticated dispatch service |
| `packages/contracts` | Shared Zod event contract |
| `fixtures` | Synthetic patient demo input and expected event |
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
- Meta WhatsApp Cloud API for the demo; provider adapters preserve the Saudi production seam
- LiveKit and Telnyx for demo calls; ElevenLabs for exact approved speech
- TypeScript/Zod shared contracts; React/Vite dashboard

## Local setup

Requirements: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/),
Node.js 22 and npm. Install ffmpeg so `ffprobe` can validate generated audio.

```bash
cp .env.example .env
docker compose up -d postgres minio minio-init
npm ci
npm run dev:api
npm run dev -w apps/dashboard
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

## Complete role-based prototype

The dashboard is implemented in [`apps/dashboard`](apps/dashboard/README.md).
The hospital uploads a synthetic discharge PDF and selects the patient language.
The insurer reviews extracted content, chooses service eligibility, edits and
approves the exact voice and call scripts, approves medication images, and
dispatches the journey. The caregiver sees only adherence state and required
action. The patient remains in WhatsApp and telephone channels and does not need
to open Hawlak or follow a link.

The end-to-end product and safety decisions are in
[`docs/prototype-solution.md`](docs/prototype-solution.md). To configure the
Meta, LiveKit, Telnyx, speech-provider and hosted-demo values, run:

```bash
./scripts/setup_live_demo.sh
```

The wizard writes only the required local `.env` values. For the live host and
the WhatsApp session constraint, follow
[`docs/setup/live-demo-stack.md`](docs/setup/live-demo-stack.md).

## Collaboration rules

- `main` stays demo-ready; use `haya/<feature>` and `retaj/<feature>` branches.
- Use pull requests for shared contract changes.
- Never commit tokens, real phone numbers, patient data, generated media or
  local database volumes.
- Keep AI, WhatsApp and media logic out of `apps/dashboard`.
- Keep dashboard UI code out of `apps/api`.
- Preserve exact-script human approval and deterministic clinical-fact checks.

The architecture source and rendered SVG are in `docs/architecture/`.

The next live-delivery milestone is defined in
[`../26_hawlak_live_phone_delivery_implementation.md`](../26_hawlak_live_phone_delivery_implementation.md):
an authorized tester enters a number in the dashboard, receives a real WhatsApp
voice note, and receives a LiveKit-powered conversational telephone call. The
external demo provider profile is intentionally separate from the Saudi-hosted
production provider profile recorded in
[`docs/adr/0003-separate-demo-and-saudi-production-provider-profiles.md`](docs/adr/0003-separate-demo-and-saudi-production-provider-profiles.md).
