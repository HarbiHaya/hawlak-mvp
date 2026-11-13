import { describe, expect, it } from "vitest";

import type { WorkspaceCaseDetail } from "./api";
import { dispatchSummary, readiness } from "./readiness";

type Content = Pick<WorkspaceCaseDetail, "insurance" | "medications" | "dischargeVoiceNote" | "callPlan">;

function readyCase(): Content {
  return {
    insurance: { memberId: "SYN-4471203", status: "eligible" },
    dischargeVoiceNote: { enabled: true, script: "نص الرسالة" },
    medications: [{
      medicationId: "SYN-MED-1", displayName: "سينثوميد", doseInstruction: "٥ ملغ", dispensed: true,
      image: { source: "catalog", objectKey: "cases/c/1.png", reviewStatus: "approved" }, reminderEnabled: true, reminderScript: "حان وقت الدواء",
    }],
    callPlan: {
      enabled: true, scheduledAfterHours: 24, firstCallAt: null, repeat: "none", occurrences: 1,
      openingScript: "مرحباً", questions: [{ id: "q-1", prompt: "كيف حالك؟" }], completionScript: "شكراً",
      transferScript: "سنحولك", transferTarget: "الفريق", responderPhoneE164: "+99900000001",
    },
  };
}

describe("approval readiness mirrors the API approval order", () => {
  it("is ready when every section is complete", () => {
    expect(readiness(readyCase())).toEqual({ blocker: null, blockerArea: null, areas: { coverage: null, medications: null, content: null } });
  });

  it("reports eligibility before any content problem", () => {
    const detail = { ...readyCase(), insurance: null, medications: [] };
    const result = readiness(detail);
    expect(result.blocker).toBe("eligibility_not_verified");
    expect(result.areas.medications).toBe("medications_required");
  });

  it("blocks members who are not eligible", () => {
    expect(readiness({ ...readyCase(), insurance: { memberId: "SYN-9", status: "not_eligible" } }).blocker).toBe("member_not_eligible");
  });

  it("does not require a medicine photo before approval", () => {
    const noPhoto = readyCase();
    noPhoto.medications[0].image = null;
    expect(readiness(noPhoto).blocker).toBe(null);
  });

  it("flags an incomplete call plan and a first call in the past", () => {
    const incomplete = readyCase();
    incomplete.callPlan.questions = [{ id: "q-1", prompt: " " }];
    expect(readiness(incomplete).blocker).toBe("call_plan_incomplete");

    const past = readyCase();
    past.callPlan.firstCallAt = "2026-01-01T08:00:00Z";
    expect(readiness(past, new Date("2026-11-13T08:00:00Z")).blocker).toBe("call_time_in_past");
  });

  it("requires at least one channel", () => {
    const silent = readyCase();
    silent.dischargeVoiceNote.enabled = false;
    silent.callPlan.enabled = false;
    silent.medications[0].reminderEnabled = false;
    expect(readiness(silent).blocker).toBe("no_channel_enabled");
  });
});

describe("dispatch summary mirrors scheduled delivery runs", () => {
  it("counts reminders and expands repeating calls", () => {
    const detail = readyCase();
    detail.callPlan = { ...detail.callPlan, firstCallAt: "2026-11-20T07:00:00.000Z", repeat: "every_2_days", occurrences: 3 };
    detail.medications.push({ ...detail.medications[0], medicationId: "SYN-MED-2", dispensed: false, reminderEnabled: false, displayName: "كارديوفكس" });
    const summary = dispatchSummary(detail);
    expect(summary.voiceNote).toBe(true);
    expect(summary.reminders).toBe(1);
    expect(summary.photoRequest).toBe(true);
    expect(summary.calls.map((date) => date.toISOString())).toEqual(["2026-11-20T07:00:00.000Z", "2026-11-22T07:00:00.000Z", "2026-11-24T07:00:00.000Z"]);
    expect(summary.notDispensed).toEqual(["كارديوفكس"]);
  });

  it("schedules relative calls from the approval time", () => {
    const summary = dispatchSummary(readyCase(), new Date("2026-11-13T10:00:00.000Z"));
    expect(summary.calls.map((date) => date.toISOString())).toEqual(["2026-11-14T10:00:00.000Z"]);
  });
});
