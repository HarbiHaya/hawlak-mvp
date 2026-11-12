import plan from "@fixtures/approved-plan.abu-mohammed.json";
import reviewEvent from "@fixtures/expected-review-event.abu-mohammed.json";

/** Synthetic, fictional plan. Never replace with real patient data. */
export const DEMO_PLAN = plan;
export type DemoPlan = typeof plan;

/** Offline queue seed, validated by the queue like any polled item. */
export const DEMO_REVIEW_EVENT: unknown = reviewEvent;

export const DEMO_RECIPIENT_PLACEHOLDER = "+966500000000";
export const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;

/** "ar-SA-najdi" -> "najdi" */
export function dialectSuffix(code: string): string {
  const last = code.split("-").pop() ?? code;
  return last.replace(/[^A-Za-z0-9_-]/g, "").toLowerCase() || "dialect";
}

/**
 * Body for POST /internal/cases.
 *
 * The API returns 409 when an existing case is re-sent with another dialect,
 * so each dialect gets its own synthetic case and plan id (case_01-najdi …).
 * Re-sending the same dialect and number is replay-safe. Clinical facts are
 * copied unchanged from the approved fixture.
 */
export function buildCaseRequest(dialectCode: string, demoRecipient: string, source: DemoPlan = plan) {
  const suffix = dialectSuffix(dialectCode);
  return {
    ...source,
    case: { ...source.case, caseId: `${source.case.caseId}-${suffix}`, dialectCode },
    approvedPlan: { ...source.approvedPlan, planId: `${source.approvedPlan.planId}-${suffix}` },
    demoRecipient,
  };
}

/** Last four digits only, for display. */
export function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  return digits.length <= 4 ? phone : `+${"•".repeat(Math.max(digits.length - 4, 0))}${digits.slice(-4)}`;
}
