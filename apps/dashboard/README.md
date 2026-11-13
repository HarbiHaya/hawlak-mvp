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

### Administration

The overview shows live counts (cases awaiting review, approved plans, open
alerts) and the items that need action, all from the API. Navigation groups each
role's workspace.

### Hospital

The discharge user enters the registered patient name, mobile number and member
ID, chooses language and dialect, and drops or selects the discharge PDF. Fields
validate inline. The confirmation shows the case reference with a copy button.
The hospital does not edit eligibility or approve patient content.

### Insurer

The integrated-care reviewer works from a queue filtered to cases awaiting
review. Opening a case lands on the first section that blocks approval. The
readiness strip under the header names the blocker in the API's own order
(`src/readiness.ts` mirrors `CareJourneyService.approve`; the server stays
authoritative and alone runs the identifier scan). Tabs show which sections are
complete.

- Edits are tracked. Switching cases saves the draft first; Ctrl/⌘+S saves; the
  browser warns before closing with unsaved changes.
- Approve opens a confirmation that lists what will be scheduled: voice note,
  reminders, calls with the first call time, and alerts for medicines not
  dispensed.
- Medicine images still need an explicit "Approve image" by the reviewer.
- Alerts can be filtered (open/resolved) and each one opens its case.
- `?case=<id>` deep-links to a case.

### Caregiver

The caregiver enters the case reference once; it is kept in the URL and
remembered on that browser. The page shows plan status, the next call, open
alerts and medication reminder status, and refreshes every 30 seconds. Reminder
status is shown only after approval. The caregiver does not see the discharge
document, insurer fields or internal notes.

### Patient channels

The patient does not use this dashboard. Hawlak sends the minimized approved
voice note and approved medication image through Meta WhatsApp, with only `1`
and `2` response buttons. Scheduled follow-up uses the telephone channel.

## Structure

| File | Purpose |
|---|---|
| `src/styles.css` | Design tokens and all component styles |
| `src/ui.tsx` | Shared components: toasts, dialog, tabs, segmented control, field, badge |
| `src/i18n.ts` | Locale type, API error messages, date and number formatting |
| `src/readiness.ts` | Client mirror of the approval rules and dispatch summary |
| `src/insurer/*` | Case queue, case tabs, alerts view and insurer copy |
| `src/events.ts` | App-wide events (alerts changed, session expired) |

`ReviewWorkspace.tsx` is the earlier pharmacist photo-review screen. It is not
routed and is kept for reference.

## Verification

```bash
npm run typecheck -w apps/dashboard
npm test -w apps/dashboard
npm run build -w apps/dashboard
```

The UI is responsive down to 390 px (navigation moves into a drawer below
960 px), supports Arabic RTL and English LTR, respects reduced-motion
preferences, and exposes visible keyboard focus. Tabs follow the WAI-ARIA tabs
pattern, dialogs use the native `<dialog>` element, and route changes move focus
to the page heading.
