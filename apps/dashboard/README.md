# Hawlak dashboard handoff

Owner: Retaj. Build a React + TypeScript dashboard with Vite on
`http://localhost:5173`.

The dashboard is an operator and pharmacist interface. It calls Hawlak's API;
it must not call OpenAI, ElevenLabs, WhatsApp, PostgreSQL or MinIO directly.

## Start the app

From the repository root:

```bash
npm create vite@latest apps/dashboard -- --template react-ts
npm install
npm install -w apps/dashboard @hawlak/contracts
npm run dev -w apps/dashboard
```

Keep this handoff when Vite asks about replacing the non-empty directory.

## Authentication

Ask the operator for the local demo bearer token at runtime. Keep it only in
React memory and send it as:

```http
Authorization: Bearer <token>
```

Never store it in `localStorage`, commit it, or expose it through a `VITE_*`
environment variable.

## Required screens

### 1. Synthetic demo setup

1. Fetch `GET /internal/voice-options`.
2. Render its dialects as a selector: Hijazi, Najdi and Southern Saudi.
3. Create the synthetic case through `POST /internal/cases`, using the selected
   `code` as `case.dialectCode`.
4. Call `POST /internal/cases/{caseId}/generate-script`.
5. Show the complete Arabic script and fact-check status for human review.
6. Send the returned artifact ID and unchanged checksum to
   `POST /internal/cases/{caseId}/approve-and-send` with a fresh
   `Idempotency-Key` only after explicit operator approval.

Never make the approval automatic. A changed script must be regenerated and
approved with its new checksum.

### 2. Pharmacist review queue

1. Poll `GET /internal/review-events?after=<cursor>&limit=20`.
2. Validate every item with `PharmacistReviewRequestedSchema` from
   `@hawlak/contracts`.
3. Upsert by `eventId` and retain the returned opaque cursor.
4. Show patient alias, masked phone, approved plan version, received/expected
   photo count and audit time.
5. Fetch each photo from `GET /internal/media/{mediaId}` with the same bearer
   token. Create object URLs in memory and revoke them when no longer used.
6. Submit `matched`, `mismatch_found`, `unclear_photo`, or `contact_patient` to
   `POST /internal/review-events/{eventId}/outcomes` with a per-click
   `Idempotency-Key`.

The pharmacist decides whether a photo matches the plan. The dashboard and
backend must not use AI to interpret medicine photos.

## Work without the backend

Use `fixtures/expected-review-event.abu-mohammed.json` as the initial queue item
and validate it with the shared Zod schema. This allows the UI to be implemented
without provider keys or local infrastructure.

Exact request and response shapes are in
[`docs/integration-contract.md`](../../docs/integration-contract.md). When the
API is running, use `http://127.0.0.1:3000/docs` to inspect its OpenAPI schema.

## Design

Colors, type, spacing and screen references are in
[`docs/design-system/`](../../docs/design-system/README.md). Reuse the tokens;
don't copy the reference HTML into the app.

## Definition of done

- Responsive Arabic-first UI with correct RTL layout, using the design-system tokens.
- Token remains memory-only.
- Contract validation errors are visible and do not crash the app.
- Polling is replay-safe and does not duplicate cases.
- Photo object URLs are cleaned up.
- Outcome buttons prevent accidental double submission.
- Loading, empty, error and success states are implemented.
- `npm run typecheck`, `npm test` and `npm run build` pass from the repository
  root.

---

## Implementation notes (Retaj)

### First run

```bash
npm install            # from the repo root; commit the updated package-lock.json
npm run dev -w apps/dashboard
```

Open `http://localhost:5173`, enter the API address (`http://localhost:3000`)
and the `INTERNAL_API_TOKEN` from Haya's `.env`. Or choose **العمل بدون خادم**
to load `fixtures/expected-review-event.abu-mohammed.json` with no backend.

`@hawlak/contracts` and `fixtures/` are resolved from source through aliases in
`vite.config.ts` and `tsconfig.json`, so `typecheck`, `test` and `build` do not
need the contracts package to be built first.

### Behaviour worth knowing

- **One case per dialect.** The API returns `409 case_conflict` if an existing
  case is re-sent with a different dialect, so the dashboard creates
  `case_01-hijazi`, `case_01-najdi`, `case_01-janoubi` (and matching plan ids).
  Re-creating the same dialect with the same number is replay-safe.
- **Approval** needs a ticked acknowledgement, sends the generated checksum
  unchanged and a new `Idempotency-Key` per click. A new script remounts the
  approval step.
- **Polling** runs every 5 s, one request at a time, follows `nextCursor`, keeps
  the last cursor when an empty page returns `null`, and upserts by `eventId`.
  It stops after a `401` until **تحديث الآن** is pressed.
- **Contract errors** are listed in an amber panel; valid events still show.
- **Outcomes** are chosen, then confirmed. Double clicks send one request.
  Retrying the identical decision after a failure reuses its key; any change
  gets a new key. After success the decision is locked.
- **Photos** are fetched with the bearer token into object URLs that are revoked
  when the photo changes or the view unmounts. Nothing interprets them.

### Files

| Path | What it does |
|---|---|
| `src/lib/api.ts` | The only code that calls the API |
| `src/lib/schemas.ts` | Zod shapes for the non-event routes |
| `src/lib/queue.ts` | Contract validation + replay-safe upsert |
| `src/hooks/useReviewQueue.ts` | Polling loop |
| `src/components/SetupScreen.tsx`, `ApprovalStep.tsx` | Screen 1 |
| `src/components/ReviewScreen.tsx`, `MedicinePhoto.tsx`, `OutcomePanel.tsx` | Screen 2 |
| `src/styles.css` | Design-system tokens, RTL via logical properties |
