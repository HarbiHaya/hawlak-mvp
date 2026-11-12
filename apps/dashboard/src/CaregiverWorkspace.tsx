import { useEffect, useState, type FormEvent } from "react";

import { displayError, type Locale } from "./App";
import type { CaregiverCase, HawlakApi } from "./api";

const labels = {
  ar: {
    title: "متابعة أحد أفراد العائلة", subtitle: "حالة المتابعة والتنبيهات فقط. لا يمكن تغيير الخطة.", caseId: "رقم الحالة",
    open: "فتح المتابعة", medications: "الأدوية", attention: "تحتاج متابعة", noAlerts: "لا توجد تنبيهات مفتوحة",
    scheduled: "مجدول", needs_support: "يحتاج مساعدة", empty: "أدخل رقم الحالة الذي شاركه المريض معك.",
    nextCall: "مكالمة المتابعة", noCall: "لا توجد مكالمة مجدولة", alertCount: "تنبيهات مفتوحة",
  },
  en: {
    title: "Family follow-up", subtitle: "Follow-up status and alerts only. The plan cannot be changed here.", caseId: "Case ID",
    open: "Open follow-up", medications: "Medications", attention: "Needs attention", noAlerts: "No open alerts",
    scheduled: "Scheduled", needs_support: "Needs support", empty: "Enter the case ID shared with you by the patient.",
    nextCall: "Follow-up call", noCall: "No call scheduled", alertCount: "open alerts",
  },
} as const;

export function CaregiverWorkspace({ api, locale }: { api: HawlakApi; locale: Locale }) {
  const t = labels[locale];
  const [caseId, setCaseId] = useState("");
  const [data, setData] = useState<CaregiverCase | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(event?: FormEvent) {
    event?.preventDefault();
    if (!caseId) return;
    setBusy(true); setError(null);
    try { setData(await api.getCaregiverCase(caseId)); }
    catch (caught) { setError(displayError(caught, locale)); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (!data) return;
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [data, caseId]);

  return <div className="workspace caregiver-workspace">
    <header className="page-header"><span>{locale === "ar" ? "مقدم الرعاية" : "Caregiver"}</span><h1>{t.title}</h1><p>{t.subtitle}</p></header>
    <form className="caregiver-search" onSubmit={(event) => void load(event)}><label>{t.caseId}<input dir="ltr" value={caseId} onChange={(event) => setCaseId(event.target.value)} placeholder="case_..." /></label><button className="button button--primary" disabled={!caseId || busy}>{busy ? "…" : t.open}</button></form>
    {error && <div className="notice notice--danger" role="alert">{error}</div>}
    {!data ? <section className="empty-panel"><span>♡</span><h2>{t.empty}</h2></section> : <div className="caregiver-card">
      <header><span className="avatar avatar--large">{data.patientName.slice(0, 1)}</span><div><h2>{data.patientName}</h2><p>{data.nextCallAt ? `${t.nextCall}: ${new Date(data.nextCallAt).toLocaleString(locale === "ar" ? "ar-SA" : "en-US")}` : t.noCall}</p></div></header>
      {data.openAlertCount > 0 ? <section className="caregiver-alerts"><h3>{t.attention}</h3><article><span>!</span><div><b>{data.openAlertCount} {t.alertCount}</b></div></article></section> : <div className="all-clear">✓ {t.noAlerts}</div>}
      <section className="caregiver-medications"><h3>{t.medications}</h3>{data.medications.map((item) => <article key={item.medicationId}><span className="medicine-thumb" aria-hidden="true">▣</span><div><b>{item.displayName}</b></div><i className={`dose-state dose-state--${item.status}`}>{t[item.status]}</i></article>)}</section>
    </div>}
  </div>;
}
