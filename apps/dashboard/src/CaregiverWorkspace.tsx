import { useEffect, useState, type FormEvent } from "react";

import { displayError, type Locale } from "./App";
import type { CaregiverCase, HawlakApi } from "./api";

const labels = {
  ar: {
    title: "متابعة حالة المريض", subtitle: "اطّلع على حالة الأدوية وموعد مكالمة المتابعة القادمة والتنبيهات المفتوحة.", caseId: "رقم الحالة",
    open: "عرض الحالة", loading: "جارٍ التحميل…", medications: "الأدوية", attention: "تتطلب متابعة", noAlerts: "لا توجد تنبيهات مفتوحة.",
    scheduled: "التذكير مُفعّل", needs_support: "يتطلب دعماً", empty: "أدخل رقم الحالة الذي زوّدك به المستشفى أو المريض.",
    nextCall: "مكالمة المتابعة القادمة", noCall: "لا توجد مكالمة متابعة مجدولة.", alertCount: "عدد التنبيهات المفتوحة", underReview: "خطة المتابعة قيد المراجعة لدى شركة التأمين. ستظهر الأدوية ومواعيد المكالمات بعد اعتمادها.",
  },
  en: {
    title: "Patient follow-up", subtitle: "View medication status, the next follow-up call and any open alerts.", caseId: "Case reference",
    open: "View case", loading: "Loading…", medications: "Medications", attention: "Requires attention", noAlerts: "There are no open alerts.",
    scheduled: "Reminder active", needs_support: "Support required", empty: "Enter the case reference provided by the hospital or the patient.",
    nextCall: "Next follow-up call", noCall: "No follow-up call is scheduled.", alertCount: "Open alerts", underReview: "The follow-up plan is under review by the insurer. Medications and call times will appear once it is approved.",
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
    <header className="page-title-block"><div><h1>{t.title}</h1><p>{t.subtitle}</p></div></header>
    <form className="caregiver-search" onSubmit={(event) => void load(event)}><label>{t.caseId}<input dir="ltr" value={caseId} onChange={(event) => setCaseId(event.target.value)} placeholder="case_..." /></label><button className="button button--primary" disabled={!caseId || busy}>{busy ? t.loading : t.open}</button></form>
    {error && <div className="notice notice--danger" role="alert">{error}</div>}
    {!data ? <section className="empty-panel"><span>♡</span><h2>{t.empty}</h2></section> : <div className="caregiver-card">
      <header><span className="avatar avatar--large">{data.patientName.slice(0, 1)}</span><div><h2>{data.patientName}</h2><p>{data.nextCallAt ? `${t.nextCall}: ${new Date(data.nextCallAt).toLocaleString(locale === "ar" ? "ar-SA" : "en-GB", { dateStyle: "medium", timeStyle: "short" })}` : t.noCall}</p></div></header>
      {data.journeyStatus === "draft" && <div className="notice notice--info" role="status">{t.underReview}</div>}
      {data.openAlertCount > 0 ? <section className="caregiver-alerts"><h3>{t.attention}</h3><article><span>!</span><div><b>{t.alertCount}: {data.openAlertCount.toLocaleString(locale === "ar" ? "ar-SA" : "en-US")}</b></div></article></section> : <div className="all-clear">✓ {t.noAlerts}</div>}
      <section className="caregiver-medications"><h3>{t.medications}</h3>{data.medications.map((item) => <article key={item.medicationId}><span className="medicine-thumb" aria-hidden="true">▣</span><div><b>{item.displayName}</b></div><i className={`dose-state dose-state--${item.status}`}>{t[item.status]}</i></article>)}</section>
    </div>}
  </div>;
}
