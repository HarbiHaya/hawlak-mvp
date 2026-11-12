# Hawlak dashboard

Bilingual React/Vite workspace for the synthetic Hawlak proof of concept. One
application exposes only the tools allowed for each role. Provider, database and
storage credentials never reach the browser.

## Run

From the repository root:

```bash
npm install
npm run dev -w apps/dashboard
```

Open <http://localhost:5173> and sign in with a demo role account (`admin`,
`hospital`, `insurer` or `caregiver`) and `DEMO_LOGIN_PASSWORD` from `.env`.

## Role workspaces

### Hospital

The discharge user enters the registered patient name and test number, chooses
language and dialect, and uploads the discharge PDF. The hospital does not edit
insurer service eligibility or approve generated patient content.

### Insurer

The integrated-care reviewer sees a compact case queue. They can verify the
extracted discharge instructions, edit the exact voice-note and call text,
approve medication images, choose the follow-up schedule, decide whether the
member receives Hawlak, and approve the journey. Dispatch remains disabled until
the required content is approved.

### Caregiver

The caregiver sees adherence state, the next action, and open escalation status.
They do not see the full discharge document, insurer fields, or internal notes.
The current proof of concept is web-based; a caregiver app can reuse this API
later.

### Patient channels

The patient does not use this dashboard. Hawlak sends the minimized approved
voice note and approved medication image through Meta WhatsApp, with only `1`
and `2` response buttons. Scheduled follow-up uses the telephone channel.

## Verification

```bash
npm run typecheck -w apps/dashboard
npm test -w apps/dashboard
npm run build -w apps/dashboard
```

The UI is responsive down to 390 px, supports Arabic RTL and English LTR,
respects reduced-motion preferences, and exposes visible keyboard focus.
