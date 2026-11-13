import type { CallRepeat, FactSource, InsuranceRecord, PhotoCheckStatus } from "../api";
import type { Bilingual, Locale } from "../i18n";

export type CaseTab = "source" | "coverage" | "medications" | "content" | "photos" | "journey";

export const t = {
  ar: {
    title: "مراجعة الحالات", caseDetails: "تفاصيل الحالة", retry: "إعادة المحاولة",
    toReview: "للمراجعة", approvedFilter: "معتمدة", all: "الكل", filter: "تصفية الحالات", search: "بحث بالاسم أو رقم الحالة",
    noMatches: "لا توجد حالات مطابقة.", noCases: "لا توجد حالات بعد", selectCase: "اختر حالة لعرضها", queueEmptyReview: "لا توجد حالات بانتظار المراجعة.",
    statusDraft: "بانتظار المراجعة", statusApproved: "معتمدة", preferred: "صيغة المخاطبة", openAlerts: "{n} تنبيه مفتوح",
    source: "ملخص الخروج", coverage: "التغطية", content: "الرسائل والمكالمة", medications: "الأدوية", photos: "صور الأدوية", journey: "التنفيذ",
    save: "حفظ", saving: "جارٍ الحفظ…", saved: "حُفظت المسودة.", unsaved: "تغييرات غير محفوظة", allSaved: "كل التغييرات محفوظة",
    approve: "اعتماد", approving: "جارٍ الاعتماد…", goTo: "الانتقال إلى {tab}", cancel: "إلغاء",
    approveTitle: "اعتماد خطة المتابعة", approveIntro: "سيُجدول ما يلي لـ {name}:", approveConfirm: "اعتماد وجدولة",
    approveImmutable: "لا يمكن تعديل المحتوى بعد الاعتماد.",
    dispatchVoice: "رسالة صوتية واحدة عبر واتساب", dispatchReminders: "تذكيرات الأدوية: {n}", dispatchReminders1: "تذكير دواء واحد", dispatchPhotoRequest: "طلب صور علب الأدوية عبر واتساب", dispatchCalls: "مكالمات المتابعة: {n}", dispatchCalls1: "مكالمة متابعة واحدة", firstCallShort: "الأولى",
    dispatchAlerts: "تنبيهات لأدوية لم تُصرف: {n}", dispatchAlerts1: "تنبيه لدواء لم يُصرف",
    approvedToast: "اعتُمدت خطة المتابعة. رقم التسجيل: {ref}",
    approvedBy: "اعتمدها",
    // Source
    document: "الملف", language: "اللغة", openPdf: "فتح في نافذة جديدة", extracted: "البيانات المستخرجة", extractedMeds: "الأدوية",
    extractedStopped: "أدوية موقوفة", extractedNotes: "ملاحظات", fullText: "عرض النص الكامل", noText: "لا يحتوي الملف على نص قابل للقراءة وقد يكون صورة ممسوحة. أدخل المحتوى يدوياً.",
    unreadable: "تعذّرت قراءة الملف. أدخل المحتوى يدوياً.", nothingFound: "لم يُعثر على قائمة أدوية في الملف.", loadingPdf: "جارٍ تحميل الملف…",
    // Coverage
    memberId: "رقم العضوية", check: "التحقق من الأهلية", checking: "جارٍ التحقق…", recheck: "إعادة التحقق", checked: "حُدّثت بيانات التغطية.",
    eligible: "مؤهل", notEligible: "غير مؤهل", notFound: "العضو غير موجود", policyLapsed: "انتهت صلاحية الوثيقة",
    policy: "رقم الوثيقة", plan: "فئة التغطية", network: "الشبكة الطبية", period: "فترة التغطية", programme: "البرنامج", programName: "الرعاية بعد الخروج",
    manager: "مدير الحالة", checkedAt: "تاريخ التحقق", enrollment: "رقم التسجيل في البرنامج", notChecked: "لم يُتحقق من الأهلية بعد.",
    notFoundHint: "تحقق من رقم العضوية مع المستشفى.", coverageSource: "المصدر: نظام الأعضاء لدى شركة التأمين (بيئة تجريبية)", memberInvalid: "من ٤ إلى ٣٢ حرفاً أو رقماً.",
    // Content
    voice: "الرسالة الصوتية", script: "النص", voiceHint: "تُرسل عبر واتساب بعد الاعتماد مباشرة.", call: "مكالمة المتابعة",
    opening: "الافتتاحية", questions: "الأسئلة", addQuestion: "إضافة سؤال", completion: "الختام", transfer: "نص التحويل إلى الفريق",
    responder: "رقم فريق الاستجابة", team: "جهة التحويل", remove: "حذف", removeQuestion: "حذف السؤال {n}",
    schedule: "الموعد", inHours: "بعد {n} ساعة", pickDate: "تاريخ محدد", firstCall: "المكالمة الأولى", hoursAfter: "ساعات بعد الاعتماد", repeat: "التكرار", occurrences: "عدد المكالمات",
    originGenerated: "مُنشأ تلقائياً", originEdited: "معدّل", originManual: "إدخال يدوي",
    generatedBy: "أُنشئت المسودات من ملخص الخروج ({method}) {date}. راجع كل نص قبل الاعتماد.", methodTemplate: "قوالب معتمدة", methodAi: "نموذج لغوي",
    notGenerated: "لا توجد مسودات تلقائية لهذه الحالة.", generate: "إنشاء المسودات", regenerate: "إعادة الإنشاء", regenerating: "جارٍ الإنشاء…",
    regenerateTitle: "إعادة إنشاء المسودات", regenerateConfirm: "ستُستبدل نصوص الرسالة الصوتية والتذكيرات والمكالمة الحالية بمسودات جديدة من ملخص الخروج.", regenerated: "أُنشئت مسودات جديدة.",
    mixedLanguage: "ملخص الخروج بلغة مختلفة عن لغة المريض، فبقيت البنود السريرية بلغة الملف. ترجمها قبل الاعتماد.", liveRejected: "لم تجتز مسودة النموذج فحص الأرقام والأدوية، فاستُخدمت القوالب المعتمدة.",
    // Medications
    medicationName: "اسم الدواء", dose: "الجرعة", reminder: "نص التذكير", dispensed: "صُرف الدواء", enableReminder: "تذكير يومي",
    uploadImage: "رفع صورة", replaceImage: "استبدال الصورة", uploadingImage: "جارٍ الرفع…", approveImage: "اعتماد الصورة", imageApproved: "صورة معتمدة", imagePending: "صورة بانتظار الاعتماد", imageRejected: "صورة مرفوضة", noImage: "لا توجد صورة",
    addMedication: "إضافة دواء", removeMedication: "حذف الدواء", noMedications: "لا توجد أدوية.", removed: "حُذف «{name}».", undo: "تراجع", unnamed: "دواء بلا اسم",
    notDispensedHint: "يُنشأ تنبيه لفريق الرعاية عند الاعتماد.",
    needsAttention: "تتطلب إجراءً", failedSteps: "{n} تعذّرت", registered: "وقت التسجيل", nextStep: "التالي:",
    priorityHigh: "عالية الأولوية", priorityLow: "للمراجعة",
    unitStrength: "تركيز الحبة أو الكبسولة المؤكد", reminderTimes: "أوقات التذكير (بتوقيت السعودية)", timesHint: "مثال: 08:00، 20:00. بدونها يُرسل التذكير عند الاعتماد.",
    factDose: "الجرعة الموصوفة", factUnits: "عدد الحبات لكل جرعة", factTimes: "أوقات التذكير", factsAfterSave: "تُحدَّث بعد الحفظ.",
    patientPhoto: "الصورة من المريض بعد الاعتماد.", photoAfterApproval: "بعد الاعتماد يطلب حولك من المريض تصوير هذه العلبة باسمها المعتمد.",
    noPhotos: "لم تصل صور علب أدوية من المريض أو مقدم الرعاية بعد.", photosNote: "يطلب حولك صورة كل دواء معتمد باسمه، فترتبط كل صورة بدوائها. يُقرأ النص المطبوع على العلبة فقط ويُقارن آلياً بذلك الدواء. لا يُرسل للمريض أي حكم؛ القرار لك.",
    sentBy: "أرسلها", fromPatient: "المريض", fromCaregiver: "مقدم الرعاية", label: "المكتوب على العلبة", planned: "الدواء في الخطة", photoStatus: "نتيجة الفحص", notRead: "لم تُقرأ",
    confirmPhoto: "تأكيد المطابقة", followUp: "يحتاج متابعة", reviewed: "راجعها {who}", photoReviewed: "حُفظت مراجعة الصورة.",
    // Delivery
    demoMode: "وضع العرض: لا تُرسل رسائل ولا تُجرى مكالمات فعلياً، وتُحاكى خطوات التنفيذ فقط.", simulated: "محاكاة — لم يُرسل فعلياً",
    noRuns: "تظهر خطوات التنفيذ بعد الاعتماد.", approvedAt: "تاريخ الاعتماد",
    // Alerts
    alerts: "التنبيهات", open: "مفتوحة", resolved: "تمت معالجتها", resolve: "تأكيد المعالجة", resolvedToast: "عولج التنبيه.", openCase: "فتح الحالة",
    noOpenAlerts: "لا توجد تنبيهات مفتوحة", noAlertsHint: "تظهر هنا التنبيهات الواردة من خطط المتابعة النشطة.", noResolved: "لا توجد تنبيهات معالجة.",
  },
  en: {
    title: "Case review", caseDetails: "Case details", retry: "Retry",
    toReview: "To review", approvedFilter: "Approved", all: "All", filter: "Filter cases", search: "Search name or case reference",
    noMatches: "No matching cases.", noCases: "No cases yet", selectCase: "Select a case", queueEmptyReview: "No cases are awaiting review.",
    statusDraft: "Awaiting review", statusApproved: "Approved", preferred: "Form of address", openAlerts: "{n} open alerts",
    source: "Discharge summary", coverage: "Coverage", content: "Messages and call", medications: "Medications", photos: "Medicine photos", journey: "Delivery",
    save: "Save", saving: "Saving…", saved: "Draft saved.", unsaved: "Unsaved changes", allSaved: "All changes saved",
    approve: "Approve", approving: "Approving…", goTo: "Go to {tab}", cancel: "Cancel",
    approveTitle: "Approve follow-up plan", approveIntro: "The following will be scheduled for {name}:", approveConfirm: "Approve and schedule",
    approveImmutable: "Content cannot be edited after approval.",
    dispatchVoice: "One WhatsApp voice message", dispatchReminders: "{n} medication reminders", dispatchReminders1: "One medication reminder", dispatchPhotoRequest: "One WhatsApp request for medicine-box photos", dispatchCalls: "{n} follow-up calls", dispatchCalls1: "One follow-up call", firstCallShort: "first",
    dispatchAlerts: "{n} alerts for medications not dispensed", dispatchAlerts1: "One alert for a medication not dispensed",
    approvedToast: "Follow-up plan approved. Enrolment reference: {ref}",
    approvedBy: "Approved by",
    document: "Document", language: "Language", openPdf: "Open in new window", extracted: "Extracted information", extractedMeds: "Medications",
    extractedStopped: "Stopped medications", extractedNotes: "Notes", fullText: "Show full text", noText: "The file contains no readable text and may be a scanned image. Enter the content manually.",
    unreadable: "The file could not be read. Enter the content manually.", nothingFound: "No medication list was found in the file.", loadingPdf: "Loading document…",
    memberId: "Member ID", check: "Verify eligibility", checking: "Verifying…", recheck: "Verify again", checked: "Coverage updated.",
    eligible: "Eligible", notEligible: "Not eligible", notFound: "Member not found", policyLapsed: "Policy lapsed",
    policy: "Policy number", plan: "Plan", network: "Provider network", period: "Coverage period", programme: "Programme", programName: "Post-discharge care",
    manager: "Case manager", checkedAt: "Verified on", enrollment: "Enrolment reference", notChecked: "Eligibility has not been verified.",
    notFoundHint: "Confirm the member ID with the hospital.", coverageSource: "Source: insurer member system (demo environment)", memberInvalid: "4–32 letters, digits or hyphens.",
    voice: "Voice message", script: "Script", voiceHint: "Sent on WhatsApp immediately after approval.", call: "Follow-up call",
    opening: "Opening", questions: "Questions", addQuestion: "Add question", completion: "Closing", transfer: "Transfer message",
    responder: "Responder number", team: "Transfer destination", remove: "Remove", removeQuestion: "Remove question {n}",
    schedule: "Schedule", inHours: "In {n} h", pickDate: "Specific date", firstCall: "First call", hoursAfter: "Hours after approval", repeat: "Repeat", occurrences: "Number of calls",
    originGenerated: "Generated", originEdited: "Edited", originManual: "Manual",
    generatedBy: "Drafted from the discharge summary ({method}) {date}. Review every text before approval.", methodTemplate: "approved templates", methodAi: "language model",
    notGenerated: "No drafts have been generated for this case.", generate: "Generate drafts", regenerate: "Regenerate", regenerating: "Generating…",
    regenerateTitle: "Regenerate drafts", regenerateConfirm: "The current voice message, reminder and call texts will be replaced with new drafts from the discharge summary.", regenerated: "New drafts generated.",
    mixedLanguage: "The discharge summary is in a different language from the patient's, so clinical items remain in the document's language. Translate them before approval.", liveRejected: "The model draft did not pass the number and medication checks, so approved templates were used.",
    medicationName: "Medication", dose: "Dose", reminder: "Reminder text", dispensed: "Dispensed", enableReminder: "Daily reminder",
    uploadImage: "Upload image", replaceImage: "Replace image", uploadingImage: "Uploading…", approveImage: "Approve image", imageApproved: "Image approved", imagePending: "Image awaiting approval", imageRejected: "Image rejected", noImage: "No image",
    addMedication: "Add medication", removeMedication: "Remove medication", noMedications: "No medications.", removed: "“{name}” removed.", undo: "Undo", unnamed: "Unnamed medication",
    notDispensedHint: "An alert is raised for the care team on approval.",
    needsAttention: "Needs action", failedSteps: "{n} failed", registered: "Registered", nextStep: "Next:",
    priorityHigh: "High priority", priorityLow: "For review",
    unitStrength: "Confirmed strength of one tablet or capsule", reminderTimes: "Reminder times (Saudi time)", timesHint: "Example: 08:00, 20:00. Without them the reminder goes at approval.",
    factDose: "Prescribed dose", factUnits: "Tablets or capsules per dose", factTimes: "Reminder times", factsAfterSave: "Updated after saving.",
    patientPhoto: "Photo sent by the patient after approval.", photoAfterApproval: "After approval, Hawlak asks the patient to photograph this box using its approved name.",
    noPhotos: "No medicine-box photos have arrived from the patient or caregiver.", photosNote: "Hawlak requests each approved medicine by name, so every photo stays linked to its medicine. Only the printed label is read and compared with that medicine. No verdict is sent to the patient; the decision remains with you.",
    sentBy: "Sent by", fromPatient: "Patient", fromCaregiver: "Caregiver", label: "Printed label", planned: "Medicine in plan", photoStatus: "Check result", notRead: "Not read",
    confirmPhoto: "Confirm match", followUp: "Needs follow-up", reviewed: "Reviewed by {who}", photoReviewed: "Photo review saved.",
    demoMode: "Demo mode: no messages are sent and no calls are placed. Delivery steps are simulated.", simulated: "Simulated — not actually sent",
    noRuns: "Delivery steps appear after approval.", approvedAt: "Approved on",
    alerts: "Alerts", open: "Open", resolved: "Resolved", resolve: "Mark resolved", resolvedToast: "Alert resolved.", openCase: "Open case",
    noOpenAlerts: "No open alerts", noAlertsHint: "Alerts from active follow-up plans appear here.", noResolved: "No resolved alerts.",
  },
} as const;

export const languageLabel: Record<string, Bilingual> = { ar: { ar: "العربية", en: "Arabic" }, en: { ar: "الإنجليزية", en: "English" } };
export const dialectLabel: Record<string, Bilingual> = {
  "ar-SA-najdi": { ar: "نجدي", en: "Najdi" }, "ar-SA-hijazi": { ar: "حجازي", en: "Hijazi" }, "ar-SA-janoubi": { ar: "جنوبي", en: "Southern" },
};
export const runKindLabel: Record<string, Bilingual> = {
  discharge_voice_note: { ar: "رسالة صوتية عبر واتساب", en: "WhatsApp voice message" },
  medication_reminder: { ar: "تذكير دواء", en: "Medication reminder" },
  follow_up_call: { ar: "مكالمة متابعة", en: "Follow-up call" },
  photo_request: { ar: "طلب صور علب الأدوية عبر واتساب", en: "WhatsApp request for medicine-box photos" },
};
export const runKindIcon: Record<string, string> = { discharge_voice_note: "message", medication_reminder: "pill", follow_up_call: "phone", photo_request: "image" };
export const runStatusLabel: Record<string, Bilingual> = {
  pending: { ar: "مجدولة", en: "Scheduled" }, claimed: { ar: "قيد الإرسال", en: "Sending" }, sent: { ar: "أُرسلت", en: "Sent" },
  completed: { ar: "اكتملت", en: "Completed" }, failed: { ar: "تعذّر الإرسال", en: "Failed" }, transferred: { ar: "حُوّلت إلى الفريق", en: "Transferred to care team" },
};
export const runStatusTone: Record<string, "neutral" | "success" | "warning" | "danger" | "info"> = {
  pending: "neutral", claimed: "info", sent: "success", completed: "success", failed: "danger", transferred: "warning",
};
export const alertTypeLabel: Record<string, Bilingual> = {
  medication_access: { ar: "دواء لم يُصرف", en: "Medication not dispensed" },
  call_escalation: { ar: "تصعيد من مكالمة المتابعة", en: "Follow-up call escalation" },
  medicine_photo_mismatch: { ar: "صورة دواء لا تطابق الخطة", en: "Medicine photo does not match the plan" },
  medicine_photos_ready: { ar: "وصلت صور كل الأدوية", en: "All medicine photos received" },
};
export const photoCheckLabel: Record<PhotoCheckStatus, Bilingual> = {
  matched: { ar: "مطابقة للخطة", en: "Matches the plan" },
  strength_mismatch: { ar: "التركيز مختلف عن الخطة", en: "Strength differs from the plan" },
  different_medicine: { ar: "دواء مختلف عن المطلوب", en: "Different from the requested medicine" },
  extra: { ar: "صورة إضافية", en: "Extra photo" },
  unreadable: { ar: "الصورة غير واضحة", en: "Photo not readable" },
  not_checked: { ar: "بانتظار مراجعتك", en: "Awaiting your check" },
};
export const answerKindLabel: Record<string, Bilingual> = {
  red_flag: { ar: "إجابة تشير إلى علامة خطر", en: "Red-flag answer" }, uncertain: { ar: "إجابة غير واضحة", en: "Unclear answer" }, transfer_request: { ar: "طلب التحدث إلى الفريق", en: "Asked to speak to the team" },
};
export const repeatLabel: Record<CallRepeat, Bilingual> = {
  none: { ar: "مرة واحدة", en: "Once" }, daily: { ar: "يومياً", en: "Daily" }, every_2_days: { ar: "كل يومين", en: "Every 2 days" }, weekly: { ar: "أسبوعياً", en: "Weekly" },
};

export function coverageLabel(insurance: InsuranceRecord, locale: Locale) {
  const text = t[locale];
  return insurance.status === "eligible" ? text.eligible : insurance.status === "not_found" ? text.notFound : text.notEligible;
}

export const factSourceLabel: Record<FactSource, Bilingual> = {
  prescribed: { ar: "من تعليمات الخروج", en: "from the discharge instructions" }, calculated: { ar: "محسوب", en: "calculated" },
  reminder_preference: { ar: "وقت تذكير مختار", en: "chosen reminder time" }, unknown: { ar: "غير معروف", en: "unknown" },
};
export const factReasonLabel: Record<string, Bilingual> = {
  prescribed_dose_unknown: { ar: "لا توجد جرعة واحدة واضحة في التعليمات", en: "the instruction has no single dose amount" },
  count_already_prescribed: { ar: "العدد مذكور في التعليمات", en: "the instruction already gives the count" },
  unit_strength_unknown: { ar: "يحتاج تركيز الحبة المؤكد", en: "needs the confirmed strength" },
  unit_mismatch: { ar: "وحدة الجرعة تختلف عن وحدة التركيز", en: "dose and strength use different units" },
  not_whole_unit: { ar: "ليست حبة كاملة؛ يراجعها الصيدلي", en: "not a whole tablet; a pharmacist must check" },
};
export const alertTypeIcon: Record<string, string> = { medication_access: "pill", call_escalation: "phone", medicine_photo_mismatch: "image", medicine_photos_ready: "image" };
