import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { Icon } from "./Icon";
import type { CaregiverCase, HawlakApi } from "./api";
import { displayError, formatDateTime, formatNumber, formatTime, type Locale } from "./i18n";
import { queryParam, replaceQueryParam } from "./routing";
import { Badge, EmptyState, Field, Notice, PageHeader } from "./ui";

const labels = {
  ar: {
    title: "متابعة الحالة", caseId: "رقم الحالة", caseHint: "زوّدك به المستشفى عند الخروج.", open: "عرض", loading: "جارٍ التحميل…",
    medications: "الأدوية", status: "حالة الخطة", nextCall: "المكالمة القادمة", alerts: "تنبيهات مفتوحة",
    approved: "معتمدة", underReview: "قيد المراجعة", noCall: "لا توجد", none: "لا توجد",
    scheduled: "التذكير مفعّل", needs_support: "يتطلب دعماً", reviewNotice: "خطة المتابعة قيد المراجعة لدى شركة التأمين. تظهر مواعيد التذكيرات والمكالمات بعد اعتمادها.",
    alertNotice: "يتابع فريق الرعاية {n} تنبيه مفتوح لهذه الحالة.", empty: "أدخل رقم الحالة", emptyHint: "تظهر هنا حالة الأدوية والمكالمة القادمة والتنبيهات.",
    noMeds: "لا توجد أدوية في الخطة.", updated: "آخر تحديث {time}", refresh: "تحديث", change: "حالة أخرى",
    photosHint: "أرسل صورة لكل علبة دواء من رقمك المسجّل على واتساب حولك، أو ارفعها من هنا إذا لم تصل صورة المريض أو كانت غير واضحة. يراجعها الصيدلي.",
    upload: "رفع صورة العلبة", uploading: "جارٍ الرفع…", uploaded: "وصلت الصورة، شكراً. يراجعها الصيدلي.", unclear: "الصورة غير واضحة. صوّر الاسم المكتوب على العلبة مرة ثانية.",
    photo_missing: "لم تصل صورة", photo_received: "وصلت الصورة", photo_needs_attention: "يراجعها الصيدلي", photo_confirmed: "أكّدها الصيدلي",
  },
  en: {
    title: "Patient follow-up", caseId: "Case reference", caseHint: "Provided by the hospital at discharge.", open: "View", loading: "Loading…",
    medications: "Medications", status: "Plan status", nextCall: "Next call", alerts: "Open alerts",
    approved: "Approved", underReview: "Under review", noCall: "None scheduled", none: "None",
    scheduled: "Reminder active", needs_support: "Support required", reviewNotice: "The follow-up plan is under review by the insurer. Reminder and call times appear once it is approved.",
    alertNotice: "The care team is following up on {n} open alerts for this case.", empty: "Enter a case reference", emptyHint: "Medication status, the next call and alerts appear here.",
    noMeds: "No medications in the plan.", updated: "Updated {time}", refresh: "Refresh", change: "Another case",
    photosHint: "Send a photo of each medicine box from your registered number to Hawlak on WhatsApp, or upload it here if the patient's photo did not arrive or was unclear. A pharmacist reviews them.",
    upload: "Upload box photo", uploading: "Uploading…", uploaded: "Photo received, thank you. A pharmacist will review it.", unclear: "The photo is not clear. Photograph the name printed on the box again.",
    photo_missing: "No photo yet", photo_received: "Photo received", photo_needs_attention: "Pharmacist reviewing", photo_confirmed: "Confirmed by pharmacist",
  },
} as const;

const LAST_CASE_KEY = "hawlak.caregiver.case";

function rememberedCase(): string {
  const fromUrl = queryParam("case");
  if (fromUrl) return fromUrl;
  try { return localStorage.getItem(LAST_CASE_KEY) ?? ""; } catch { return ""; }
}

export function CaregiverWorkspace({ api, locale }: { api: HawlakApi; locale: Locale }) {
  const t = labels[locale];
  const [caseId, setCaseId] = useState(rememberedCase);
  const [data, setData] = useState<CaregiverCase | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const activeId = useRef<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [photoNotice, setPhotoNotice] = useState<"uploaded" | "unclear" | null>(null);

  const load = useCallback(async (id: string, quiet = false) => {
    const reference = id.trim();
    if (!reference) return;
    if (!quiet) { setBusy(true); setError(null); }
    try {
      const result = await api.getCaregiverCase(reference);
      activeId.current = reference;
      setData(result); setUpdatedAt(new Date()); setError(null);
      replaceQueryParam("case", reference);
      try { localStorage.setItem(LAST_CASE_KEY, reference); } catch { /* per-viewer convenience only */ }
    } catch (caught) {
      if (!quiet) { setData(null); setError(displayError(caught, locale)); }
    } finally { if (!quiet) setBusy(false); }
  }, [api, locale]);

  // Reopen the last viewed case (or the ?case= link) without retyping it.
  useEffect(() => { if (caseId) void load(caseId); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Refresh quietly while a case is open.
  useEffect(() => {
    if (!data) return;
    const timer = window.setInterval(() => { if (activeId.current) void load(activeId.current, true); }, 30_000);
    return () => window.clearInterval(timer);
  }, [data, load]);

  // The registered caregiver sends a box photo the patient did not send, or sent unclear.
  async function upload(medicationId: string, photo: File | undefined) {
    if (!photo || !data) return;
    setUploading(medicationId); setError(null); setPhotoNotice(null);
    try {
      const { result } = await api.uploadCaregiverPhoto(data.caseId, medicationId, photo);
      setPhotoNotice(result === "unclear" ? "unclear" : "uploaded");
      await load(data.caseId, true);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setUploading(null); }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(caseId);
  }

  const approved = data?.journeyStatus === "approved";

  return <div className="page page--narrow">
    <PageHeader title={t.title} actions={data && <button type="button" className="button" disabled={busy} onClick={() => void load(data.caseId)}><Icon name="refresh" size={15} />{t.refresh}</button>} />
    <form className="lookup" onSubmit={submit}>
      <Field label={t.caseId} hint={t.caseHint}>{({ id, describedBy }) => <input id={id} className="input mono" dir="ltr" autoComplete="off" spellCheck={false} value={caseId} aria-describedby={describedBy} onChange={(event) => setCaseId(event.target.value.trim())} placeholder="case_…" />}</Field>
      <button className="button button--primary" disabled={!caseId || busy}>{busy ? t.loading : t.open}</button>
    </form>
    {error && <div style={{ marginBottom: 16 }}><Notice tone="danger">{error}</Notice></div>}
    {!data ? !error && <section className="panel"><EmptyState icon="heart-handshake" title={t.empty}><p>{t.emptyHint}</p></EmptyState></section> : <div style={{ display: "grid", gap: 16 }}>
      <section className="panel">
        <header className="panel__header"><h2 style={{ fontSize: 16 }}>{data.patientName}</h2>{updatedAt && <span className="updated">{t.updated.replace("{time}", formatTime(updatedAt, locale))}</span>}</header>
        <div className="status-hero">
          <div><span>{t.status}</span><b><Badge tone={approved ? "success" : "warning"}>{approved ? t.approved : t.underReview}</Badge></b></div>
          <div><span>{t.nextCall}</span><b>{data.nextCallAt ? <bdi>{formatDateTime(data.nextCallAt, locale)}</bdi> : <span className="muted">{t.noCall}</span>}</b></div>
          <div><span>{t.alerts}</span><b style={data.openAlertCount ? { color: "var(--danger)" } : undefined}>{data.openAlertCount ? formatNumber(data.openAlertCount, locale) : <span className="muted">{t.none}</span>}</b></div>
        </div>
      </section>
      {!approved && <Notice tone="info">{t.reviewNotice}</Notice>}
      {data.openAlertCount > 0 && <Notice tone="warning">{t.alertNotice.replace("{n}", formatNumber(data.openAlertCount, locale))}</Notice>}
      <section className="panel">
        <header className="panel__header"><h2>{t.medications}</h2></header>
        {data.medications.length === 0 ? <EmptyState compact icon="pill" title={t.noMeds} />
          : <ul className="rows">{data.medications.map((item) => <li key={item.medicationId} className="row">
            <span className="row__icon"><Icon name="pill" size={15} /></span>
            <div className="row__main"><b>{item.displayName}</b>{item.photoStatus && <small className={`photo-state photo-state--${item.photoStatus}`}>{t[`photo_${item.photoStatus}`]}</small>}</div>
            {item.canUploadPhoto && <label className="button button--sm file-button" aria-disabled={uploading !== null}><Icon name="upload" size={14} />{uploading === item.medicationId ? t.uploading : t.upload}<input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" disabled={uploading !== null} onChange={(event) => { void upload(item.medicationId, event.target.files?.[0]); event.target.value = ""; }} /></label>}
            {approved && <Badge tone={item.status === "scheduled" ? "success" : "warning"}>{t[item.status]}</Badge>}
          </li>)}</ul>}
        {photoNotice && <div style={{ padding: "0 16px 12px" }}><Notice tone={photoNotice === "unclear" ? "warning" : "success"}>{t[photoNotice]}</Notice></div>}
        {approved && data.medications.length > 0 && <p className="photo-hint">{t.photosHint}</p>}
      </section>
    </div>}
  </div>;
}
