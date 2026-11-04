import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { PharmacistReviewRequestedSchema } from "../src/review-event.js";

const fixture = JSON.parse(
  readFileSync(
    new URL("../../../fixtures/expected-review-event.abu-mohammed.json", import.meta.url),
    "utf8",
  ),
);

describe("PharmacistReviewRequestedSchema", () => {
  it("accepts the shared synthetic fixture", () => {
    expect(PharmacistReviewRequestedSchema.parse(fixture)).toEqual(fixture);
  });

  it("rejects a changed event version", () => {
    expect(() =>
      PharmacistReviewRequestedSchema.parse({ ...fixture, eventVersion: 2 }),
    ).toThrow();
  });

  it("rejects invalid received counts", () => {
    expect(() =>
      PharmacistReviewRequestedSchema.parse({
        ...fixture,
        case: { ...fixture.case, receivedBoxCount: -1 },
      }),
    ).toThrow();
  });
});
