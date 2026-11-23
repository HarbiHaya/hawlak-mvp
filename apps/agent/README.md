# Hawlak call agent

This app exposes an authenticated dispatch control and runs the LiveKit worker
that places one conversational follow-up call. Code picks every step from the
immutable insurer-approved plan returned by the Hawlak API. A chat model only
phrases those steps: it acknowledges replies and answers a question from the
approved voice note and reminder scripts (`approvedFacts`), or says the care
team will help. `speech_guard.py` replaces any generated sentence that carries a
number outside the approved content, or runs over 40 words, with the approved
question. Opening, completion and transfer scripts are spoken word for word.

A first unclear reply or question gets one clarification. A second one, a red
flag or a request for a person transfers the call: the agent dials the care team
into the room, and the transfer counts only when they press 1. Otherwise the
patient hears the fixed callback line and the call is recorded as failed. Each
call's turns are stored in Hawlak for the insurer workspace only.

## Interfaces

- `GET /health` is public and returns only status and mode.
- `POST /calls` requires `Authorization: Bearer <HAWLAK_CONTROL_TOKEN>` and an
  `Idempotency-Key`. Its JSON body has `callPlanId`, `caseId`, and `scheduledAt`.
  It never accepts a phone number or clinical script.
- The LiveKit job metadata contains only `call_plan_id`.
- The worker fetches `GET /internal/call-plans/{call_plan_id}` using
  `HAWLAK_INTERNAL_API_TOKEN`. The API is the sole source of dial target,
  responder target, and approved scripts.

The backend owns durable scheduling. It calls `POST /calls` when the stored
`scheduledAt` becomes due. The control app keeps a process-local replay cache;
the LiveKit room name is also derived from the idempotency key without exposing
it.

## Local mock

Install and run tests:

```bash
uv sync --directory apps/agent
uv run --directory apps/agent pytest
```

Start the keyless control app with the mock variables from `.env.example`:

```bash
uv run --directory apps/agent uvicorn hawlak_agent.web:create_app_from_env \
  --factory --port 3100
```

Exercise the exact production conversation state machine with a synthetic plan:

```bash
uv run --directory apps/agent hawlak-agent-mock synthetic-call-plan.json \
  --answers clear,clear
```

## Live demo

Run the control process and worker as separate processes from the same image:

```bash
uv run --directory apps/agent uvicorn hawlak_agent.web:create_app_from_env \
  --factory --host 0.0.0.0 --port 3100
uv run --directory apps/agent hawlak-agent start
```

Live mode requires a LiveKit project, a stored outbound SIP trunk connected to
Telnyx, an enabled transfer path (`SIP REFER` or a tested warm-transfer route),
OpenAI-compatible classification/STT access, and an ElevenLabs voice. All
provider origins, model IDs, credentials, trunk IDs, and voice IDs are supplied
through environment variables. The worker does not contain provider or patient
defaults.

The Telnyx connection must allow the destination countries used in the demo.
The responder number must also be reachable through the same trunk. Confirm a
real transfer in rehearsal; provider acceptance of the SIP request alone is
not evidence that the responder answered.
