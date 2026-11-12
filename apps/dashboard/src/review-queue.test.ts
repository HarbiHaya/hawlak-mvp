import { describe, expect, it } from "vitest";

import fixture from "../../../fixtures/expected-review-event.abu-mohammed.json";
import { mergeReviewEvents } from "./review-queue";

describe("mergeReviewEvents", () => {
  it("keeps one pharmacist task when polling replays the same event", () => {
    const first = mergeReviewEvents([], [fixture]);
    const replay = mergeReviewEvents(first, [fixture]);

    expect(replay).toHaveLength(1);
    expect(replay[0]?.eventId).toBe("evt_01");
  });
});
