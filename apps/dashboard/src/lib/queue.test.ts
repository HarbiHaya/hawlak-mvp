import { describe, expect, it } from "vitest";

import { DEMO_REVIEW_EVENT } from "./demoCase";
import { applyPage, initialQueueState, recordReview, sortedTasks, type RecordedReview } from "./queue";

const NOW = "2026-11-08T10:00:00.000Z";
const LATER = "2026-11-08T10:00:05.000Z";
const fixture = DEMO_REVIEW_EVENT as Record<string, unknown> & { case: Record<string, unknown> };

const review: RecordedReview = {
  outcomeId: "outcome_01",
  outcome: "matched",
  reviewerId: "demo-pharmacist-01",
  note: null,
  recordedAt: NOW,
  simulated: false,
};

describe("applyPage", () => {
  it("accepts the shared fixture as one task with three photo references", () => {
    const state = applyPage(initialQueueState, { data: [fixture], nextCursor: "event-sequence:1" }, NOW);
    const tasks = Object.values(state.tasks);
    expect(tasks).toHaveLength(1);
    expect(tasks[0].event.eventId).toBe("evt_01");
    expect(tasks[0].event.medicinePhotos).toHaveLength(3);
    expect(state.invalid).toHaveLength(0);
  });

  it("importing the same event twice creates one task (first acceptance test)", () => {
    const once = applyPage(initialQueueState, { data: [fixture], nextCursor: "event-sequence:1" }, NOW);
    const twice = applyPage(once, { data: [fixture], nextCursor: "event-sequence:1" }, LATER);
    expect(Object.keys(twice.tasks)).toEqual(["evt_01"]);
    expect(twice.tasks.evt_01.event.medicinePhotos).toHaveLength(3);
    expect(twice.tasks.evt_01.firstSeenAt).toBe(NOW);
  });

  it("keeps the opaque cursor when an empty page returns null", () => {
    const first = applyPage(initialQueueState, { data: [fixture], nextCursor: "event-sequence:1" }, NOW);
    expect(first.cursor).toBe("event-sequence:1");
    const empty = applyPage(first, { data: [], nextCursor: null }, LATER);
    expect(empty.cursor).toBe("event-sequence:1");
    const moved = applyPage(empty, { data: [], nextCursor: "event-sequence:7" }, LATER);
    expect(moved.cursor).toBe("event-sequence:7");
  });

  it("lists contract violations without dropping valid events or throwing", () => {
    const broken = { ...fixture, eventId: "evt_bad", eventVersion: 2 };
    const negative = { ...fixture, eventId: "evt_neg", case: { ...fixture.case, receivedBoxCount: -1 } };
    const state = applyPage(initialQueueState, { data: [fixture, broken, negative, "nonsense"], nextCursor: null }, NOW);
    expect(Object.keys(state.tasks)).toEqual(["evt_01"]);
    expect(state.invalid).toHaveLength(3);
    expect(state.invalid.map((i) => i.eventId)).toContain("evt_bad");
    expect(state.invalid[0].issues.length).toBeGreaterThan(0);
  });

  it("does not repeat the same invalid item on every poll", () => {
    const broken = { ...fixture, eventId: "evt_bad", eventVersion: 2 };
    const once = applyPage(initialQueueState, { data: [broken], nextCursor: null }, NOW);
    const twice = applyPage(once, { data: [broken], nextCursor: null }, LATER);
    expect(twice.invalid).toHaveLength(1);
  });

  it("keeps a recorded decision when the event is fetched again", () => {
    const first = applyPage(initialQueueState, { data: [fixture], nextCursor: null }, NOW);
    const reviewed = recordReview(first, "evt_01", review);
    const again = applyPage(reviewed, { data: [fixture], nextCursor: null }, LATER);
    expect(again.tasks.evt_01.review).toEqual(review);
  });
});

describe("sortedTasks", () => {
  it("puts pending tasks first, oldest first", () => {
    const older = { ...fixture, eventId: "evt_old", occurredAt: "2026-10-25T09:00:00Z" };
    const newer = { ...fixture, eventId: "evt_new", occurredAt: "2026-10-25T15:00:00Z" };
    let state = applyPage(initialQueueState, { data: [newer, older, fixture], nextCursor: null }, NOW);
    state = recordReview(state, "evt_old", review);
    expect(sortedTasks(state).map((t) => t.event.eventId)).toEqual(["evt_01", "evt_new", "evt_old"]);
  });

  it("ignores reviews for unknown events", () => {
    expect(recordReview(initialQueueState, "missing", review)).toBe(initialQueueState);
  });
});
