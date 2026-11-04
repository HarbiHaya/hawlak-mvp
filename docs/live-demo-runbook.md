# Hawlak synthetic demo runbook

> **Synthetic prototype only. Not for clinical use.** Use Meta's test number and
> the fictional أبو محمد fixture only. Never enter real patient data or real
> medicine instructions.

## What is already connected

The backend can load the synthetic plan, create a schema-constrained Arabic
rewrite, reject changed clinical facts, bind approval to the exact script
checksum, create Opus audio, send the three-step WhatsApp sequence, receive
signed medicine-box photos, store them in Hawlak's isolated MinIO bucket and
publish one pharmacist-review event. Mock mode exercises the same state
transitions without external accounts.

Retaj integrates only with the authenticated routes documented in
[integration-contract.md](integration-contract.md): event polling, photo bytes
and review outcomes. She does not need Meta, OpenAI, ElevenLabs or MinIO keys.

## Before the live rehearsal

1. Docker Desktop must be running.
2. Keep `DEMO_PROVIDER_MODE=mock` for normal development. Change it to `live`
   only for the controlled rehearsal.
3. Configure valid `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` and an Arabic-capable
   `ELEVENLABS_VOICE_ID`. Do not use a cloned patient voice. The current local
   rehearsal uses **Fahad — Saudi, Warm & Confident**, `eleven_v4`, Arabic
   language enforcement, stability `0.35`, and similarity `0.80`.
4. In Meta's WhatsApp API setup, add the demo phone as an allowed recipient for
   the test number. From that phone, send any message to the test number shortly
   before the demo to open the 24-hour customer-service window.
5. In Meta App Dashboard → WhatsApp → Configuration, subscribe to `messages`.
   The callback URL is the current tunnel URL plus `/webhooks/whatsapp`; the
   verify token is the value already stored in `.env`.
6. OpenAI and ElevenLabs must have usable API credit. Meta's test number does
   not require registering Hawlak's future production number.

Do not run `source .env`; provider tokens can contain shell-significant text.
The Python settings loader reads `.env` directly. Keep every entry on its own
`NAME=value` line and rotate any token that appears in terminal output.

## Start the four terminals

Run every command from `/Users/haya/Documents/ChatGPT/medathon/hawlak-mvp`.

### Terminal 1 — PostgreSQL and Hawlak-only MinIO

```bash
docker compose up -d postgres minio minio-init
docker compose ps
DATABASE_URL=postgresql+psycopg://hawlak:hawlak@127.0.0.1:15432/hawlak \
  UV_PROJECT_ENVIRONMENT=/Users/haya/.cache/hawlak-api-venv \
  uv run --directory apps/api alembic upgrade head
```

Expected host ports are PostgreSQL `127.0.0.1:15432`, MinIO S3
`127.0.0.1:19000`, and MinIO console `http://127.0.0.1:19001`. These are
separate from Lucidya's PostgreSQL and MinIO.

### Terminal 2 — private/internal API

```bash
export UV_PROJECT_ENVIRONMENT=/Users/haya/.cache/hawlak-api-venv
npm run dev:api
```

The internal API is `http://localhost:3000`. Do not tunnel this port.

### Terminal 3 — webhook-only public application

```bash
export UV_PROJECT_ENVIRONMENT=/Users/haya/.cache/hawlak-api-venv
npm run dev:webhook
```

This application exposes only health and `/webhooks/whatsapp`; `/internal/*`
returns 404.

### Terminal 4 — temporary Meta callback tunnel

```bash
cloudflared tunnel --url http://localhost:3001
```

Copy the generated HTTPS origin into Meta as:

```text
https://<temporary-host>/webhooks/whatsapp
```

Do not put the verify token in the URL or terminal history. Update Meta whenever
the temporary tunnel hostname changes.

## Rehearse without any external keys

This is the reliable demo fallback and the first command to run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/haya/.cache/hawlak-api-venv \
  uv run --directory apps/api python -m scripts.demo --mock --case abu-mohammed
```

The command prints the generated checksum. Read the Arabic script, then type
that exact checksum. Expected result: three outbound message IDs, four stored
objects (one audio and three photos), one `pharmacist_review_requested` event,
and one replay-safe review outcome. No network or `.env` keys are used.

## Controlled live rehearsal

Restart the API after setting `DEMO_PROVIDER_MODE=live`, then run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/haya/.cache/hawlak-api-venv \
  uv run --directory apps/api python -m scripts.demo --live --case abu-mohammed
```

The command checks the fixture hash, ffprobe, API, MinIO, internal bearer
boundary, provider configuration and Meta test-number token before it creates
or sends anything. A failed required check stops the run. When checks pass it:

1. loads the synthetic case;
2. prints the exact generated Arabic script and checksum;
3. waits for the operator to type the same checksum;
4. sends disclosure → approved audio → photo request;
5. waits up to 120 seconds for the phone to send three synthetic box photos;
6. prints the contract-valid pharmacist-review event.

On the phone, expect the disclosure first, then one playable voice note, then
the photo request. Send three photos of obviously fictional/demo boxes. The API
acknowledges each photo. A returned Meta message ID proves acceptance by Meta,
not delivery; confirm the phone and delivery-status webhook before claiming a
successful rehearsal.

## Retaj handoff

Retaj needs these values at runtime, not committed to the dashboard bundle:

- API origin: `http://localhost:3000`
- dashboard origin configured in the backend, normally `http://localhost:5173`
- the shared internal demo bearer token, entered into the UI and held in memory
- fixture: `fixtures/expected-review-event.abu-mohammed.json`

Her first acceptance test is: poll the same event twice, upsert one task by
`eventId`, fetch each `mediaId`, and post the same outcome twice using one
`Idempotency-Key`.

## Recovery and fallback order

1. If any live preflight fails, use the mock command and Retaj's fixture mode.
2. If OpenAI fails, do not rewrite by hand inside the live workflow; use the
   already reviewed mock script and clearly label the demonstration as mock.
3. If ElevenLabs fails after approval, retry with the same checksum. If an
   approved matching audio object already exists, the backend reuses it.
4. If Meta fails, show the mock outbound sequence and the dashboard fixture;
   do not expose port 3000 or disable webhook signatures.
5. Keep the synthetic PDF or a screen recording as the final presentation
   backup.

## Rehearsal record

| Date | Automated mock | Live Meta/providers | Operator note |
|---|---|---|---|
| 2026-11-04 | Passed locally | Not run in this implementation session | Requires Haya's live OpenAI/ElevenLabs configuration and phone confirmation |
