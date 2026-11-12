import { useCallback, useEffect, useState } from "react";

import { displayError, type Locale } from "./App";
import { Icon } from "./Icon";
import type { CallPlan, CallRepeat, DischargeExtraction, GeneratedDraft, HawlakApi, InsuranceRecord, WorkspaceAlert, WorkspaceCaseDetail, WorkspaceCaseSummary, WorkspaceMedication } from "./api";

type Section = "cases" | "alerts";
type Tab = "source" | "coverage" | "content" | "medications" | "journey";

const labels = {
  ar: {
    cases: "الحالات", alerts: "التنبيهات", title: "مراجعة حالات الخروج", subtitle: "راجع المحتوى المُعدّ لكل مريض، وتحقق من التغطية التأمينية، ثم اعتمد خطة المتابعة.", alertsSubtitle: "تنبيهات خطط المتابعة النشطة التي تتطلب إجراءً من فريق الرعاية.",
    search: "البحث بالاسم أو رقم الحالة", empty: "لا توجد حالات مطابقة.", caseDetails: "تفاصيل الحالة",
    source: "ملخص الخروج", coverage: "التغطية", content: "الرسائل والمكالمة", medications: "الأدوية", journey: "التنفيذ",
    save: "حفظ المسودة", saving: "جارٍ الحفظ…", approve: "اعتماد خطة المتابعة", approving: "جارٍ الاعتماد…",
    voice: "الرسالة الصوتية للخروج عبر واتساب", call: "مكالمة المتابعة",
    schedule: "موعد مكالمة المتابعة", inHours: "بعد {n} ساعة من الاعتماد", pickDate: "تحديد تاريخ ووقت", firstCall: "موعد المكالمة الأولى", hoursAfter: "عدد الساعات بعد الاعتماد", repeat: "التكرار", occurrences: "عدد المكالمات", plannedCalls: "المواعيد المجدولة",
    opening: "افتتاحية المكالمة", questions: "أسئلة المتابعة", questionN: "السؤال {n}", addQuestion: "إضافة سؤال", completion: "ختام المكالمة",
    transfer: "نص التحويل إلى فريق الرعاية", responder: "رقم فريق الاستجابة", team: "جهة التحويل", approved: "معتمدة", pending: "بانتظار المراجعة",
    rejected: "مرفوضة", approveImage: "اعتماد الصورة", noAlerts: "لا توجد تنبيهات مفتوحة.", open: "مفتوح", resolved: "تمت المعالجة",
    document: "ملخص الخروج", patient: "المريض", preferred: "صيغة المخاطبة", status: "حالة المراجعة", medicationName: "اسم الدواء",
    dose: "تعليمات الجرعة", reminder: "نص التذكير", dispensed: "تم صرف الدواء", enableReminder: "تفعيل تذكير الدواء",
    uploadImage: "رفع صورة العبوة", uploadingImage: "جارٍ الرفع…", addMedication: "إضافة دواء", remove: "حذف", noMedications: "لم تُضف أدوية بعد. يجب إضافة دواء واحد على الأقل قبل الاعتماد.",
    queued: "اعتُمدت خطة المتابعة وجُدولت الرسائل والمكالمات للإرسال. رقم التسجيل في البرنامج: {ref}.", saved: "حُفظت المسودة.", openPdf: "فتح الملف في نافذة جديدة",
    extracted: "البيانات المستخرجة من ملخص الخروج", extractedMeds: "الأدوية", extractedStopped: "الأدوية الموقوفة", extractedNotes: "ملاحظات", fullText: "النص الكامل للملف",
    noText: "لا يحتوي الملف على نص قابل للقراءة، وقد يكون صورة ممسوحة ضوئياً. يُرجى إدخال المحتوى يدوياً.", unreadable: "تعذّرت قراءة الملف. يُرجى إدخال المحتوى يدوياً.", nothingFound: "لم يُعثر على قائمة أدوية في الملف. يُرجى إدخال الأدوية يدوياً.",
    resolve: "تأكيد المعالجة", noImage: "لا توجد صورة",
    generatedBy: "أعدّ حولك هذه المسودات تلقائياً من ملخص الخروج ({method}) بتاريخ {date}. يجب مراجعة كل نص ومطابقته مع الملف قبل الاعتماد.", methodTemplate: "قوالب النصوص المعتمدة", methodAi: "نموذج الذكاء الاصطناعي",
    notGenerated: "لم تُنشأ مسودات تلقائية لهذه الحالة. يمكنك إنشاؤها من ملخص الخروج أو إدخال النصوص يدوياً.", generate: "إنشاء المسودات من ملخص الخروج", regenerate: "إعادة إنشاء المسودات", regenerating: "جارٍ الإنشاء…",
    regenerateConfirm: "ستُستبدل نصوص الرسالة الصوتية والتذكيرات والمكالمة الحالية بمسودات جديدة من ملخص الخروج. هل تريد المتابعة؟", regenerated: "أُنشئت مسودات جديدة. يُرجى مراجعتها قبل الاعتماد.",
    originGenerated: "مُنشأ تلقائياً", originEdited: "عُدّل بعد الإنشاء", originManual: "أُدخل يدوياً",
    mixedLanguage: "ملخص الخروج بلغة مختلفة عن لغة المريض، لذا بقيت البنود السريرية بلغة الملف. يُرجى ترجمتها إلى لغة المريض قبل الاعتماد.", liveRejected: "لم تجتز مسودة الذكاء الاصطناعي فحص الأرقام والأدوية، فاستُخدمت القوالب المعتمدة بدلاً منها.",
    coverageTitle: "التحقق من التغطية التأمينية", memberId: "رقم العضوية", check: "التحقق من الأهلية", checking: "جارٍ التحقق…", recheck: "إعادة التحقق", eligible: "مؤهل", notEligible: "غير مؤهل", notFound: "العضو غير موجود",
    policy: "رقم الوثيقة", plan: "فئة التغطية", network: "الشبكة الطبية", period: "فترة التغطية", programme: "البرنامج", programName: "برنامج الرعاية بعد الخروج", manager: "مدير الحالة", checkedAt: "تاريخ التحقق", enrollment: "رقم التسجيل في البرنامج",
    notChecked: "لم يُتحقق من أهلية العضو بعد. أدخل رقم العضوية للتحقق من التغطية قبل الاعتماد.", coverageSource: "المصدر: نظام الأعضاء لدى شركة التأمين (بيئة تجريبية).", notFoundHint: "لم يُعثر على رقم العضوية في نظام الأعضاء. يُرجى التحقق من الرقم مع المستشفى.", policyLapsed: "انتهت صلاحية الوثيقة",
    checked: "حُدّثت بيانات التغطية.", approvalRecord: "سجل الاعتماد", demoMode: "وضع العرض مفعّل: لا تُرسل رسائل واتساب ولا تُجرى مكالمات فعلياً، وإنما تُحاكى خطوات التنفيذ فقط. يتطلب الإرسال الفعلي ربط مزودي واتساب وتحويل النص إلى صوت والمكالمات.", simulated: "تمت المحاكاة — لم يُرسل فعلياً", approvedBy: "اعتمدها", approvedAt: "تاريخ الاعتماد", noRuns: "تظهر خطوات التنفيذ بعد اعتماد خطة المتابعة.",
  },
  en: {
    cases: "Cases", alerts: "Alerts", title: "Discharge case review", subtitle: "Review the content prepared for each patient, verify insurance coverage, then approve the follow-up plan.", alertsSubtitle: "Alerts from active follow-up plans that require action by the care team.",
    search: "Search by name or case reference", empty: "No matching cases.", caseDetails: "Case details",
    source: "Discharge summary", coverage: "Coverage", content: "Messages and call", medications: "Medications", journey: "Delivery",
    save: "Save draft", saving: "Saving…", approve: "Approve follow-up plan", approving: "Approving…",
    voice: "WhatsApp discharge voice message", call: "Follow-up call",
    schedule: "Follow-up call schedule", inHours: "{n} hours after approval", pickDate: "Select date and time", firstCall: "First call", hoursAfter: "Hours after approval", repeat: "Repeat", occurrences: "Number of calls", plannedCalls: "Scheduled calls",
    opening: "Call opening", questions: "Follow-up questions", questionN: "Question {n}", addQuestion: "Add question", completion: "Call closing",
    transfer: "Transfer to care team message", responder: "Responder phone number", team: "Transfer destination", approved: "Approved", pending: "Pending review",
    rejected: "Rejected", approveImage: "Approve image", noAlerts: "There are no open alerts.", open: "Open", resolved: "Resolved",
    document: "Discharge summary", patient: "Patient", preferred: "Form of address", status: "Review status", medicationName: "Medication name",
    dose: "Dose instruction", reminder: "Reminder text", dispensed: "Medication dispensed", enableReminder: "Enable medication reminder",
    uploadImage: "Upload package image", uploadingImage: "Uploading…", addMedication: "Add medication", remove: "Remove", noMedications: "No medications have been added. At least one medication is required before approval.",
    queued: "The follow-up plan is approved and messages and calls are scheduled. Programme enrolment reference: {ref}.", saved: "Draft saved.", openPdf: "Open in a new window",
    extracted: "Information extracted from the discharge summary", extractedMeds: "Medications", extractedStopped: "Stopped medications", extractedNotes: "Notes", fullText: "Full document text",
    noText: "The file contains no readable text and may be a scanned image. Enter the content manually.", unreadable: "The file could not be read. Enter the content manually.", nothingFound: "No medication list was found in the file. Enter the medications manually.",
    resolve: "Mark as resolved", noImage: "No image",
    generatedBy: "Hawlak drafted this content from the discharge summary ({method}) on {date}. Review every text against the document before approval.", methodTemplate: "approved text templates", methodAi: "AI language model",
    notGenerated: "No drafts were generated for this case. Generate them from the discharge summary or enter the text manually.", generate: "Generate drafts from discharge summary", regenerate: "Regenerate drafts", regenerating: "Generating…",
    regenerateConfirm: "The current voice message, reminder and call texts will be replaced with new drafts from the discharge summary. Do you want to continue?", regenerated: "New drafts were generated. Review them before approval.",
    originGenerated: "Generated", originEdited: "Edited after generation", originManual: "Entered manually",
    mixedLanguage: "The discharge summary is in a different language from the patient's, so clinical items remain in the document's language. Translate them into the patient's language before approval.", liveRejected: "The AI draft did not pass the number and medication checks, so the approved templates were used instead.",
    coverageTitle: "Insurance coverage verification", memberId: "Member ID", check: "Verify eligibility", checking: "Verifying…", recheck: "Verify again", eligible: "Eligible", notEligible: "Not eligible", notFound: "Member not found",
    policy: "Policy number", plan: "Plan", network: "Provider network", period: "Coverage period", programme: "Programme", programName: "Post-discharge care programme", manager: "Case manager", checkedAt: "Verified on", enrollment: "Programme enrolment reference",
    notChecked: "Eligibility has not been verified. Enter the member ID to verify coverage before approval.", coverageSource: "Source: insurer member system (demo environment).", notFoundHint: "The member ID was not found in the member system. Confirm the ID with the hospital.", policyLapsed: "Policy lapsed",
    checked: "Coverage information updated.", approvalRecord: "Approval record", demoMode: "Demo mode is on: no WhatsApp messages are sent and no calls are placed; delivery steps are only simulated. Real delivery requires connecting the WhatsApp, text-to-speech and calling providers.", simulated: "Simulated — not actually sent", approvedBy: "Approved by", approvedAt: "Approved on", noRuns: "Delivery steps appear once the follow-up plan is approved.",
  },
} as const;

const statusLabel = { draft: { ar: "مسودة", en: "Draft" }, approved: { ar: "معتمدة", en: "Approved" } } as const;
const languageLabel = { ar: { ar: "العربية", en: "Arabic" }, en: { ar: "الإنجليزية", en: "English" } } as const;
const dialectLabel: Record<string, { ar: string; en: string }> = {
  "ar-SA-najdi": { ar: "نجدي", en: "Najdi" }, "ar-SA-hijazi": { ar: "حجازي", en: "Hijazi" }, "ar-SA-janoubi": { ar: "جنوبي", en: "Southern" },
};
const runKindLabel: Record<string, { ar: string; en: string }> = {
  discharge_voice_note: { ar: "رسالة الخروج الصوتية عبر واتساب", en: "WhatsApp discharge voice message" },
  medication_reminder: { ar: "تذكير الدواء مع صورة العبوة", en: "Medication reminder with package image" },
  follow_up_call: { ar: "مكالمة المتابعة", en: "Follow-up call" },
};
const runStatusLabel: Record<string, { ar: string; en: string }> = {
  pending: { ar: "مجدولة", en: "Scheduled" }, claimed: { ar: "قيد الإرسال", en: "Sending" }, sent: { ar: "أُرسلت", en: "Sent" },
  completed: { ar: "اكتملت", en: "Completed" }, failed: { ar: "تعذّر الإرسال — تتطلب متابعة", en: "Failed — follow-up required" }, transferred: { ar: "حُوّلت إلى فريق الرعاية", en: "Transferred to care team" },
};
const alertTypeLabel: Record<string, { ar: string; en: string }> = {
  medication_access: { ar: "دواء لم يُصرف", en: "Medication not dispensed" },
  call_escalation: { ar: "تصعيد من مكالمة المتابعة", en: "Follow-up call escalation" },
};
const answerKindLabel: Record<string, { ar: string; en: string }> = {
  red_flag: { ar: "إجابة تشير إلى علامة خطر", en: "red-flag answer" }, uncertain: { ar: "إجابة غير واضحة", en: "unclear answer" }, transfer_request: { ar: "طلب التحدث إلى أحد أعضاء الفريق", en: "request to speak to a team member" },
};
const repeatLabel: Record<CallRepeat, { ar: string; en: string }> = {
  none: { ar: "مرة واحدة", en: "Once" }, daily: { ar: "يومياً", en: "Daily" }, every_2_days: { ar: "كل يومين", en: "Every 2 days" }, weekly: { ar: "أسبوعياً", en: "Weekly" },
};
const repeatDays: Record<CallRepeat, number> = { none: 0, daily: 1, every_2_days: 2, weekly: 7 };
type Origin = "generated" | "edited" | "manual";
const originOf = (current: string, generated: string | undefined): Origin => generated === undefined ? "manual" : current.trim() === generated.trim() ? "generated" : "edited";
const callText = (opening: string, questions: { prompt: string }[], completion: string, transfer: string) => [opening, ...questions.map((q) => q.prompt), completion, transfer].join("\n");
const formatDate = (value: string, locale: Locale, withTime = true) => new Date(value).toLocaleString(locale === "ar" ? "ar-SA" : "en-GB", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });

function OriginBadge({ origin, locale }: { origin: Origin; locale: Locale }) {
  const t = labels[locale];
  return <span className={`origin origin--${origin}`}>{origin === "generated" ? t.originGenerated : origin === "edited" ? t.originEdited : t.originManual}</span>;
}

const pick = (labels: Record<string, { ar: string; en: string }>, key: string, locale: Locale) => labels[key]?.[locale] ?? key;

function alertDetail(alert: WorkspaceAlert, locale: Locale): string {
  if (alert.type === "medication_access") return alert.summary.split(": ").slice(1).join(": ");
  const kind = /Call escalation: (\w+)/.exec(alert.summary)?.[1];
  return kind ? pick(answerKindLabel, kind, locale) : alert.summary;
}

function useCaseFileUrl(api: HawlakApi, caseId: string, key: string | undefined) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!key) { setUrl(null); return; }
    let objectUrl: string | null = null;
    let cancelled = false;
    api.getCaseFile(caseId, key).then((blob) => { if (cancelled) return; objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); }).catch(() => setUrl(null));
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [api, caseId, key]);
  return url;
}

export function InsurerWorkspace({ api, locale, section, reviewer }: { api: HawlakApi; locale: Locale; section: Section; reviewer: string }) {
  const t = labels[locale];
  const [cases, setCases] = useState<WorkspaceCaseSummary[]>([]);
  const [alerts, setAlerts] = useState<WorkspaceAlert[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkspaceCaseDetail | null>(null);
  const [tab, setTab] = useState<Tab>("source");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"save" | "approve" | "draft" | "eligibility" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadCases = useCallback(async (preferredId?: string | null) => {
    setLoading(true);
    try {
      const result = await api.listWorkspaceCases();
      setCases(result.data);
      const nextId = preferredId ?? selectedId ?? result.data[0]?.caseId ?? null;
      setSelectedId(nextId);
      setDetail(nextId ? await api.getWorkspaceCase(nextId) : null);
      setError(null);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setLoading(false); }
  }, [api, locale, selectedId]);

  const loadAlerts = useCallback(async () => {
    try { setAlerts((await api.listWorkspaceAlerts()).data); setError(null); }
    catch (caught) { setError(displayError(caught, locale)); }
  }, [api, locale]);

  useEffect(() => { void loadCases(); }, [api]);
  const inFlight = detail?.deliveryRuns.some((run) => run.status === "pending" || run.status === "claimed");
  useEffect(() => {
    if (!detail || !inFlight) return;
    const timer = window.setInterval(() => { api.getWorkspaceCase(detail.caseId).then(setDetail).catch(() => undefined); }, 5_000);
    return () => window.clearInterval(timer);
  }, [api, detail?.caseId, inFlight]);
  useEffect(() => { setNotice(null); if (section === "alerts") void loadAlerts(); }, [section, loadAlerts]);

  async function resolveAlert(alertId: string) {
    try { await api.resolveWorkspaceAlert(alertId); await loadAlerts(); void loadCases(); }
    catch (caught) { setError(displayError(caught, locale)); }
  }

  async function chooseCase(caseId: string) {
    setSelectedId(caseId); setLoading(true); setError(null); setNotice(null);
    try { setDetail(await api.getWorkspaceCase(caseId)); }
    catch (caught) { setError(displayError(caught, locale)); }
    finally { setLoading(false); }
  }

  async function saveContent() {
    if (!detail || detail.reviewStatus === "approved") return;
    setAction("save"); setError(null); setNotice(null);
    try { await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail)); setDetail(await api.getWorkspaceCase(detail.caseId)); setNotice(t.saved); }
    catch (caught) { setError(displayError(caught, locale)); }
    finally { setAction(null); }
  }

  async function approve() {
    if (!detail || detail.reviewStatus === "approved") return;
    setAction("approve"); setError(null); setNotice(null);
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      const result = await api.approveWorkspaceCase(detail.caseId, reviewer, `approve-${detail.caseId}-${crypto.randomUUID()}`);
      await loadCases(detail.caseId);
      setNotice(t.queued.replace("{ref}", result.insurance?.enrollmentReference ?? "—")); setTab("journey");
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setAction(null); }
  }

  async function regenerate() {
    if (!detail || detail.reviewStatus === "approved") return;
    if (detail.generatedDraft && !window.confirm(t.regenerateConfirm)) return;
    setAction("draft"); setError(null); setNotice(null);
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      setDetail(await api.regenerateDrafts(detail.caseId)); setNotice(t.regenerated);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setAction(null); }
  }

  async function checkEligibility(memberId: string) {
    if (!detail || detail.reviewStatus === "approved") return;
    setAction("eligibility"); setError(null); setNotice(null);
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      setDetail(await api.checkEligibility(detail.caseId, memberId)); setNotice(t.checked); void loadCases(detail.caseId);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setAction(null); }
  }

  function updateMedication(medicationId: string, change: Partial<WorkspaceMedication>) {
    if (!detail || detail.reviewStatus === "approved") return;
    setDetail({ ...detail, medications: detail.medications.map((item) => item.medicationId === medicationId ? { ...item, ...change } : item) });
  }

  function addMedication() {
    if (!detail || detail.reviewStatus === "approved") return;
    const medication: WorkspaceMedication = {
      medicationId: `SYN-MED-${crypto.randomUUID().slice(0, 8)}`, displayName: "", doseInstruction: "", dispensed: true,
      image: null, reminderEnabled: false, reminderScript: "",
    };
    setDetail({ ...detail, medications: [...detail.medications, medication] });
  }

  async function uploadMedicationImage(medicationId: string, image: File) {
    if (!detail || detail.reviewStatus === "approved") return;
    setError(null);
    try {
      const stored = await api.uploadMedicationImage(detail.caseId, image);
      updateMedication(medicationId, {
        image: {
          source: "catalog",
          objectKey: stored.objectKey,
          reviewStatus: "pending",
        },
      });
    } catch (caught) {
      setError(displayError(caught, locale));
      throw caught;
    }
  }

  const filtered = cases.filter((item) => `${item.patientName} ${item.caseId}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const tabs: Array<{ value: Tab; label: string }> = [
    { value: "source", label: t.source }, { value: "coverage", label: t.coverage }, { value: "content", label: t.content },
    { value: "medications", label: t.medications }, { value: "journey", label: t.journey },
  ];

  return <div className="workspace workspace--wide">
    <header className="page-title-block"><div><h1>{section === "alerts" ? t.alerts : t.title}</h1><p>{section === "alerts" ? t.alertsSubtitle : t.subtitle}</p></div>{section === "cases" && <span className="record-count">{cases.length} {t.cases}</span>}</header>
    {error && <div className="notice notice--danger" role="alert">{error}</div>}
    {notice && <div className="notice notice--success" role="status">{notice}</div>}
    {section === "alerts" ? <AlertsPanel alerts={alerts} locale={locale} onResolve={(id) => void resolveAlert(id)} /> : <div className="case-layout">
      <aside className="case-list"><label className="search-field"><Icon name="search" size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.search} /></label>{!loading && filtered.length === 0 && <div className="compact-empty">{t.empty}</div>}{filtered.map((item) => <button key={item.caseId} className={selectedId === item.caseId ? "active" : ""} onClick={() => void chooseCase(item.caseId)}><span className="avatar">{item.patientName.slice(0, 1)}</span><span><b>{item.patientName}</b><small>{item.caseId}</small></span><i className={`status status--${item.reviewStatus}`}>{statusLabel[item.reviewStatus][locale]}</i>{item.alertCount > 0 && <em>{item.alertCount}</em>}</button>)}</aside>
      <section className="case-detail">{loading && !detail ? <div className="detail-loading" /> : detail && <>
        <header className="case-detail__header"><div><span>{detail.caseId}</span><h2>{detail.patientName}</h2>{detail.preferredFormOfAddress && <p>{t.preferred}: {detail.preferredFormOfAddress}</p>}</div><div className="case-detail__chips">{detail.insurance && <i className={`status status--coverage-${detail.insurance.status}`}>{coverageLabel(detail.insurance, locale)}</i>}<i className={`status status--${detail.reviewStatus}`}>{statusLabel[detail.reviewStatus][locale]}</i></div></header>
        <nav className="tabs" aria-label={t.caseDetails}>{tabs.map((item) => <button key={item.value} className={tab === item.value ? "active" : ""} onClick={() => setTab(item.value)}>{item.label}</button>)}</nav>
        <div className="tab-panel">{(tab === "content" || tab === "medications") && <DraftBanner detail={detail} locale={locale} busy={action === "draft"} onGenerate={() => void regenerate()} />}{tab === "source" && <SourceTab api={api} detail={detail} locale={locale} />}{tab === "coverage" && <CoverageTab detail={detail} locale={locale} busy={action === "eligibility"} onCheck={(memberId) => void checkEligibility(memberId)} />}{tab === "content" && <ContentTab detail={detail} locale={locale} onChange={setDetail} />}{tab === "medications" && <MedicationsTab api={api} detail={detail} locale={locale} onUpdate={updateMedication} onUpload={uploadMedicationImage} onAdd={addMedication} onRemove={(id) => setDetail({ ...detail, medications: detail.medications.filter((item) => item.medicationId !== id) })} />}{tab === "journey" && <JourneyTab detail={detail} locale={locale} />}</div>
        <footer className="case-actions"><button className="button" disabled={!!action || detail.reviewStatus === "approved"} onClick={() => void saveContent()}>{action === "save" ? t.saving : t.save}</button><button className="button button--primary" disabled={!!action || detail.reviewStatus === "approved"} onClick={() => void approve()}>{action === "approve" ? t.approving : t.approve}</button></footer>
      </>}</section>
    </div>}
  </div>;
}

function reviewedContent(detail: WorkspaceCaseDetail) {
  return { dischargeVoiceNote: detail.dischargeVoiceNote, medications: detail.medications, callPlan: detail.callPlan };
}

function AlertsPanel({ alerts, locale, onResolve }: { alerts: WorkspaceAlert[]; locale: Locale; onResolve: (id: string) => void }) {
  const t = labels[locale];
  if (alerts.length === 0) return <section className="empty-panel"><span>✓</span><h2>{t.noAlerts}</h2></section>;
  return <section className="alerts-panel">{alerts.map((alert) => <article key={alert.id} className={`alert-card alert-card--${alert.status}`}><span>{alert.status === "open" ? "!" : "✓"}</span><div><p><b>{pick(alertTypeLabel, alert.type, locale)}</b>{alertDetail(alert, locale) && ` — ${alertDetail(alert, locale)}`}</p><small>{alert.patientName && <><bdi>{alert.patientName}</bdi> · </>}<bdi>{alert.caseId}</bdi> · <bdi>{formatDate(alert.createdAt, locale)}</bdi></small></div>{alert.status === "open" ? <button className="button" onClick={() => onResolve(alert.id)}>{t.resolve}</button> : <b>{t.resolved}</b>}</article>)}</section>;
}

function SourceTab({ api, detail, locale }: { api: HawlakApi; detail: WorkspaceCaseDetail; locale: Locale }) {
  const t = labels[locale];
  const pdfUrl = useCaseFileUrl(api, detail.caseId, detail.sourceDocument.objectKey);
  return <><div className="source-grid"><div><span>{t.patient}</span><b>{detail.patientName}</b><small>{detail.preferredFormOfAddress || "—"}</small></div><div><span>{t.document}</span><b>{detail.sourceDocument.filename}</b><small>{languageLabel[detail.languageCode][locale]}{detail.languageCode === "ar" && ` · ${pick(dialectLabel, detail.dialectCode, locale)}`}</small></div><div><span>{t.status}</span><b>{statusLabel[detail.reviewStatus][locale]}</b>{detail.approvedAt && <small>{formatDate(detail.approvedAt, locale)}</small>}</div></div>
    <ExtractionPanel api={api} detail={detail} locale={locale} />
    {pdfUrl && <><a className="button" href={pdfUrl} target="_blank" rel="noreferrer">{t.openPdf}</a><iframe className="source-preview" src={pdfUrl} title={t.document} /></>}</>;
}

function ContentTab({ detail, locale, onChange }: { detail: WorkspaceCaseDetail; locale: Locale; onChange: (next: WorkspaceCaseDetail) => void }) {
  const t = labels[locale];
  const locked = detail.reviewStatus === "approved";
  const plan = detail.callPlan;
  const generated = detail.generatedDraft;
  const updateCall = (change: Partial<CallPlan>) => onChange({ ...detail, callPlan: { ...plan, ...change } });
  const updateQuestion = (index: number, prompt: string) => updateCall({ questions: plan.questions.map((item, i) => i === index ? { ...item, prompt } : item) });
  const nextQuestionId = () => { let n = plan.questions.length + 1; while (plan.questions.some((q) => q.id === `q-${n}`)) n += 1; return `q-${n}`; };
  const voiceOrigin = originOf(detail.dischargeVoiceNote.script, generated?.voiceScript);
  const callOrigin = originOf(callText(plan.openingScript, plan.questions, plan.completionScript, plan.transferScript), generated ? callText(generated.callOpening, generated.callQuestions, generated.callCompletion, generated.callTransfer) : undefined);
  return <div className="content-editor">
    <div className="field-span section-heading"><label className="checkbox-field"><input type="checkbox" checked={detail.dischargeVoiceNote.enabled} disabled={locked} onChange={(event) => onChange({ ...detail, dischargeVoiceNote: { ...detail.dischargeVoiceNote, enabled: event.target.checked } })} />{t.voice}</label><OriginBadge origin={voiceOrigin} locale={locale} /></div>
    <label className="field-span"><textarea className="script-field" dir="auto" disabled={locked || !detail.dischargeVoiceNote.enabled} value={detail.dischargeVoiceNote.script} onChange={(event) => onChange({ ...detail, dischargeVoiceNote: { ...detail.dischargeVoiceNote, script: event.target.value } })} /></label>
    <div className="field-span section-heading"><label className="checkbox-field"><input type="checkbox" checked={plan.enabled} disabled={locked} onChange={(event) => updateCall({ enabled: event.target.checked })} />{t.call}</label><OriginBadge origin={callOrigin} locale={locale} /></div>
    <fieldset className="field-span call-fields" disabled={locked || !plan.enabled}>
      <label>{t.opening}<textarea dir="auto" value={plan.openingScript} onChange={(event) => updateCall({ openingScript: event.target.value })} /></label>
      <label>{t.completion}<textarea dir="auto" value={plan.completionScript} onChange={(event) => updateCall({ completionScript: event.target.value })} /></label>
      <div className="field-span question-list"><b>{t.questions}</b>{plan.questions.map((question, index) => <div className="question-row" key={question.id}><label>{t.questionN.replace("{n}", String(index + 1))}<textarea dir="auto" value={question.prompt} onChange={(event) => updateQuestion(index, event.target.value)} /></label><button type="button" className="button" onClick={() => updateCall({ questions: plan.questions.filter((_, i) => i !== index) })}>{t.remove}</button></div>)}{plan.questions.length < 12 && <button type="button" className="button question-add" onClick={() => updateCall({ questions: [...plan.questions, { id: nextQuestionId(), prompt: "" }] })}>+ {t.addQuestion}</button>}</div>
      <label>{t.transfer}<textarea dir="auto" value={plan.transferScript} onChange={(event) => updateCall({ transferScript: event.target.value })} /></label>
      <div className="stacked-fields"><label>{t.team}<input value={plan.transferTarget} onChange={(event) => updateCall({ transferTarget: event.target.value })} /></label><label>{t.responder}<input dir="ltr" value={plan.responderPhoneE164} onChange={(event) => updateCall({ responderPhoneE164: event.target.value.replace(/\s/g, "") })} /></label></div>
    </fieldset>
    <CallSchedule plan={plan} locked={locked || !plan.enabled} locale={locale} onChange={updateCall} />
  </div>;
}

function DraftBanner({ detail, locale, busy, onGenerate }: { detail: WorkspaceCaseDetail; locale: Locale; busy: boolean; onGenerate: () => void }) {
  const t = labels[locale];
  const draft: GeneratedDraft | null = detail.generatedDraft;
  const locked = detail.reviewStatus === "approved";
  const method = draft?.generator.startsWith("openai") ? t.methodAi : t.methodTemplate;
  return <div className="draft-banner">
    <div><p>{draft ? t.generatedBy.replace("{method}", method).replace("{date}", formatDate(draft.generatedAt, locale)) : t.notGenerated}</p>
      {draft && draft.sourceLanguage !== detail.languageCode && draft.generator === "template" && !locked && <p className="draft-banner__warning">{t.mixedLanguage}</p>}
      {draft?.notes.includes("live_draft_rejected") && <p className="draft-banner__warning">{t.liveRejected}</p>}</div>
    {!locked && <button className="button" disabled={busy} onClick={onGenerate}>{busy ? t.regenerating : draft ? t.regenerate : t.generate}</button>}
  </div>;
}

function coverageLabel(insurance: InsuranceRecord, locale: Locale) {
  const t = labels[locale];
  return insurance.status === "eligible" ? t.eligible : insurance.status === "not_found" ? t.notFound : t.notEligible;
}

function CoverageTab({ detail, locale, busy, onCheck }: { detail: WorkspaceCaseDetail; locale: Locale; busy: boolean; onCheck: (memberId: string) => void }) {
  const t = labels[locale];
  const insurance = detail.insurance;
  const locked = detail.reviewStatus === "approved";
  const [memberId, setMemberId] = useState(insurance?.memberId ?? "");
  useEffect(() => setMemberId(detail.insurance?.memberId ?? ""), [detail.caseId, detail.insurance?.memberId]);
  const valid = /^[A-Za-z0-9-]{4,32}$/.test(memberId);
  const rows: Array<[string, string | undefined]> = insurance ? [
    [t.policy, insurance.policyNumber], [t.plan, insurance.plan], [t.network, insurance.network],
    [t.period, insurance.coverageStart && insurance.coverageEnd ? `${formatDate(insurance.coverageStart, locale, false)} – ${formatDate(insurance.coverageEnd, locale, false)}` : undefined],
    [t.programme, insurance.program ? t.programName : undefined],
    [t.manager, insurance.caseManager ? `${insurance.caseManager.name} · ${insurance.caseManager.phoneE164}` : undefined],
    [t.checkedAt, insurance.checkedAt ? formatDate(insurance.checkedAt, locale) : undefined],
    [t.enrollment, insurance.enrollmentReference],
  ] : [];
  return <section className="coverage-panel">
    <h3>{t.coverageTitle}</h3>
    {!insurance && <div className="notice notice--info">{t.notChecked}</div>}
    {insurance && <div className={`coverage-status coverage-status--${insurance.status}`}><b>{coverageLabel(insurance, locale)}</b><span><bdi>{insurance.memberId}</bdi>{insurance.reason === "policy_lapsed" && ` · ${t.policyLapsed}`}</span></div>}
    {insurance?.status === "not_found" && <div className="notice notice--danger">{t.notFoundHint}</div>}
    {rows.some(([, value]) => value) && <dl className="coverage-grid">{rows.filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><bdi>{value}</bdi></dd></div>)}</dl>}
    {!locked && <form className="coverage-check" onSubmit={(event) => { event.preventDefault(); if (valid) onCheck(memberId); }}><label>{t.memberId}<input dir="ltr" value={memberId} onChange={(event) => setMemberId(event.target.value.trim().toUpperCase())} placeholder="SYN-4471203" /></label><button className="button button--primary" disabled={!valid || busy}>{busy ? t.checking : insurance ? t.recheck : t.check}</button></form>}
    <small className="coverage-source">{t.coverageSource}</small>
  </section>;
}

const toLocalInput = (iso: string) => { const date = new Date(iso); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); };
const tomorrowAtTen = () => { const date = new Date(); date.setDate(date.getDate() + 1); date.setHours(10, 0, 0, 0); return date.toISOString(); };

function CallSchedule({ plan, locked, locale, onChange }: { plan: CallPlan; locked: boolean; locale: Locale; onChange: (change: Partial<CallPlan>) => void }) {
  const t = labels[locale];
  const repeat = plan.repeat ?? "none";
  const occurrences = repeat === "none" ? 1 : plan.occurrences ?? 1;
  const exact = !!plan.firstCallAt;
  const format = (date: Date) => date.toLocaleString(locale === "ar" ? "ar-SA" : "en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const times = exact ? Array.from({ length: occurrences }, (_, index) => new Date(new Date(plan.firstCallAt!).getTime() + index * repeatDays[repeat] * 86_400_000)) : [];
  return <fieldset className="field-span call-schedule" disabled={locked}>
    <legend>{t.schedule}</legend>
    <div className="chip-row">
      {[24, 48, 72].map((hours) => <button type="button" key={hours} className={!exact && plan.scheduledAfterHours === hours ? "chip active" : "chip"} onClick={() => onChange({ firstCallAt: null, scheduledAfterHours: hours })}>{t.inHours.replace("{n}", String(hours))}</button>)}
      <button type="button" className={exact ? "chip active" : "chip"} onClick={() => onChange({ firstCallAt: plan.firstCallAt ?? tomorrowAtTen() })}>{t.pickDate}</button>
    </div>
    <div className="schedule-fields">
      {exact
        ? <label>{t.firstCall}<input type="datetime-local" dir="ltr" min={toLocalInput(new Date().toISOString())} value={toLocalInput(plan.firstCallAt!)} onChange={(event) => event.target.value && onChange({ firstCallAt: new Date(event.target.value).toISOString() })} /></label>
        : <label>{t.hoursAfter}<input type="number" min="0" max="168" value={plan.scheduledAfterHours} onChange={(event) => onChange({ scheduledAfterHours: Math.min(168, Math.max(0, Number(event.target.value))) })} /></label>}
      <label>{t.repeat}<select value={repeat} onChange={(event) => { const next = event.target.value as CallRepeat; onChange({ repeat: next, occurrences: next === "none" ? 1 : Math.max(2, occurrences) }); }}>{(Object.keys(repeatLabel) as CallRepeat[]).map((value) => <option key={value} value={value}>{repeatLabel[value][locale]}</option>)}</select></label>
      <label>{t.occurrences}<select value={occurrences} disabled={repeat === "none"} onChange={(event) => onChange({ occurrences: Number(event.target.value) })}>{Array.from({ length: 14 }, (_, index) => index + 1).map((count) => <option key={count} value={count}>{count}</option>)}</select></label>
    </div>
    {times.length > 0 && <div className="schedule-summary"><b>{t.plannedCalls}</b><ol>{times.map((time) => <li key={time.toISOString()}><bdi>{format(time)}</bdi></li>)}</ol></div>}
  </fieldset>;
}

function MedicationsTab({ api, detail, locale, onUpdate, onUpload, onAdd, onRemove }: { api: HawlakApi; detail: WorkspaceCaseDetail; locale: Locale; onUpdate: (id: string, change: Partial<WorkspaceMedication>) => void; onUpload: (id: string, image: File) => Promise<void>; onAdd: () => void; onRemove: (id: string) => void }) {
  const t = labels[locale];
  const locked = detail.reviewStatus === "approved";
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  return <div className="medication-grid">
    {detail.medications.length === 0 && <div className="compact-empty">{t.noMedications}</div>}
    {detail.medications.map((item) => <article className="medication-editor" key={item.medicationId}>
      <MedicineImage api={api} caseId={detail.caseId} objectKey={item.image?.objectKey} alt={item.displayName} empty={t.noImage} />
      <div className="medication-fields">
        <label>{t.medicationName}<input disabled={locked} value={item.displayName} onChange={(event) => onUpdate(item.medicationId, { displayName: event.target.value })} /></label>
        <label>{t.dose}<input disabled={locked} value={item.doseInstruction} onChange={(event) => onUpdate(item.medicationId, { doseInstruction: event.target.value })} /></label>
        <label className="field-span"><span className="label-row">{t.reminder}<OriginBadge origin={originOf(item.reminderScript, detail.generatedDraft?.reminderScripts[item.medicationId])} locale={locale} /></span><input dir="auto" disabled={locked} value={item.reminderScript} onChange={(event) => onUpdate(item.medicationId, { reminderScript: event.target.value })} /></label>
        <label className="checkbox-field"><input type="checkbox" disabled={locked} checked={item.dispensed} onChange={(event) => onUpdate(item.medicationId, { dispensed: event.target.checked, reminderEnabled: event.target.checked ? item.reminderEnabled : false })} />{t.dispensed}</label>
        <label className="checkbox-field"><input type="checkbox" disabled={locked || !item.dispensed} checked={item.reminderEnabled} onChange={(event) => onUpdate(item.medicationId, { reminderEnabled: event.target.checked })} />{t.enableReminder}</label>
        {item.image && <span className={`image-state image-state--${item.image.reviewStatus === "pending" ? "candidate" : item.image.reviewStatus}`}>{item.image.reviewStatus === "approved" ? t.approved : item.image.reviewStatus === "pending" ? t.pending : t.rejected}</span>}
      </div>
      <div className="medication-actions">{!locked && <label className="button medication-upload">{uploadingId === item.medicationId ? t.uploadingImage : t.uploadImage}<input type="file" accept="image/jpeg,image/png,image/webp" disabled={uploadingId !== null} onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; setUploadingId(item.medicationId); void onUpload(item.medicationId, file).finally(() => setUploadingId(null)); }} /></label>}{item.image?.reviewStatus === "pending" && !locked && <button className="button" onClick={() => onUpdate(item.medicationId, { image: { ...item.image!, reviewStatus: "approved" } })}>{t.approveImage}</button>}{!locked && <button className="button" onClick={() => onRemove(item.medicationId)}>{t.remove}</button>}</div>
    </article>)}
    {!locked && <button className="button medication-add" onClick={onAdd}>+ {t.addMedication}</button>}
  </div>;
}

function JourneyTab({ detail, locale }: { detail: WorkspaceCaseDetail; locale: Locale }) {
  const t = labels[locale];
  if (detail.deliveryRuns.length === 0) return <div className="compact-empty">{t.noRuns}</div>;
  return <>
    {detail.deliveryMode === "mock" && <div className="notice notice--info">{t.demoMode}</div>}
    {detail.approvedAt && <dl className="coverage-grid approval-record"><div><dt>{t.approvedBy}</dt><dd><bdi>{detail.approvedBy}</bdi></dd></div><div><dt>{t.approvedAt}</dt><dd>{formatDate(detail.approvedAt, locale)}</dd></div>{detail.insurance?.enrollmentReference && <div><dt>{t.enrollment}</dt><dd><bdi>{detail.insurance.enrollmentReference}</bdi></dd></div>}</dl>}
    <ol className="journey-list">{detail.deliveryRuns.map((run) => <li key={run.id}><span /><div><b>{pick(runKindLabel, run.kind, locale)}</b><p>{run.providerRef?.startsWith("mock:") ? t.simulated : pick(runStatusLabel, run.status, locale)}</p></div><time>{formatDate(run.scheduledAt, locale)}</time></li>)}</ol>
  </>;
}

function MedicineImage({ api, caseId, objectKey, alt, empty }: { api: HawlakApi; caseId: string; objectKey?: string; alt: string; empty: string }) {
  const url = useCaseFileUrl(api, caseId, objectKey?.startsWith(`cases/${caseId}/`) ? objectKey : undefined);
  return <div className="medicine-image">{url ? <img src={url} alt={alt} /> : <span title={empty} aria-label={empty}>▣</span>}</div>;
}


function ExtractionPanel({ api, detail, locale }: { api: HawlakApi; detail: WorkspaceCaseDetail; locale: Locale }) {
  const t = labels[locale];
  const [extraction, setExtraction] = useState<DischargeExtraction | null>(null);
  useEffect(() => {
    let cancelled = false;
    setExtraction(null);
    api.getCaseExtraction(detail.caseId).then((result) => { if (!cancelled) setExtraction(result); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [api, detail.caseId]);
  if (!extraction) return null;
  if (extraction.status !== "parsed") return <div className="notice notice--danger">{extraction.status === "no_text" ? t.noText : t.unreadable}</div>;
  const docDir = extraction.language === "ar" ? "rtl" : "ltr";
  return <section className="extraction-panel">
    <h3>{t.extracted}</h3>
    {extraction.medications.length === 0 && <div className="notice notice--danger">{t.nothingFound}</div>}
        <div className="extraction-grid" dir={docDir}>
      {extraction.medications.length > 0 && <div><b>{t.extractedMeds}</b><ul>{extraction.medications.map((item, index) => <li key={index}><bdi>{item.name}</bdi>{item.instruction && <> — <bdi>{item.instruction}</bdi></>}</li>)}</ul></div>}
      {extraction.stoppedMedications.length > 0 && <div><b>{t.extractedStopped}</b><ul>{extraction.stoppedMedications.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      {extraction.sections.map((section, index) => <div key={index}><b>{section.heading}</b><ul>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></div>)}
      {extraction.notes.length > 0 && <div><b>{t.extractedNotes}</b><ul>{extraction.notes.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    </div>
    <details><summary>{t.fullText}</summary><pre dir={docDir}>{extraction.text}</pre></details>
  </section>;
}

