# Hawlak MVP

Hawlak turns an existing discharge document into an insurer-approved follow-up
journey: one minimized WhatsApp voice note, approved medication images with
`1`/`2` replies, scheduled conversational calls, and caregiver status.

This repository is a synthetic local prototype. It is not approved for real
patients or real clinical data. OpenAI may adapt wording and Saudi dialect only;
it cannot add or change clinical facts. A human must approve the exact script
before audio is generated or sent.

## Status (12 November 2026)

### The product today

One bilingual (Arabic/English) web app with role-scoped demo login:

1. **Hospital** uploads the discharge PDF and enters the patient label, test phone
   number, language and dialect, and insurer member ID.
2. **Hawlak** reads the PDF (`pypdf`) and drafts the WhatsApp voice note, one
   reminder per medicine, and the call script. It also checks the member's
   eligibility with the insurer system. The insurer system is simulated by
   `MockInsurerSystems`.
3. **Insurer** reviews the case in five tabs: source, coverage, content,
   medications and journey. Each text shows whether it was generated or edited by
   the reviewer, and the reviewer can regenerate drafts. The reviewer schedules
   calls (24/48/72 hours, or an exact date and time; repeating daily, every 2 days
   or weekly; up to 14 calls), then approves. Approval needs an eligible member,
   records an enrollment reference and creates the delivery runs.
4. **Delivery worker** sends due runs. In mock mode every run is labelled
   "Simulated — not actually sent".
5. **Caregiver** sees adherence state, the next call and open escalations only.

Drafting uses a template, or OpenAI with prompt `journey-draft-v2` when live keys
are set. Every OpenAI draft passes a fidelity guard: the same numbers as the
source, exact medicine names, and every dose in the script. A draft that fails
falls back to the template.

The demo runs on AWS (eu-north-1): CloudFront → one EC2 instance (Docker Compose)
→ S3, with secrets in SSM. It is still in **mock mode**. See
[`deploy/aws/README.md`](deploy/aws/README.md).

### Done

- Full hospital → insurer → caregiver flow, in English and Arabic, with formal
  wording throughout.
- PDF parser that drafts the medicine list, voice note, reminders and call
  questions.
- Mock insurer systems: eligibility (IDs ending `99` are not found; IDs ending
  `00` have a lapsed policy) and enrollment references.
- Call calendar with exact time, repeat pattern and number of calls.
- Prompt v2 and the deterministic draft guard.
- PII gate. Approval is blocked when patient-facing text contains:
  - the full name or the phone number;
  - a national or Iqama number;
  - the member or policy number;
  - the case ID or the source filename.
  Drafts greet without a name unless a form of address is approved.
- Honest delivery labels in mock mode.
- AWS hosting with scripts:
  - `provision.sh`
  - `deploy.sh`
  - `sync_keys.sh`, which pushes provider keys from `.env` to SSM and redeploys
- Medicine-photo check ([design](docs/architecture/medicine-photo-check.md)):
  - The insurer approves medicine names only; there is no image upload.
  - After approval, Hawlak asks the patient (or the registered caregiver) to
    photograph each approved box by name. Each photo links to that medicine by slot.
  - In live mode, a low-detail vision read returns the printed label; code checks it
    against that one medicine. Identical photos are read once.
  - Fixed replies only. A mismatch alerts the reviewer, who confirms or marks
    follow-up. Reminders then carry the patient's matched or confirmed box photo.
- Checks: API 231 tests, dashboard 19 tests, contracts 3 tests, typecheck and build.

### Planned / next

- **Live providers**:
  - Meta WhatsApp production number on the Hawlak business. It has only a test
    number today, the app is in development mode, and there is no payment method.
  - OpenAI key.
  - ElevenLabs Saudi Arabic voice.
  - LiveKit project and Telnyx SIP trunk with +966 allowed and a tested transfer.
  - Then run `deploy/aws/sync_keys.sh`.
- WhatsApp message templates, so Hawlak can send outside the 24-hour window. Until
  then, the patient must message the business number first.
- Reconcile Retaj's pharmacist-review dashboard (on `main` from PR #1) with this
  branch.
- Contract review by Haya and Retaj of the new fields: `memberId`, `callPlan`
  schedule, `insurance`, `generatedDraft`, `caregiverPhoneE164`, `medicinePhotos` and the `photo_request` run.
- OCR for scanned PDFs, and a real insurer integration in place of the mock.
- Before any real data:
  - HTTPS from CloudFront to the origin.
  - Production identity and roles.
  - The registered name removed from the caregiver view.
  - The PDPL work in ADR 0003.
- Show the patient's `taken`/`not_yet` replies in the caregiver view. Hawlak
  records the replies today, but the caregiver view doesn't show them.
- The data flow, privacy boundary, threat model and status of each component are
  in
  [`docs/architecture/platform-data-privacy.md`](docs/architecture/platform-data-privacy.md).

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
| `deploy/aws`, `docker-compose.aws.yml` | AWS demo hosting (CloudFront, EC2, S3, SSM) |

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
npm run dev:worker   # sends approved journey steps (mock mode: no real messages)
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
The hospital uploads a synthetic discharge PDF, the patient language and the
insurer member ID. The insurer reviews the generated drafts against the source,
confirms coverage, edits and approves the exact voice and call scripts,
schedules the calls, and approves the journey. The caregiver sees only adherence state and required
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
The current platform data flow, privacy boundary, threat summary, Saudi-hosted
alternative, and evidence-based component status are in
[`docs/architecture/platform-data-privacy.md`](docs/architecture/platform-data-privacy.md).

The next milestone is live delivery: an authorized tester enters a number in the
dashboard, receives a real WhatsApp voice note, and then receives a
LiveKit-powered conversational telephone call. The external demo provider profile is intentionally separate from the Saudi-hosted
production provider profile recorded in
[`docs/adr/0003-separate-demo-and-saudi-production-provider-profiles.md`](docs/adr/0003-separate-demo-and-saudi-production-provider-profiles.md).
