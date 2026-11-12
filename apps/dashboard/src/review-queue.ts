import {
  PharmacistReviewRequestedSchema,
  type PharmacistReviewRequested,
} from "@hawlak/contracts";

export function mergeReviewEvents(
  current: PharmacistReviewRequested[],
  incoming: unknown[],
): PharmacistReviewRequested[] {
  const byId = new Map(current.map((event) => [event.eventId, event]));
  for (const item of incoming) {
    const event = PharmacistReviewRequestedSchema.parse(item);
    byId.set(event.eventId, event);
  }
  return [...byId.values()].sort((left, right) =>
    left.occurredAt.localeCompare(right.occurredAt),
  );
}
