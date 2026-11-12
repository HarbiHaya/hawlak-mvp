# Hawlak prototype solution

## Product promise

Hawlak turns a clinician-approved discharge plan into short Saudi Arabic voice
notes, then keeps the patient and pharmacist connected through WhatsApp photos
and audio-guided medication reminders. The prototype is deliberately designed
for people who may not read.

This repository uses only synthetic cases and fictional medicines. It is not a
medical device and is not ready for real patient data.

## Actors and journeys

### Clinician or demo operator

1. Loads the approved synthetic plan.
2. Chooses Hijazi, Najdi or broadly understandable Southern Saudi.
3. Reviews two generated scripts: a session and medicine summary ending with a
   spoken photo request, then recovery instructions and warning signs.
4. Confirms the deterministic fact check and approves the exact checksum.
5. Sends the two voice notes to the test phone.

The AI may change wording, ordering for spoken clarity and dialect only. The
approved plan remains the only source of clinical facts.

### Patient

1. Hears the two voice notes without needing to read.
2. Sends one clear photo per medicine box.
3. Later receives a spoken reminder followed by their own medicine photo.
4. Hears that button `١` means “taken” and button `٢` means “not yet,” then taps
   one numeric button.

### Pharmacist

1. Sees a replay-safe task after the expected photos arrive.
2. Reviews opaque stored photos; Hawlak does not identify medicines with AI.
3. Records matched, mismatch, unclear photo or contact patient.
4. Can trigger the audio-guided reminder during the controlled demo.

## Prototype architecture

- **Dashboard:** React/TypeScript, Arabic-first RTL, memory-only local token.
- **API:** FastAPI, Pydantic, SQLAlchemy and strict authenticated internal routes.
- **Text AI:** OpenAI Structured Outputs with dialect profiles and copied-fact
  comparison.
- **Voice AI:** ElevenLabs Arabic OGG/Opus after exact human approval.
- **Messaging:** Twilio WhatsApp Sandbox for the demo; Meta adapter remains
  isolated and available.
- **Storage:** Hawlak-only MinIO bucket and PostgreSQL instance.
- **Public boundary:** webhook-only app on port 3001; internal routes stay on
  local port 3000.

## Saudi dialect product rules

| Dialect | Intended voice | Guardrails |
|---|---|---|
| Hijazi | Warm urban western Saudi speech | No Egyptian wording or exaggerated slang |
| Najdi | Clear, direct contemporary central Saudi speech | No Bedouin caricature or Gulf mixing |
| Southern Saudi | Light, broadly understandable regional flavor | No invented hyper-local spelling |

Every output must be short, spoken, respectful and unambiguous. Prompts ban
headings, markdown, emojis, diagnosis, new advice and medicine interpretation.

## Sender identity decision

Twilio Sandbox is the correct judge-demo transport because it needs no
registered sender, but its shared number always shows Twilio branding. A Hawlak
profile name, photo and dedicated number require Twilio WhatsApp Self Sign-up.
The prepared profile image is
`docs/design-system/assets/hawlak-whatsapp-profile.png`, and the repeatable human
setup is `scripts/setup_live_demo.sh`.

## Demo acceptance criteria

- Two approved voice notes reach the joined test phone.
- A synthetic medicine photo reaches the webhook and private object storage.
- One pharmacist task appears without duplication.
- The dashboard can send an audio-guided reminder with the same photo.
- Buttons display only `١` and `٢`; the webhook records `taken` or `not_yet`.
- Delivery status and inbound choice are present in the audit timeline.
- No secret, full phone number, generated audio or patient data is committed.

## Explicitly outside this prototype

- Real patient care or production deployment.
- Automated medicine recognition or clinical interpretation.
- Unreviewed AI-generated clinical content.
- Production identity, authorization, consent, retention and monitoring.
- Guaranteed WhatsApp display-name approval or an Official Business Account.
