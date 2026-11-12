# Hawlak live demo stack

This setup gives one test user a real WhatsApp message and a real telephone
call. It uses synthetic content only. It is not a production clinical setup.

## The shortest reliable hosting path

Use one Google Compute Engine VM for the hackathon. Run the Hawlak containers
with Docker Compose. Use LiveKit Cloud for the media room. Use Telnyx for the
telephone connection. Use Meta Cloud API for WhatsApp.

The VM is necessary for three reasons:

1. Meta must reach a stable HTTPS webhook.
2. Judges must reach the dashboard without a local tunnel.
3. The API and call worker need one stable environment for the rehearsal.

Caddy is the only public container. It terminates TLS and routes traffic:

- `/` goes to the dashboard.
- `/api/*` goes to the private Hawlak API.
- `/webhooks/*` goes to the signed public webhook application.

The browser does not receive the internal API token. Caddy adds it when it
forwards an API request. PostgreSQL, MinIO, the API, and the call worker stay on
the private Docker network.

## Accounts and values

### Meta WhatsApp

Create a Meta Business app and add the WhatsApp product. Test with Meta's free
number first. Then add the Telnyx number, receive the one-time SMS through a
temporary Telnyx messaging webhook, and register the number with the API version
shown on the Meta API Setup page. Save these runtime values:

- `META_GRAPH_API_VERSION`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_VERIFY_TOKEN`
- `META_APP_SECRET`

Use a permanent system-user access token for the deployed demo. Do not use the
short-lived token from the API Setup page. Store the six-digit registration PIN
in a password manager, not in Hawlak `.env`.

Set the callback URL to:

```text
https://YOUR_HOST/webhooks/whatsapp
```

Use the same `WHATSAPP_VERIFY_TOKEN` and subscribe the app to the `messages`
field. Add a payment method and approve the required utility templates before
the live outbound rehearsal.

#### WhatsApp session rule

A permanent access token does not make free-form outbound audio available at
all times. For the controlled demo, the synthetic recipient sends `START` to
the Hawlak number during the discharge handoff. Hawlak can then send the exact
approved voice note and medication image inside the active customer-service
window. A reply through button `1` or `2` refreshes that window.

If the window is closed, Hawlak must use an approved utility template to reopen
the conversation or use the scheduled telephone call. It must not silently
replace a template with unapproved free-form audio. Rehearse the `START` step
before the presentation and keep the approved template as the fallback.

Official guide: <https://developers.facebook.com/docs/whatsapp/cloud-api/get-started>

### LiveKit and Telnyx

Create a LiveKit Cloud project. Save:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Use a paid Telnyx account. Buy a test phone number. Create an outbound voice
profile and a credential-authenticated FQDN connection. Use `+E.164` number
format. Create the LiveKit outbound trunk with `sip.telnyx.com`, the Telnyx
username and password, and the purchased number. Save the returned trunk ID as
`LIVEKIT_SIP_OUTBOUND_TRUNK_ID`.

Telnyx must receive the username on the first SIP request. Follow the current
LiveKit Telnyx guide for the required `X-Telnyx-Username` trunk attribute.

Official guides:

- <https://docs.livekit.io/telephony/start/providers/telnyx/>
- <https://docs.livekit.io/telephony/making-calls/outbound-trunk/>
- <https://docs.livekit.io/telephony/features/transfers/cold/>

Test transfer before the presentation. A successful call does not prove that
SIP `REFER` is enabled. Use a synthetic red-flag answer and confirm that the
responder phone rings.

### Speech and conversation

The demo worker needs an Arabic-capable speech-to-text provider, the configured
language model, and ElevenLabs:

- `OPENAI_API_KEY`
- `OPENAI_STT_MODEL`
- `OPENAI_CLASSIFIER_MODEL`
- `OPENAI_LLM_MODEL`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- the speech-to-text values listed in `apps/agent/.env.example`

The agent can ask only the approved questions from Hawlak. It cannot invent a
clinical instruction. It transfers the call when it detects an approved red
flag, uncertainty, or a transfer request.

## Live flow

1. The hospital user uploads one synthetic discharge PDF.
2. The insurer user edits and approves the exact patient content.
3. Hawlak renders the approved voice note.
4. Hawlak uploads the approved media to Meta and sends it on WhatsApp.
5. Hawlak starts the scheduled LiveKit call through Telnyx.
6. The call agent fetches the approved call plan by case ID.
7. The patient speaks. The agent records only the constrained outcome.
8. A red flag, uncertainty, or request starts the transfer.
9. The caregiver view shows status and the action needed. It does not show the
   full discharge record.

## Rehearsal gates

- Use a synthetic patient and fictional medicine.
- Confirm the permanent Meta token is active.
- Send `START` from the synthetic recipient before dispatching the first voice note.
- Confirm the Meta callback challenge and signed inbound webhook.
- Confirm the utility template is approved for the rehearsal sender.
- Confirm WhatsApp `sent`, `delivered`, and `read` callbacks.
- Confirm that the call uses the test number entered in the case.
- Confirm Arabic speech recognition with the chosen dialect.
- Confirm the normal path, the uncertain path, and the transfer path.
- Confirm that logs show only the last four phone digits.
- Keep a mock-mode screen recording as the presentation fallback.

## Saudi production replacement

Do not present the external demo stack as the production architecture. The
Saudi production profile replaces the external speech and call services with
Saudi-hosted model inference and a contracted local carrier such as stc or
Zain. The clinical workflow, approval checksum, provider interfaces, and user
experience stay the same. Legal, privacy, security, and carrier teams must
approve the production data flow before any real patient pilot.
