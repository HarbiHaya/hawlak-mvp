# Haya ↔ Retaj Integration Contract

## Boundary

Haya’s API owns everything up to creation of `pharmacist_review_requested`. Retaj’s dashboard owns everything from displaying that event onward.

## Delivery mechanism for the MVP

Start with an authenticated polling endpoint:

```http
GET /internal/review-events?after=<cursor>&limit=20
Authorization: Bearer <internal-dashboard-token>
```

The API returns an array of objects that pass `PharmacistReviewRequestedSchema` and a new cursor. This is simpler than operating a message broker during the hackathon.

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

