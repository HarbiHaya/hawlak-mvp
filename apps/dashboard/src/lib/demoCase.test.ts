import { PharmacistReviewRequestedSchema } from "@hawlak/contracts";
import { describe, expect, it } from "vitest";

import { DEMO_PLAN, DEMO_REVIEW_EVENT, PHONE_PATTERN, buildCaseRequest, dialectSuffix } from "./demoCase";
import { newIdempotencyKey } from "./idempotency";

describe("buildCaseRequest", () => {
  it("uses the selected dialect code unchanged and copies clinical facts exactly", () => {
    const body = buildCaseRequest("ar-SA-hijazi", "+966500000000");
    expect(body.case.dialectCode).toBe("ar-SA-hijazi");
    expect(body.demoRecipient).toBe("+966500000000");
    expect(body.synthetic).toBe(true);
    expect(body.approvedPlan.clinicalFacts).toEqual(DEMO_PLAN.approvedPlan.clinicalFacts);
    expect(body.approvedPlan.source).toEqual(DEMO_PLAN.approvedPlan.source);
  });

  it("gives each dialect its own replay-safe case and plan id", () => {
    const najdi = buildCaseRequest("ar-SA-najdi", "+966500000000");
    const janoubi = buildCaseRequest("ar-SA-janoubi", "+966500000000");
    expect(najdi.case.caseId).toBe("case_01-najdi");
    expect(najdi.approvedPlan.planId).toBe("plan_01-najdi");
    expect(janoubi.case.caseId).toBe("case_01-janoubi");
    expect(buildCaseRequest("ar-SA-najdi", "+966500000000")).toEqual(najdi);
    // The API only allows letters, digits, "_" and "-" in ids.
    expect(najdi.case.caseId).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("does not modify the shared fixture", () => {
    buildCaseRequest("ar-SA-hijazi", "+966500000000");
    expect(DEMO_PLAN.case.caseId).toBe("case_01");
    expect(DEMO_PLAN.case.dialectCode).toBe("ar-SA-najdi");
  });

  it("derives a clean suffix", () => {
    expect(dialectSuffix("ar-SA-najdi")).toBe("najdi");
    expect(dialectSuffix("weird code!")).toBe("weirdcode");
  });

  it("accepts only E.164 demo numbers", () => {
    expect(PHONE_PATTERN.test("+966500000000")).toBe(true);
    expect(PHONE_PATTERN.test("0500000000")).toBe(false);
    expect(PHONE_PATTERN.test("+96650000000000000")).toBe(false);
  });
});

describe("fixtures", () => {
  it("the offline review event passes the shared contract", () => {
    expect(PharmacistReviewRequestedSchema.safeParse(DEMO_REVIEW_EVENT).success).toBe(true);
  });
});

describe("newIdempotencyKey", () => {
  it("returns a fresh prefixed key every time", () => {
    const keys = new Set(Array.from({ length: 50 }, () => newIdempotencyKey("review")));
    expect(keys.size).toBe(50);
    for (const key of keys) expect(key.startsWith("review-")).toBe(true);
  });
});
