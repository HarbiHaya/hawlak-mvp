# Hawlak dashboard

Arabic-first React/Vite operator dashboard for the synthetic Hawlak prototype.
It drives the complete demo without exposing OpenAI, ElevenLabs, Twilio,
PostgreSQL or MinIO credentials to the browser.

## Run

From the repository root:

```bash
npm install
npm run dev -w apps/dashboard
```

Open <http://localhost:5173>. Paste `INTERNAL_API_TOKEN` when prompted. The
token stays only in React memory: it is never written to local storage, a URL,
a cookie or a `VITE_*` build variable.

## Product flows

### Send a voice pack

1. Enter a Twilio Sandbox recipient in E.164 format.
2. Choose Hijazi, Najdi or Southern Saudi.
3. Create a fresh synthetic case and generate the two audio-first scripts.
4. Review both scripts and the clinical-fact check.
5. Explicitly approve the unchanged bundle checksum.
6. Send the session summary and recovery/warning voice notes.

### Review medicine photos

The dashboard polls replay-safely, validates every event with
`@hawlak/contracts`, loads stored photos through the authenticated API and lets
the pharmacist record one of four outcomes. Object URLs are revoked when the
photo leaves the screen.

The review task also includes **Send demo reminder now**. It sends:

1. a Saudi Arabic voice note explaining `١ = أخذتها` and `٢ = لسه`;
2. the same medicine photo the patient sent;
3. two numeric WhatsApp quick replies, while the backend records semantic
   values `taken` and `not_yet`.

### WhatsApp connection

The connection screen distinguishes the shared, Twilio-branded Sandbox from a
registered Hawlak sender. Use `scripts/setup_twilio_sender.sh` for the latter.

## Verification

```bash
npm run typecheck -w apps/dashboard
npm test -w apps/dashboard
npm run build -w apps/dashboard
```

The UI is responsive down to 390 px, uses RTL layout, respects reduced-motion
preferences and exposes visible keyboard focus.
