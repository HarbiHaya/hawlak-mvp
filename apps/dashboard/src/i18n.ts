import { HawlakApiError } from "./api";

export type Locale = "ar" | "en";
export type Bilingual = { ar: string; en: string };

const errorMessages: Record<string, Bilingual> = {
  invalid_credentials: { ar: "اسم المستخدم أو كلمة المرور غير صحيحة.", en: "The username or password is incorrect." },
  Forbidden: { ar: "لا يملك هذا الحساب صلاحية الوصول إلى هذه الصفحة.", en: "This account is not authorised to access this page." },
  Unauthorized: { ar: "انتهت صلاحية الجلسة. سجّل الدخول مرة أخرى.", en: "Your session has expired. Sign in again." },
  approved_content_is_immutable: { ar: "لا يمكن تعديل المحتوى بعد اعتماده.", en: "Approved content cannot be modified." },
  already_approved: { ar: "سبق اعتماد هذه الحالة.", en: "This case has already been approved." },
  eligibility_not_verified: { ar: "تحقق من أهلية العضو قبل الاعتماد.", en: "Verify the member's eligibility before approval." },
  member_not_eligible: { ar: "العضو غير مؤهل لبرنامج الرعاية بعد الخروج.", en: "The member is not eligible for the post-discharge care programme." },
  medications_required: { ar: "أضف دواءً واحداً على الأقل.", en: "Add at least one medication." },
  medication_details_required: { ar: "أكمل اسم الدواء والجرعة لجميع الأدوية.", en: "Complete the name and dose for every medication." },
  reminder_script_required: { ar: "أدخل نص التذكير لكل دواء مفعّل له التذكير.", en: "Enter the reminder text for every medication with a reminder." },
  voice_script_required: { ar: "أدخل نص الرسالة الصوتية أو أوقف إرسالها.", en: "Enter the voice message text or turn the voice message off." },
  call_plan_incomplete: { ar: "أكمل نصوص مكالمة المتابعة ورقم فريق الاستجابة، أو أوقف المكالمة.", en: "Complete the follow-up call texts and responder number, or turn the call off." },
  call_time_in_past: { ar: "موعد المكالمة الأولى في الماضي.", en: "The first call is scheduled in the past." },
  patient_text_contains_identifier: { ar: "يحتوي نص موجّه للمريض على بيانات تعريفية (الاسم الكامل أو رقم الجوال أو الهوية أو العضوية أو الوثيقة أو رقم الحالة أو اسم الملف). احذفها قبل الاعتماد.", en: "Patient-facing text contains an identifier (full name, phone, national or Iqama number, member or policy number, case ID or file name). Remove it before approval." },
  no_channel_enabled: { ar: "فعّل قناة واحدة على الأقل: الرسالة الصوتية أو التذكير أو المكالمة.", en: "Enable at least one channel: voice message, reminder or call." },
  document_not_readable: { ar: "تعذّرت قراءة نص ملخص الخروج، لذا لا يمكن إنشاء المسودات تلقائياً.", en: "The discharge summary text could not be read, so drafts cannot be generated." },
  case_not_found: { ar: "لم يُعثر على حالة بهذا الرقم.", en: "No case matches this reference." },
  alert_not_found: { ar: "لم يُعثر على التنبيه.", en: "The alert was not found." },
  file_not_found: { ar: "تعذّر فتح الملف.", en: "The file could not be opened." },
  validation_failed: { ar: "بعض الحقول غير صالحة. راجع الأرقام والنصوص المدخلة.", en: "Some fields are invalid. Review the numbers and text entered." },
  pdf_required: { ar: "يُقبل ملف PDF فقط.", en: "Only PDF files are accepted." },
  pdf_filename_required: { ar: "يُقبل ملف PDF فقط.", en: "Only PDF files are accepted." },
  invalid_pdf: { ar: "الملف المرفوع ليس ملف PDF صالحاً.", en: "The uploaded file is not a valid PDF." },
  document_too_large: { ar: "يتجاوز حجم الملف ٥ ميجابايت.", en: "The file exceeds 5 MB." },
  image_required: { ar: "ارفع صورة بصيغة JPEG أو PNG أو WebP.", en: "Upload a JPEG, PNG or WebP image." },
  invalid_image: { ar: "الصورة المرفوعة غير صالحة.", en: "The uploaded image is not valid." },
  image_size_invalid: { ar: "يجب ألا يتجاوز حجم الصورة ١٠ ميجابايت.", en: "The image must not exceed 10 MB." },
  photo_already_received: { ar: "وصلت صورة لهذا الدواء من قبل.", en: "A photo for this medicine has already arrived." },
  caregiver_not_registered: { ar: "لم يُسجَّل مرافق لهذه الحالة عند الخروج.", en: "No caregiver was registered for this case at discharge." },
  journey_not_approved: { ar: "خطة المتابعة لم تُعتمد بعد.", en: "The follow-up plan is not approved yet." },
  medication_not_found: { ar: "هذا الدواء غير موجود في الخطة المعتمدة.", en: "This medicine is not in the approved plan." },
  storage_unavailable: { ar: "خدمة التخزين غير متاحة حالياً. حاول لاحقاً.", en: "File storage is temporarily unavailable. Try again later." },
};

export function displayError(error: unknown, locale: Locale): string {
  if (error instanceof HawlakApiError) {
    return errorMessages[error.code]?.[locale] ?? (locale === "ar" ? "تعذّر إكمال الطلب. حاول مرة أخرى." : "Unable to complete the request. Try again.");
  }
  return locale === "ar" ? "تعذّر الاتصال بالخادم. تحقق من الاتصال وحاول مرة أخرى." : "Unable to reach the server. Check the connection and try again.";
}

const intlLocale = (locale: Locale) => (locale === "ar" ? "ar-SA" : "en-GB");

export function formatDateTime(value: string | Date, locale: Locale): string {
  return new Date(value).toLocaleString(intlLocale(locale), { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(value: string | Date, locale: Locale): string {
  return new Date(value).toLocaleDateString(intlLocale(locale), { dateStyle: "medium" });
}

export function formatShort(value: string | Date, locale: Locale): string {
  return new Date(value).toLocaleString(intlLocale(locale), { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function formatTime(value: string | Date, locale: Locale): string {
  return new Date(value).toLocaleTimeString(intlLocale(locale), { hour: "2-digit", minute: "2-digit" });
}

export function formatNumber(value: number, locale: Locale): string {
  return value.toLocaleString(locale === "ar" ? "ar-SA" : "en-GB");
}

/** Relative wording for recent timestamps; falls back to a date. */
export function formatRelative(value: string | Date, locale: Locale): string {
  const diff = (new Date(value).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(intlLocale(locale), { numeric: "auto" });
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86_400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 7 * 86_400) return rtf.format(Math.round(diff / 86_400), "day");
  return formatDate(value, locale);
}

export const pick = (labels: Record<string, Bilingual>, key: string, locale: Locale) => labels[key]?.[locale] ?? key;
