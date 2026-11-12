import {
  PharmacistReviewRequestedSchema,
  type PharmacistReviewRequested,
} from "@hawlak/contracts";

import { issuesToText, type Outcome, type ReviewPage } from "./schemas";

export interface RecordedReview {
  outcomeId: string;
  outcome: Outcome;
  reviewerId: string;
  note: string | null;
  recordedAt: string;
  /** true when recorded locally in offline fixture mode. */
  simulated: boolean;
}

export interface ReviewTask {
  event: PharmacistReviewRequested;
  firstSeenAt: string;
  review: RecordedReview | null;
}

export interface InvalidItem {
  key: string;
  eventId: string | null;
  issues: string[];
  receivedAt: string;
}

export interface QueueState {
  tasks: Record<string, ReviewTask>;
  cursor: string | null;
  invalid: InvalidItem[];
  lastSyncAt: string | null;
}

export const initialQueueState: QueueState = {
  tasks: {},
  cursor: null,
  invalid: [],
  lastSyncAt: null,
};

const MAX_INVALID = 20;

function invalidKey(item: unknown): { key: string; eventId: string | null } {
  if (item && typeof item === "object" && typeof (item as { eventId?: unknown }).eventId === "string") {
    const eventId = (item as { eventId: string }).eventId;
    return { key: `event:${eventId}`, eventId };
  }
  let raw: string;
  try {
    raw = JSON.stringify(item) ?? String(item);
  } catch {
    raw = String(item);
  }
  return { key: `raw:${raw.slice(0, 200)}`, eventId: null };
}

/**
 * Merge one polled page. Every item is validated with the shared contract.
 * Valid events are upserted by eventId (re-fetching never duplicates a task);
 * invalid items are listed for the operator instead of crashing the app.
 */
export function applyPage(state: QueueState, page: ReviewPage, now: string): QueueState {
  const tasks = { ...state.tasks };
  const invalid = new Map(state.invalid.map((item) => [item.key, item]));

  for (const item of page.data) {
    const result = PharmacistReviewRequestedSchema.safeParse(item);
    if (result.success) {
      const event = result.data;
      const existing = tasks[event.eventId];
      tasks[event.eventId] = {
        event,
        firstSeenAt: existing?.firstSeenAt ?? now,
        review: existing?.review ?? null,
      };
      invalid.delete(`event:${event.eventId}`);
    } else {
      const { key, eventId } = invalidKey(item);
      invalid.set(key, { key, eventId, issues: issuesToText(result.error), receivedAt: now });
    }
  }

  return {
    tasks,
    // The cursor is opaque. An empty page may return null when we never had
    // one; keep the last cursor we were given rather than starting over.
    cursor: page.nextCursor ?? state.cursor,
    invalid: Array.from(invalid.values()).slice(-MAX_INVALID),
    lastSyncAt: now,
  };
}

export function recordReview(state: QueueState, eventId: string, review: RecordedReview): QueueState {
  const task = state.tasks[eventId];
  if (!task) return state;
  return { ...state, tasks: { ...state.tasks, [eventId]: { ...task, review } } };
}

/** Pending tasks first, oldest first within each group. */
export function sortedTasks(state: QueueState): ReviewTask[] {
  return Object.values(state.tasks).sort((a, b) => {
    const aDone = a.review ? 1 : 0;
    const bDone = b.review ? 1 : 0;
    if (aDone !== bDone) return aDone - bDone;
    return a.event.occurredAt.localeCompare(b.event.occurredAt);
  });
}

export type QueueAction =
  | { type: "page"; page: ReviewPage; now: string }
  | { type: "review"; eventId: string; review: RecordedReview };

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case "page":
      return applyPage(state, action.page, action.now);
    case "review":
      return recordReview(state, action.eventId, action.review);
  }
}
