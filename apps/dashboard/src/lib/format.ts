import type { PharmacistReviewRequested } from "@hawlak/contracts";

import type { Outcome } from "./schemas";

const dateTime = new Intl.DateTimeFormat("ar-SA-u-nu-latn-ca-gregory", {
  dateStyle: "medium",
  timeStyle: "short",
});
const timeOnly = new Intl.DateTimeFormat("ar-SA-u-nu-latn-ca-gregory", { timeStyle: "short" });

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateTime.format(date);
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : timeOnly.format(date);
}

export function shortHash(hash: string): string {
  return hash.length > 24 ? `${hash.slice(0, 15)}…${hash.slice(-6)}` : hash;
}

export type Tone = "green" | "amber" | "red" | "blue" | "grey";

export const OUTCOME_LABELS: Record<Outcome, { label: string; hint: string; tone: Tone }> = {
  matched: { label: "مطابقة للخطة", hint: "كل العلب تطابق الخطة المعتمدة", tone: "green" },
  mismatch_found: { label: "يوجد اختلاف", hint: "دواء أو تركيز لا يطابق الخطة", tone: "red" },
  unclear_photo: { label: "الصورة غير واضحة", hint: "يلزم تصوير العلبة من جديد", tone: "amber" },
  contact_patient: { label: "التواصل مع المريض", hint: "يحتاج اتصالًا قبل اتخاذ القرار", tone: "blue" },
};

export const REASON_LABELS: Record<PharmacistReviewRequested["reviewReason"], string> = {
  expected_photo_count_reached: "اكتمل عدد الصور المتوقع",
  patient_marked_done: "أنهى المريض الإرسال",
};
