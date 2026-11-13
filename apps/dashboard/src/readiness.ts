import type { WorkspaceCaseDetail } from "./api";

/**
 * Client-side mirror of the approval rules in
 * apps/api/app/services/care_journey_service.py (approve + _first_incomplete_section).
 * It lets reviewers see what blocks approval before they press the button.
 * The API stays authoritative: the identifier scan, for example, runs only on the server.
 */
export type ReadinessArea = "coverage" | "medications" | "content";

export type BlockerCode =
  | "eligibility_not_verified"
  | "member_not_eligible"
  | "medications_required"
  | "medication_details_required"
  | "reminder_script_required"
  | "medication_image_requires_review"
  | "voice_script_required"
  | "call_plan_incomplete"
  | "call_time_in_past"
  | "no_channel_enabled";

export interface Readiness {
  /** First blocker in the same order the API checks them, or null when ready. */
  blocker: BlockerCode | null;
  blockerArea: ReadinessArea | null;
  areas: Record<ReadinessArea, BlockerCode | null>;
}

const areaOf: Record<BlockerCode, ReadinessArea> = {
  eligibility_not_verified: "coverage",
  member_not_eligible: "coverage",
  medications_required: "medications",
  medication_details_required: "medications",
  reminder_script_required: "medications",
  medication_image_requires_review: "medications",
  voice_script_required: "content",
  call_plan_incomplete: "content",
  call_time_in_past: "content",
  no_channel_enabled: "content",
};

type Content = Pick<WorkspaceCaseDetail, "insurance" | "medications" | "dischargeVoiceNote" | "callPlan">;

function coverageBlocker(detail: Content): BlockerCode | null {
  if (!detail.insurance?.status) return "eligibility_not_verified";
  if (detail.insurance.status !== "eligible") return "member_not_eligible";
  return null;
}

function medicationBlocker(detail: Content): BlockerCode | null {
  if (detail.medications.length === 0) return "medications_required";
  for (const medication of detail.medications) {
    if (!medication.displayName.trim() || !medication.doseInstruction.trim()) return "medication_details_required";
    if (medication.dispensed && medication.reminderEnabled) {
      if (!medication.reminderScript.trim()) return "reminder_script_required";
      if (medication.image?.reviewStatus !== "approved") return "medication_image_requires_review";
    }
  }
  return null;
}

function contentBlocker(detail: Content, now: Date): BlockerCode | null {
  const voice = detail.dischargeVoiceNote;
  const call = detail.callPlan;
  if (voice.enabled && !voice.script.trim()) return "voice_script_required";
  if (call.enabled) {
    const texts = [call.openingScript, call.completionScript, call.transferScript, call.transferTarget];
    if (!texts.every((text) => text.trim()) || call.questions.length === 0 || !call.questions.every((question) => question.prompt.trim()) || !call.responderPhoneE164) {
      return "call_plan_incomplete";
    }
    if (call.firstCallAt && new Date(call.firstCallAt).getTime() < now.getTime()) return "call_time_in_past";
  }
  const reminders = detail.medications.some((medication) => medication.dispensed && medication.reminderEnabled);
  if (!voice.enabled && !call.enabled && !reminders) return "no_channel_enabled";
  return null;
}

export function readiness(detail: Content, now: Date = new Date()): Readiness {
  const areas = {
    coverage: coverageBlocker(detail),
    medications: medicationBlocker(detail),
    content: contentBlocker(detail, now),
  };
  // Server order: coverage, then medications, then voice/call/channel checks.
  const blocker = areas.coverage ?? areas.medications ?? areas.content;
  return { blocker, blockerArea: blocker ? areaOf[blocker] : null, areas };
}

export interface DispatchSummary {
  voiceNote: boolean;
  reminders: number;
  calls: Date[];
  /** Medications marked not dispensed: approval raises a medication-access alert for each. */
  notDispensed: string[];
}

const repeatDays = { none: 0, daily: 1, every_2_days: 2, weekly: 7 } as const;

/** What approval will schedule, mirroring CareJourneyService.approve and _call_times. */
export function dispatchSummary(detail: Content, approvedAt: Date = new Date()): DispatchSummary {
  const call = detail.callPlan;
  const repeat = call.repeat ?? "none";
  const count = repeat === "none" ? 1 : call.occurrences ?? 1;
  const first = call.firstCallAt ? new Date(call.firstCallAt) : new Date(approvedAt.getTime() + call.scheduledAfterHours * 3_600_000);
  return {
    voiceNote: detail.dischargeVoiceNote.enabled,
    reminders: detail.medications.filter((medication) => medication.dispensed && medication.reminderEnabled).length,
    calls: call.enabled ? Array.from({ length: count }, (_, index) => new Date(first.getTime() + index * repeatDays[repeat] * 86_400_000)) : [],
    notDispensed: detail.medications.filter((medication) => !medication.dispensed).map((medication) => medication.displayName),
  };
}
