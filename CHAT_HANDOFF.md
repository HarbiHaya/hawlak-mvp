# Hawlak new-chat handoff

Read this file first. Do not reconstruct the project from the old chat. Inspect
only the files listed below unless the task needs more context.

## One-sentence product

Hawlak converts an existing hospital discharge document into an
insurer-approved follow-up journey that uses one minimized WhatsApp discharge
voice note, approved medication images and reminders, conversational telephone
calls, and a limited caregiver status view.

## Locked proof-of-concept scope

- One web application serves three roles: hospital, insurer, and caregiver.
- The hospital uploads the discharge PDF, enters the registered patient name
  and test phone number, and selects the language and dialect.
- The insurer decides service eligibility. The insurer reviews and edits the
  exact patient-facing scripts, medication entries, medication images, and call
  schedule. The insurer then approves the journey.
- The patient does not open Hawlak and does not follow a link.
- Meta WhatsApp sends the approved discharge voice note once.
- Meta WhatsApp sends each approved medication image with an approved reminder
  voice note and only two buttons: `1 = taken` and `2 = not yet`.
- A conversational telephone agent asks only approved questions. It listens to
  the answer. It transfers the live call when it detects a red flag,
  uncertainty, or a request for a person.
- The caregiver sees adherence state, the next call, and open escalation count.
  The caregiver does not see the source PDF, insurer notes, or full clinical
  record.
- A preferred form of address, such as a family nickname, is optional metadata.
  It is not the patient name.

## Demo and production boundaries

The Medathon demo uses:

- Meta WhatsApp Cloud API
- LiveKit Cloud
- Telnyx voice and SIP transfer
- ElevenLabs text-to-speech
- an OpenAI-compatible speech and classification interface
- one AWS EC2 instance (eu-north-1) with Docker Compose behind CloudFront, files in S3,
  secrets in SSM (`deploy/aws/`); live since 12 November 2026 in mock mode

The Saudi production profile replaces external speech and call processing with
Saudi-hosted models and contracted local carriers such as stc or Zain. Do not
claim that the demo stack is production-ready or automatically PDPL-compliant.
A real pilot still needs the controller's legal basis, notices, processor terms,
transfer assessment, security controls, retention rules, DPIA, and vendor review.

## Important WhatsApp constraint

A permanent Meta token does not permit free-form outbound audio at all times.
For the controlled demo, the synthetic recipient sends `START` during the
discharge handoff. Hawlak sends approved free-form media inside the active
customer-service window. Replies through `1` or `2` refresh the window. If the
window is closed, use an approved utility template or the scheduled call.

## Implemented architecture

```text
Hospital web ─┐
Insurer web ──┼─> Caddy /api ─> FastAPI ─> PostgreSQL + private MinIO
Caregiver web ┘                     │
                                    ├─> Meta WhatsApp Cloud API
                                    └─> call-control service
                                           └─> LiveKit room
                                                 └─> Telnyx call + transfer

Meta webhook ─> Caddy /webhooks ─> webhook-only FastAPI app
delivery worker ─> due approved delivery runs
```

Browser code never receives provider credentials or the internal API token.
Caddy adds the internal token to same-origin `/api` requests. Patient-facing
scripts become immutable after insurer approval.

## Important files

Start with these files:

- `README.md` — repository entry point
- `docker-compose.aws.yml`, `deploy/aws/README.md` — hosted AWS demo and going live
- `apps/api/app/services/journey_drafter.py` — drafts plus fidelity guard (prompt v2)
- `apps/api/app/services/insurer_systems.py` — mock eligibility and enrollment
- `docs/setup/live-demo-stack.md` — manual provider and hosting setup
- `scripts/setup_live_demo.sh` — interactive credential setup wizard
- `apps/dashboard/src/HospitalWorkspace.tsx` — hospital workflow
- `apps/dashboard/src/InsurerWorkspace.tsx` — insurer workflow
- `apps/dashboard/src/CaregiverWorkspace.tsx` — caregiver workflow
- `apps/dashboard/src/api.ts` — browser/API contract
- `apps/api/app/routes/care_journeys.py` — intake and role APIs
- `apps/api/app/services/care_journey_service.py` — approval and journey rules
- `apps/api/app/services/journey_delivery.py` — Meta and call dispatch
- `apps/agent/src/hawlak_agent/conversation.py` — deterministic call state
- `apps/agent/src/hawlak_agent/livekit_worker.py` — LiveKit and Telnyx worker
- `docs/adr/` — product and provider decisions

## Current verification baseline

The following checks pass:

- API: Ruff and 209 tests
- call agent: Ruff and 19 tests
- dashboard: TypeScript, 18 tests, and production build
- shared contracts: TypeScript, 3 tests, and production build
- Docker images: API, dashboard, and agent build successfully
- container smoke tests: API import, agent app creation, and Nginx config
- Compose configuration and setup-wizard shell syntax

Run the checks again after code changes:

```bash
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/ruff format --check apps/api
apps/api/.venv/bin/pytest apps/api/tests

apps/agent/.venv/bin/ruff check apps/agent
apps/agent/.venv/bin/ruff format --check apps/agent
apps/agent/.venv/bin/pytest apps/agent/tests

npm run typecheck
npm test
npm run build

bash -n scripts/setup_live_demo.sh
docker compose --env-file .env.example -f docker-compose.demo.yml config --quiet
```

## Work that still needs a human or live credentials

- Complete the Meta Business app, sender registration, payment method, permanent
  token, webhook subscription, and utility-template approval.
- Create the LiveKit project and the Telnyx SIP trunk. Test both the outbound
  call and SIP transfer.
- Select and test the Arabic voice and speech-to-text model.
- Put the provider keys in the local `.env` and run `deploy/aws/sync_keys.sh` (AWS hosting
  already exists). The Meta business "Hawlak" still needs a production number, payment
  method and a published app.
- Run one rehearsal with synthetic data only.
- Confirm that the test recipient sends `START` before WhatsApp dispatch.

## Known proof-of-concept limits

- The discharge PDF is parsed with `pypdf` (`apps/api/app/services/discharge_parser.py`)
  and pre-fills the insurer draft: medications, plus the voice-note text when the
  document and patient languages match. Parsing is deterministic and heading-based;
  scanned PDFs (no text layer) need manual entry until OCR is added. The insurer
  still checks and approves every line.
- The web role selector is a prototype. Production needs identity, organization,
  membership, and role-based authorization.
- The caregiver view is web-only and uses a case identifier in the prototype.
- Live provider delivery has not been executed without the user's credentials.
- OCR is only a candidate when a medication photo is missing. A human must verify
  the medication before Hawlak uses it.
- No real patient data, real phone number, provider secret, or generated patient
  media belongs in Git.

## Git rules

- Current working branch: `haya/complete-prototype`.
- Commit as `Haya <alharbiihaya@gmail.com>`.
- Do not add a Codex co-author.
- Do not push unless Haya asks.
- Preserve unrelated user changes.

## Prompt for the next chat

Copy this into a new chat:

> Continue the Hawlak MVP in this repository. Read `CHAT_HANDOFF.md` first and
> follow it as the source of truth. Then inspect only the files it lists that are
> relevant to my next request. Keep the locked product scope. Use synthetic data
> only. Do not hard-code provider values, phone numbers, patient data, or scripts.
> Keep all patient-facing clinical text human-approved and exact. Run the relevant
> checks before you commit. Commit as Haya, with no Codex attribution, and do not
> push unless I ask.
