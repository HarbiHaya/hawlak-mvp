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
