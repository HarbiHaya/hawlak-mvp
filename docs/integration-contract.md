# Haya ↔ Retaj Integration Contract

## Boundary

Haya's API owns all business logic, provider calls, persistence and webhooks.
Retaj's dashboard owns the operator controls and pharmacist-facing UI. The two
sides communicate only through the authenticated routes below.

## Delivery mechanism for the MVP

All routes in this document are under the local demo's shared bearer-token
boundary. Requests without the configured token return `401 Unauthorized`.

### Review-event polling

The dashboard polls:

```http
GET /internal/review-events?after=<cursor>&limit=20
Authorization: Bearer <internal-dashboard-token>
```

The response is exactly:

```json
{
  "data": [
    {
      "eventId": "evt_01",
      "eventType": "pharmacist_review_requested",
      "eventVersion": 1,
      "idempotencyKey": "case_01:pharmacist_review_requested:v1",
      "occurredAt": "2026-10-25T12:00:00Z",
      "case": {
        "caseId": "case_01",
        "patientAlias": "أبو محمد",
        "phoneE164Masked": "+9665*****123",
        "expectedBoxCount": 3,
        "receivedBoxCount": 3
      },
      "approvedPlan": {
        "planId": "plan_01",
        "version": 1,
        "sourceHash": "sha256:synthetic-fixture-hash"
      },
      "medicinePhotos": [
        {"mediaId": "media_01", "objectKey": "cases/case_01/media/01.jpg"}
      ],
      "reviewReason": "expected_photo_count_reached"
    }
  ],
  "nextCursor": "event-sequence:1"
}
```

Each item in `data` must pass `PharmacistReviewRequestedSchema`. Events are
ordered by a server-owned, monotonically increasing event sequence, oldest
first. The cursor is opaque to the dashboard and points after the final event
returned. `limit` defaults to 20 and must be between 1 and 100; an invalid
limit or cursor returns `400`. An empty page returns `data: []` and preserves
the supplied cursor in `nextCursor` (or returns `null` when no initial cursor
exists). This is simpler than operating a message broker during the hackathon.

### Dialect selector

Before creating a synthetic demo case, the dashboard fetches:

```http
GET /internal/voice-options
Authorization: Bearer <internal-dashboard-token>
```

The `dialects` array is the source of truth for the selector. Its `code` is sent
unchanged as `case.dialectCode` in `POST /internal/cases`. The initial supported
codes are `ar-SA-hijazi`, `ar-SA-najdi`, and `ar-SA-janoubi`. The response also
shows the server-configured voice label, model and language so the operator can
confirm that a native Saudi Arabic voice—not an English premade voice—is active.

### Audio-first script review and approval

The operator screen uses this sequence:

1. `POST /internal/cases` with the synthetic approved-plan document, demo
   recipient and selected `case.dialectCode`.
2. `POST /internal/cases/{caseId}/generate-audio-first` to receive two scripts,
   their artifact IDs, individual checksums, the bundle `approvalChecksum` and
   the fact report.
3. Display both scripts completely. Do not edit them in the browser.
4. After explicit approval, call
   `POST /internal/cases/{caseId}/approve-audio-first-and-send` with:

```json
{
  "sessionArtifactId": "<session-summary artifact ID>",
  "recoveryArtifactId": "<recovery-warning artifact ID>",
  "approvalChecksum": "<unchanged bundle checksum>",
  "approvedBy": "demo-operator-01"
}
```

The approval request also requires a new `Idempotency-Key` header. The backend
rejects a changed checksum and sends exactly two audio notes. The first note
contains the spoken disclosure, medicine summary and photo request; the second
contains recovery guidance and warning signs. The dashboard must never approve
automatically.

### Audio-guided numeric reminder

After at least one stored patient photo exists, the operator can run:

```http
POST /internal/cases/{caseId}/send-photo-reminder
Authorization: Bearer <internal-dashboard-token>
Content-Type: application/json
Idempotency-Key: <unique-reminder-action-id>

{
  "mediaId": "<stored inbound media ID>",
  "reminderId": "<unique occurrence ID>"
}
```

The backend first sends a Saudi Arabic voice instruction explaining that `١`
means taken and `٢` means not yet. It then sends the same stored photo with two
numeric quick replies. Visible titles stay numeric while hidden button payloads
remain `taken` and `not_yet` for the audit trail.

### Authenticated medicine photos

The dashboard fetches each photo by its contract `mediaId`:

```http
GET /internal/media/{mediaId}
Authorization: Bearer <internal-dashboard-token>
```

A successful response contains the stored image bytes and their recorded
`Content-Type`. Missing or inaccessible media returns `404` without revealing
the MinIO object key. MinIO credentials are never sent to the browser, and the
route never accepts a client-supplied bucket name or object key.

### Pharmacist outcomes

The dashboard records one review decision with an idempotency key generated
for that user action:

```http
POST /internal/review-events/{eventId}/outcomes
Authorization: Bearer <internal-dashboard-token>
Content-Type: application/json
Idempotency-Key: <unique-review-action-id>

{
  "eventVersion": 1,
  "outcome": "matched",
  "reviewerId": "demo-pharmacist-01",
  "note": null
}
```

`outcome` is one of `matched`, `mismatch_found`, `unclear_photo`, or
`contact_patient`. `reviewerId` is required and `note` is optional. The first
accepted request returns `201` with:

```json
{
  "data": {
    "outcomeId": "outcome_01",
    "eventId": "evt_01",
    "eventVersion": 1,
    "outcome": "matched",
    "reviewerId": "demo-pharmacist-01",
    "note": null,
    "recordedAt": "2026-11-04T12:00:00Z"
  }
}
```

Repeating the same `Idempotency-Key` with the same body is replay-safe and
returns the existing outcome. Reusing the key with a different body, or
submitting against a superseded event version, returns `409 Conflict`.

## Browser boundary for the local demo

The FastAPI application accepts browser requests only from the exact
`DASHBOARD_ORIGIN` value, which must be `http://localhost:<port>`. The shared
demo token is entered at runtime, kept only in memory, and sent in the
`Authorization` header. It must never be committed, stored in browser local
storage, or bundled in a `VITE_*` variable. This token and CORS policy are for
the local synthetic demo only; production requires real user sessions and
authorization.

## Idempotency

- `eventId` identifies one event record.
- `idempotencyKey` is unique for the case and event version.
- The dashboard stores the last cursor and upserts by `eventId`.
- Re-fetching the same page must not duplicate a review task.

## Ownership rules

- Haya can add optional fields without breaking the dashboard.
- Removing, renaming, or changing the meaning of a field requires `eventVersion: 2`.
- Retaj never reads Haya’s database directly.
- Haya never writes directly into Retaj’s dashboard database.
- Medicine interpretation belongs to the pharmacist workflow, not the ingestion service.

## First acceptance test

Given one case with three stored medicine photos, the API returns one valid version-1 event. Importing it twice creates one dashboard task containing three photo references.

