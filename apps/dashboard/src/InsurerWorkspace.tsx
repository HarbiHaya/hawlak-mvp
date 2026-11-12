import { useCallback, useEffect, useState } from "react";

import { displayError, type Locale } from "./App";
import type { HawlakApi, WorkspaceAlert, WorkspaceCaseDetail, WorkspaceCaseSummary, WorkspaceMedication } from "./api";

type Section = "cases" | "alerts";
type Tab = "source" | "content" | "medications" | "journey";

const labels = {
  ar: {
    cases: "الحالات", alerts: "التنبيهات", title: "متابعة الخروج", search: "بحث بالاسم أو رقم الحالة", empty: "لا توجد حالات بعد",
    source: "المصدر", content: "المحتوى", medications: "الأدوية", journey: "الرحلة", save: "حفظ المسودة", saving: "جارٍ الحفظ…",
    approve: "اعتماد وبدء المتابعة", approving: "جارٍ الاعتماد…", voice: "رسالة الخروج الصوتية", call: "مكالمة المتابعة",
    delay: "المكالمة بعد", hours: "ساعات", opening: "بداية المكالمة", question: "سؤال المتابعة", completion: "نهاية المكالمة",
    transfer: "رسالة التحويل", responder: "رقم فريق الاستجابة", team: "فريق التحويل", approved: "معتمد", pending: "بانتظار المراجعة",
    rejected: "مرفوض", approveImage: "اعتماد الصورة", noAlerts: "لا توجد تنبيهات مفتوحة", open: "مفتوح", resolved: "مغلق",
    document: "ملف الخروج", patient: "المريض", preferred: "النداء الصوتي", status: "الحالة", medicationName: "اسم الدواء",
    dose: "تعليمات الجرعة", reminder: "نص التذكير", dispensed: "تم صرفه", enableReminder: "تفعيل التذكير",
    imageKey: "مرجع صورة الدواء", uploadImage: "رفع صورة الدواء", uploadingImage: "جارٍ الرفع…", addMedication: "إضافة دواء", remove: "حذف", noMedications: "أضف دواء واحداً على الأقل قبل الاعتماد.",
    queued: "تم الاعتماد. أضيفت الرسائل والمكالمة إلى قائمة التنفيذ.",
  },
  en: {
    cases: "Cases", alerts: "Alerts", title: "Discharge follow-up", search: "Search name or case ID", empty: "No cases yet",
    source: "Source", content: "Content", medications: "Medications", journey: "Journey", save: "Save draft", saving: "Saving…",
    approve: "Approve and start follow-up", approving: "Approving…", voice: "Discharge voice note", call: "Follow-up call",
    delay: "Call after", hours: "hours", opening: "Call opening", question: "Follow-up question", completion: "Call closing",
    transfer: "Transfer message", responder: "Responder phone", team: "Transfer team", approved: "Approved", pending: "Needs review",
    rejected: "Rejected", approveImage: "Approve image", noAlerts: "No open alerts", open: "Open", resolved: "Resolved",
    document: "Discharge document", patient: "Patient", preferred: "Voice address", status: "Status", medicationName: "Medication name",
    dose: "Dose instruction", reminder: "Reminder script", dispensed: "Dispensed", enableReminder: "Enable reminder",
    imageKey: "Medication image reference", uploadImage: "Upload medicine image", uploadingImage: "Uploading…", addMedication: "Add medication", remove: "Remove", noMedications: "Add at least one medication before approval.",
    queued: "Approved. Messages and the call are queued for delivery.",
  },
} as const;

const statusLabel = { draft: { ar: "مسودة", en: "Draft" }, approved: { ar: "معتمد", en: "Approved" } } as const;

export function InsurerWorkspace({ api, locale }: { api: HawlakApi; locale: Locale }) {
  const t = labels[locale];
  const [section, setSection] = useState<Section>("cases");
  const [cases, setCases] = useState<WorkspaceCaseSummary[]>([]);
  const [alerts, setAlerts] = useState<WorkspaceAlert[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkspaceCaseDetail | null>(null);
  const [tab, setTab] = useState<Tab>("source");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"save" | "approve" | null>(null);
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
  useEffect(() => { if (section === "alerts") void loadAlerts(); }, [section, loadAlerts]);

  async function chooseCase(caseId: string) {
    setSelectedId(caseId); setLoading(true); setError(null); setNotice(null);
    try { setDetail(await api.getWorkspaceCase(caseId)); setSection("cases"); }
    catch (caught) { setError(displayError(caught, locale)); }
    finally { setLoading(false); }
  }

  async function saveContent() {
    if (!detail || detail.reviewStatus === "approved") return;
    setAction("save"); setError(null); setNotice(null);
    try { await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail)); setDetail(await api.getWorkspaceCase(detail.caseId)); }
    catch (caught) { setError(displayError(caught, locale)); }
    finally { setAction(null); }
  }

  async function approve() {
    if (!detail || detail.reviewStatus === "approved") return;
    setAction("approve"); setError(null); setNotice(null);
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      await api.approveWorkspaceCase(detail.caseId, "SYN-INTEGRATED-CARE-REVIEWER", `approve-${detail.caseId}-${crypto.randomUUID()}`);
      await loadCases(detail.caseId);
      setNotice(t.queued); setTab("journey");
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
    { value: "source", label: t.source }, { value: "content", label: t.content },
    { value: "medications", label: t.medications }, { value: "journey", label: t.journey },
  ];

  return <div className="workspace workspace--wide">
    <header className="insurer-header"><div><span>{locale === "ar" ? "شركة التأمين" : "Insurer"}</span><h1>{t.title}</h1></div><nav><button className={section === "cases" ? "active" : ""} onClick={() => setSection("cases")}>{t.cases}<b>{cases.length}</b></button><button className={section === "alerts" ? "active" : ""} onClick={() => setSection("alerts")}>{t.alerts}<b className="alert-count">{alerts.filter((item) => item.status === "open").length}</b></button></nav></header>
    {error && <div className="notice notice--danger" role="alert">{error}</div>}
    {notice && <div className="notice notice--success" role="status">{notice}</div>}
    {section === "alerts" ? <AlertsPanel alerts={alerts} locale={locale} /> : <div className="case-layout">
      <aside className="case-list"><label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.search} /></label>{!loading && filtered.length === 0 && <div className="compact-empty">{t.empty}</div>}{filtered.map((item) => <button key={item.caseId} className={selectedId === item.caseId ? "active" : ""} onClick={() => void chooseCase(item.caseId)}><span className="avatar">{item.patientName.slice(0, 1)}</span><span><b>{item.patientName}</b><small>{item.caseId}</small></span><i className={`status status--${item.reviewStatus}`}>{statusLabel[item.reviewStatus][locale]}</i>{item.alertCount > 0 && <em>{item.alertCount}</em>}</button>)}</aside>
      <section className="case-detail">{loading && !detail ? <div className="detail-loading" /> : detail && <>
        <header className="case-detail__header"><div><span>{detail.caseId}</span><h2>{detail.patientName}</h2>{detail.preferredFormOfAddress && <p>{t.preferred}: {detail.preferredFormOfAddress}</p>}</div><i className={`status status--${detail.reviewStatus}`}>{statusLabel[detail.reviewStatus][locale]}</i></header>
        <nav className="tabs" aria-label={locale === "ar" ? "تفاصيل الحالة" : "Case details"}>{tabs.map((item) => <button key={item.value} className={tab === item.value ? "active" : ""} onClick={() => setTab(item.value)}>{item.label}</button>)}</nav>
        <div className="tab-panel">{tab === "source" && <SourceTab detail={detail} locale={locale} />}{tab === "content" && <ContentTab detail={detail} locale={locale} onChange={setDetail} />}{tab === "medications" && <MedicationsTab detail={detail} locale={locale} onUpdate={updateMedication} onUpload={uploadMedicationImage} onAdd={addMedication} onRemove={(id) => setDetail({ ...detail, medications: detail.medications.filter((item) => item.medicationId !== id) })} />}{tab === "journey" && <JourneyTab detail={detail} locale={locale} />}</div>
        <footer className="case-actions"><button className="button" disabled={!!action || detail.reviewStatus === "approved"} onClick={() => void saveContent()}>{action === "save" ? t.saving : t.save}</button><button className="button button--primary" disabled={!!action || detail.reviewStatus === "approved"} onClick={() => void approve()}>{action === "approve" ? t.approving : t.approve}</button></footer>
      </>}</section>
    </div>}
  </div>;
}

function reviewedContent(detail: WorkspaceCaseDetail) {
  return { dischargeVoiceNote: detail.dischargeVoiceNote, medications: detail.medications, callPlan: detail.callPlan };
}

function AlertsPanel({ alerts, locale }: { alerts: WorkspaceAlert[]; locale: Locale }) {
  const t = labels[locale];
  if (alerts.length === 0) return <section className="empty-panel"><span>✓</span><h2>{t.noAlerts}</h2></section>;
  return <section className="alerts-panel">{alerts.map((alert) => <article key={alert.id} className={`alert-card alert-card--${alert.status}`}><span>{alert.status === "open" ? "!" : "✓"}</span><div><h2>{alert.caseId}</h2><p>{alert.summary}</p><small>{new Date(alert.createdAt).toLocaleString(locale === "ar" ? "ar-SA" : "en-US")}</small></div><b>{alert.status === "open" ? t.open : t.resolved}</b></article>)}</section>;
}

function SourceTab({ detail, locale }: { detail: WorkspaceCaseDetail; locale: Locale }) {
  const t = labels[locale];
  return <div className="source-grid"><div><span>{t.patient}</span><b>{detail.patientName}</b><small>{detail.preferredFormOfAddress || "—"}</small></div><div><span>{t.document}</span><b>{detail.sourceDocument.filename}</b><small>{detail.languageCode} · {detail.dialectCode}</small></div><div><span>{t.status}</span><b>{statusLabel[detail.reviewStatus][locale]}</b>{detail.approvedAt && <small>{new Date(detail.approvedAt).toLocaleString(locale === "ar" ? "ar-SA" : "en-US")}</small>}</div></div>;
}

function ContentTab({ detail, locale, onChange }: { detail: WorkspaceCaseDetail; locale: Locale; onChange: (next: WorkspaceCaseDetail) => void }) {
  const t = labels[locale];
  const locked = detail.reviewStatus === "approved";
  const question = detail.callPlan.questions[0] ?? { id: "red-flag", prompt: "" };
  const updateCall = (change: Partial<WorkspaceCaseDetail["callPlan"]>) => onChange({ ...detail, callPlan: { ...detail.callPlan, ...change } });
  return <div className="content-editor">
    <label className="field-span checkbox-field"><input type="checkbox" checked={detail.dischargeVoiceNote.enabled} disabled={locked} onChange={(event) => onChange({ ...detail, dischargeVoiceNote: { ...detail.dischargeVoiceNote, enabled: event.target.checked } })} />{t.voice}</label>
    <label className="field-span"><textarea disabled={locked} value={detail.dischargeVoiceNote.script} onChange={(event) => onChange({ ...detail, dischargeVoiceNote: { ...detail.dischargeVoiceNote, script: event.target.value } })} /></label>
    <label className="field-span checkbox-field"><input type="checkbox" checked={detail.callPlan.enabled} disabled={locked} onChange={(event) => updateCall({ enabled: event.target.checked })} />{t.call}</label>
    <label>{t.opening}<textarea disabled={locked} value={detail.callPlan.openingScript} onChange={(event) => updateCall({ openingScript: event.target.value })} /></label>
    <label>{t.question}<textarea disabled={locked} value={question.prompt} onChange={(event) => updateCall({ questions: [{ ...question, prompt: event.target.value }] })} /></label>
    <label>{t.completion}<textarea disabled={locked} value={detail.callPlan.completionScript} onChange={(event) => updateCall({ completionScript: event.target.value })} /></label>
    <label>{t.transfer}<textarea disabled={locked} value={detail.callPlan.transferScript} onChange={(event) => updateCall({ transferScript: event.target.value })} /></label>
    <label>{t.team}<input disabled={locked} value={detail.callPlan.transferTarget} onChange={(event) => updateCall({ transferTarget: event.target.value })} /></label>
    <label>{t.responder}<input dir="ltr" disabled={locked} value={detail.callPlan.responderPhoneE164} onChange={(event) => updateCall({ responderPhoneE164: event.target.value.replace(/\s/g, "") })} /></label>
    <label className="delay-field"><span>{t.delay}</span><input type="number" min="0" max="168" disabled={locked} value={detail.callPlan.scheduledAfterHours} onChange={(event) => updateCall({ scheduledAfterHours: Number(event.target.value) })} /><span>{t.hours}</span></label>
  </div>;
}

function MedicationsTab({ detail, locale, onUpdate, onUpload, onAdd, onRemove }: { detail: WorkspaceCaseDetail; locale: Locale; onUpdate: (id: string, change: Partial<WorkspaceMedication>) => void; onUpload: (id: string, image: File) => Promise<void>; onAdd: () => void; onRemove: (id: string) => void }) {
  const t = labels[locale];
  const locked = detail.reviewStatus === "approved";
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  return <div className="medication-grid">
    {detail.medications.length === 0 && <div className="compact-empty">{t.noMedications}</div>}
    {detail.medications.map((item) => <article className="medication-editor" key={item.medicationId}>
      <div className="medicine-image"><span aria-hidden="true">▣</span></div>
      <div className="medication-fields">
        <label>{t.medicationName}<input disabled={locked} value={item.displayName} onChange={(event) => onUpdate(item.medicationId, { displayName: event.target.value })} /></label>
        <label>{t.dose}<input disabled={locked} value={item.doseInstruction} onChange={(event) => onUpdate(item.medicationId, { doseInstruction: event.target.value })} /></label>
        <label className="field-span">{t.reminder}<input disabled={locked} value={item.reminderScript} onChange={(event) => onUpdate(item.medicationId, { reminderScript: event.target.value })} /></label>
        <label className="checkbox-field"><input type="checkbox" disabled={locked} checked={item.dispensed} onChange={(event) => onUpdate(item.medicationId, { dispensed: event.target.checked, reminderEnabled: event.target.checked ? item.reminderEnabled : false })} />{t.dispensed}</label>
        <label className="checkbox-field"><input type="checkbox" disabled={locked || !item.dispensed} checked={item.reminderEnabled} onChange={(event) => onUpdate(item.medicationId, { reminderEnabled: event.target.checked })} />{t.enableReminder}</label>
        {item.reminderEnabled && <label className="field-span">{t.imageKey}<input disabled={locked} value={item.image?.objectKey ?? ""} onChange={(event) => onUpdate(item.medicationId, { image: event.target.value ? { source: "catalog", objectKey: event.target.value, reviewStatus: "pending" } : null })} /></label>}
        {item.image && <span className={`image-state image-state--${item.image.reviewStatus === "pending" ? "candidate" : item.image.reviewStatus}`}>{item.image.reviewStatus === "approved" ? t.approved : item.image.reviewStatus === "pending" ? t.pending : t.rejected}</span>}
      </div>
      <div className="medication-actions">{!locked && <label className="button medication-upload">{uploadingId === item.medicationId ? t.uploadingImage : t.uploadImage}<input type="file" accept="image/jpeg,image/png,image/webp" disabled={uploadingId !== null} onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; setUploadingId(item.medicationId); void onUpload(item.medicationId, file).finally(() => setUploadingId(null)); }} /></label>}{item.image?.reviewStatus === "pending" && !locked && <button className="button" onClick={() => onUpdate(item.medicationId, { image: { ...item.image!, reviewStatus: "approved" } })}>{t.approveImage}</button>}{!locked && <button className="button" onClick={() => onRemove(item.medicationId)}>{t.remove}</button>}</div>
    </article>)}
    {!locked && <button className="button medication-add" onClick={onAdd}>+ {t.addMedication}</button>}
  </div>;
}

function JourneyTab({ detail, locale }: { detail: WorkspaceCaseDetail; locale: Locale }) {
  if (detail.deliveryRuns.length === 0) return <div className="compact-empty">{locale === "ar" ? "تظهر خطوات الإرسال بعد الاعتماد." : "Delivery steps appear after approval."}</div>;
  return <ol className="journey-list">{detail.deliveryRuns.map((run) => <li key={run.id}><span /><div><b>{run.kind}</b><p>{run.status}</p></div><time>{new Date(run.scheduledAt).toLocaleString(locale === "ar" ? "ar-SA" : "en-US")}</time></li>)}</ol>;
}
