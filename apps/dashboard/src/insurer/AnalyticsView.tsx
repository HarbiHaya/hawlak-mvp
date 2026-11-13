import { useCallback, useEffect, useState, type MouseEvent, type ReactNode } from "react";

import type { HawlakApi, ProgrammeAnalytics } from "../api";
import { Icon } from "../Icon";
import { displayError, formatDate, formatNumber, formatTime, pick, type Bilingual, type Locale } from "../i18n";
import { Badge, EmptyState, Notice, PageHeader, Segmented } from "../ui";
import { alertTypeLabel, dialectLabel, languageLabel, photoCheckLabel, runKindLabel } from "./text";

type Period = "7" | "30" | "90";

const copy = {
  ar: {
    title: "تحليلات البرنامج", subtitle: "الحالات المسجّلة خلال آخر {n} يوماً. أعداد ومدد فقط، بلا بيانات مرضى.", period: "الفترة", days: "{n} يوماً", refresh: "تحديث", updated: "آخر تحديث {time}",
    demo: "وضع العرض مفعّل: خطوات الإرسال تُحاكى ولا تصل فعلياً، فأرقام الإرسال هنا ليست وصولاً حقيقياً.",
    nowTitle: "الوضع الآن", awaiting: "بانتظار المراجعة", longestWait: "أطول انتظار {t}", nothingWaiting: "لا شيء ينتظر",
    attention: "تتطلب إجراءً", highAlerts: "{n} تنبيه عالي الأولوية · أقدمها منذ {t}", noHighAlerts: "لا تنبيهات عالية الأولوية",
    active: "خطط متابعة نشطة", completed: "{n} خطة اكتملت", photosWaiting: "صور بانتظار المراجعة", lowAlerts: "{n} تنبيه للمراجعة",
    funnelTitle: "مسار الحالة", funnelNote: "النسبة من الحالات المسجّلة في الفترة.",
    reviewTitle: "المراجعة والاعتماد", medianApproval: "وسيط المدة من التسجيل إلى الاعتماد", within24: "اعتُمدت خلال ٢٤ ساعة", edited: "مسودات عدّلها المراجع قبل الاعتماد",
    aiDrafted: "مسودات صاغها نموذج الذكاء الاصطناعي", aiRejected: "مسودات رفضها فحص الحقائق فاستُخدمت القوالب",
    trendTitle: "الحالات يومياً", registeredPerDay: "سُجّلت", approvedPerDay: "اعتُمدت", peak: "الأعلى في يوم: {n}", table: "عرض الأرقام في جدول", date: "التاريخ",
    deliveryTitle: "الإرسال حسب القناة", step: "الخطوة", scheduled: "مجدولة", delivered: "أُرسلت", failed: "تعذّرت", rate: "نسبة الإرسال", simulated: "{n} خطوة تمت محاكاتها ولم تُرسل فعلياً.",
    callsTitle: "مكالمات المتابعة", callsDone: "اكتملت مع المريض", callsTransferred: "حُوّلت إلى فريق الرعاية", callsFailed: "لم تكتمل", callsPlaced: "أُجريت ولم تصل نتيجتها بعد", callsScheduled: "ما زالت مجدولة", escalation: "نسبة التحويل من المكالمات المُجابة",
    photosTitle: "صور علب الأدوية", boxes: "علب وصلت صورتها", firstMatch: "طابقت الخطة من أول قراءة", photosReview: "بانتظار مراجعة الصيدلي", reviewTime: "وسيط المدة حتى المراجعة",
    fromPatient: "من المريض", fromCaregiver: "من المرافق", byResult: "نتيجة الفحص الآلي", noPhotos: "لم تصل صور في هذه الفترة.",
    alertsTitle: "التنبيهات حسب النوع", type: "النوع", priority: "الأولوية", open: "مفتوحة", resolved: "عولجت", resolveTime: "وسيط مدة المعالجة", high: "عالية", low: "للمراجعة",
    medsTitle: "الأدوية والتواصل", medsTotal: "أدوية في الخطط", notDispensed: "لم تُصرف عند الخروج", reminders: "لها تذكير", times: "لها أوقات تذكير مختارة", strength: "لها تركيز مؤكد", languages: "لغة التواصل",
    notMeasured: "غير مقيس بعد: إعادة التنويم وزيارات الطوارئ خلال ٣٠ يوماً (تحتاج بيانات المطالبات لدى شركة التأمين)، والالتزام جرعةً بجرعة (ردود المريض تُستقبل لكنها غير مربوطة بجرعة محددة).",
    empty: "لا حالات مسجّلة في هذه الفترة", emptyHint: "اختر فترة أطول، أو سجّل حالة من مساحة المستشفى.", none: "—",
  },
  en: {
    title: "Programme analytics", subtitle: "Cases registered in the last {n} days. Counts and times only, no patient details.", period: "Period", days: "{n} days", refresh: "Refresh", updated: "Updated {time}",
    demo: "Demo mode is on: delivery steps are simulated and reach no one, so the delivery figures here are not real deliveries.",
    nowTitle: "Right now", awaiting: "Awaiting review", longestWait: "Longest wait {t}", nothingWaiting: "Nothing waiting",
    attention: "Needs action", highAlerts: "{n} high-priority alerts · oldest {t}", noHighAlerts: "No high-priority alerts",
    active: "Active follow-up plans", completed: "{n} plans completed", photosWaiting: "Photos awaiting review", lowAlerts: "{n} alerts for review",
    funnelTitle: "Case funnel", funnelNote: "Share of the cases registered in the period.",
    reviewTitle: "Review and approval", medianApproval: "Median time from registration to approval", within24: "Approved within 24 hours", edited: "Drafts the reviewer edited before approval",
    aiDrafted: "Drafts written by the AI model", aiRejected: "AI drafts rejected by the fact check (templates used)",
    trendTitle: "Cases per day", registeredPerDay: "Registered", approvedPerDay: "Approved", peak: "Busiest day: {n}", table: "Show the numbers as a table", date: "Date",
    deliveryTitle: "Delivery by channel", step: "Step", scheduled: "Scheduled", delivered: "Delivered", failed: "Failed", rate: "Delivery rate", simulated: "{n} steps were simulated and not actually sent.",
    callsTitle: "Follow-up calls", callsDone: "Completed with the patient", callsTransferred: "Transferred to the care team", callsFailed: "Not completed", callsPlaced: "Placed, outcome not reported yet", callsScheduled: "Still scheduled", escalation: "Share of answered calls transferred",
    photosTitle: "Medicine-box photos", boxes: "Boxes with a photo", firstMatch: "Matched the plan on first read", photosReview: "Awaiting pharmacist review", reviewTime: "Median time to review",
    fromPatient: "From the patient", fromCaregiver: "From the caregiver", byResult: "Automatic check result", noPhotos: "No photos arrived in this period.",
    alertsTitle: "Alerts by type", type: "Type", priority: "Priority", open: "Open", resolved: "Resolved", resolveTime: "Median time to resolve", high: "High", low: "For review",
    medsTitle: "Medicines and reach", medsTotal: "Medicines in plans", notDispensed: "Not dispensed at discharge", reminders: "With a reminder", times: "With chosen reminder times", strength: "With a confirmed strength", languages: "Communication language",
    notMeasured: "Not measured yet: 30-day readmissions and emergency visits (they need the insurer's claims data), and dose-by-dose adherence (patient replies arrive but are not linked to a dose).",
    empty: "No cases registered in this period", emptyHint: "Choose a longer period, or register a case from the hospital workspace.", none: "—",
  },
} as const;

const funnelLabel: Record<string, Bilingual> = {
  registered: { ar: "سُجّلت من المستشفى", en: "Registered by the hospital" },
  eligible: { ar: "تأكدت التغطية", en: "Coverage confirmed" },
  approved: { ar: "اعتُمدت خطة المتابعة", en: "Follow-up plan approved" },
  contacted: { ar: "أُرسلت أول رسالة أو مكالمة", en: "First message or call delivered" },
  photos_received: { ar: "وصلت صور كل العلب", en: "All box photos received" },
  call_completed: { ar: "أُجيبت مكالمة المتابعة", en: "Follow-up call answered" },
};

const intl = (locale: Locale) => (locale === "ar" ? "ar-SA" : "en-GB");
const percent = (value: number | null, locale: Locale) => value === null ? "—" : (value / 100).toLocaleString(intl(locale), { style: "percent" });
function duration(hours: number | null, locale: Locale): string {
  if (hours === null) return "—";
  const [value, unit] = hours < 1 ? [Math.max(1, Math.round(hours * 60)), "minute"] : hours < 48 ? [hours, "hour"] : [hours / 24, "day"];
  return new Intl.NumberFormat(intl(locale), { style: "unit", unit, unitDisplay: "short", maximumFractionDigits: 1 }).format(value);
}

interface Meter { label: string; value: number; of: number; showTotal?: boolean }

/** One named bar per row on a shared baseline, with its figure beside it. */
function Meters({ rows, locale }: { rows: Meter[]; locale: Locale }) {
  return <ul className="meters">{rows.map((row) => {
    const share = row.of ? Math.round((100 * row.value) / row.of) : 0;
    return <li key={row.label}>
      <span className="meters__label">{row.label}</span>
      <span className="meters__track" aria-hidden="true"><i style={{ inlineSize: `${share}%` }} /></span>
      <span className="meters__figure"><b>{formatNumber(row.value, locale)}</b>{row.showTotal ? <small>/ {formatNumber(row.of, locale)}</small> : row.of > 0 && <small>{percent(share, locale)}</small>}</span>
    </li>;
  })}</ul>;
}

function Stats({ rows }: { rows: Array<[string, ReactNode]> }) {
  return <dl className="stats">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

/** Daily columns for one series. Each column carries its date and value as a tooltip. */
function Columns({ title, points, max, locale }: { title: string; points: Array<{ date: string; value: number }>; max: number; locale: Locale }) {
  const total = points.reduce((sum, point) => sum + point.value, 0);
  return <figure className="columns">
    <figcaption><b>{title}</b><span>{formatNumber(total, locale)}</span></figcaption>
    <div className="columns__plot" role="img" aria-label={`${title}: ${formatNumber(total, locale)}`}>
      {points.map((point) => <span key={point.date} className="columns__col" title={`${formatDate(point.date, locale)}: ${formatNumber(point.value, locale)}`}><i style={{ blockSize: `${(100 * point.value) / max}%` }} /></span>)}
    </div>
    <div className="columns__axis"><span>{formatDate(points[0].date, locale)}</span><span>{formatDate(points[points.length - 1].date, locale)}</span></div>
  </figure>;
}

export function AnalyticsView({ api, locale, casesPath, alertsPath, navigate }: { api: HawlakApi; locale: Locale; casesPath: string; alertsPath: string; navigate: (path: string) => void }) {
  const t = copy[locale];
  const [period, setPeriod] = useState<Period>("30");
  const [data, setData] = useState<ProgrammeAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try { setData(await api.getAnalytics(Number(period))); setError(null); }
    catch (caught) { setError(displayError(caught, locale)); }
    finally { setBusy(false); }
  }, [api, locale, period]);
  useEffect(() => { void load(); }, [load]);

  const go = (path: string) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault(); navigate(path);
  };
  const n = (value: number) => formatNumber(value, locale);
  const header = <PageHeader title={t.title} description={t.subtitle.replace("{n}", n(Number(period)))} actions={<>
    <Segmented label={t.period} value={period} onChange={setPeriod} options={(["7", "30", "90"] as const).map((value) => ({ value, label: t.days.replace("{n}", n(Number(value))) }))} />
    <button type="button" className="button" disabled={busy} onClick={() => void load()}><Icon name="refresh" size={15} />{t.refresh}</button>
  </>} />;

  if (!data) return <div className="page">{header}
    {error ? <Notice tone="danger">{error}</Notice> : <div style={{ display: "grid", gap: 16 }} aria-hidden="true"><div className="skeleton" style={{ height: 96 }} /><div className="skeleton" style={{ height: 260 }} /></div>}
  </div>;

  const { now, review, calls, photos, medications } = data;
  const registered = data.funnel[0]?.count ?? 0;
  const peak = Math.max(1, ...data.daily.map((day) => Math.max(day.registered, day.approved)));
  const simulated = data.delivery.reduce((sum, row) => sum + row.simulated, 0);
  const photoRows = Object.entries(photos.byStatus).filter(([, count]) => count > 0);
  const languages = Object.entries(data.languages).map(([code, count]) => `${pick(languageLabel, code, locale)} ${n(count)}`);
  const dialects = Object.entries(data.dialects).map(([code, count]) => `${pick(dialectLabel, code, locale)} ${n(count)}`);

  return <div className="page" aria-busy={busy}>
    {header}
    {error && <div style={{ marginBottom: 16 }}><Notice tone="danger">{error}</Notice></div>}
    {data.deliveryMode === "mock" && <div style={{ marginBottom: 16 }}><Notice tone="info">{t.demo}</Notice></div>}

    <section className="panel metrics metrics--4" aria-label={t.nowTitle}>
      <a className="metric" href={casesPath} onClick={go(casesPath)}><span>{t.awaiting}</span><b>{n(now.awaitingReview)}</b><small>{now.oldestWaitingHours === null ? t.nothingWaiting : t.longestWait.replace("{t}", duration(now.oldestWaitingHours, locale))}</small></a>
      <a className="metric" href={alertsPath} onClick={go(alertsPath)}><span>{t.attention}</span><b className={now.needsAttention ? "is-danger" : undefined}>{n(now.needsAttention)}</b><small>{now.openAlerts.high ? t.highAlerts.replace("{n}", n(now.openAlerts.high)).replace("{t}", duration(now.oldestOpenAlertHours, locale)) : t.noHighAlerts}</small></a>
      <a className="metric" href={casesPath} onClick={go(casesPath)}><span>{t.active}</span><b>{n(now.activeJourneys)}</b><small>{t.completed.replace("{n}", n(now.completedJourneys))}</small></a>
      <a className="metric" href={casesPath} onClick={go(casesPath)}><span>{t.photosWaiting}</span><b>{n(now.photosAwaitingReview)}</b><small>{t.lowAlerts.replace("{n}", n(now.openAlerts.low))}</small></a>
    </section>

    {registered === 0 ? <section className="panel"><EmptyState icon="chart" title={t.empty}><p>{t.emptyHint}</p></EmptyState></section> : <div className="analytics-grid">
      <section className="panel">
        <header className="panel__header"><h2>{t.funnelTitle}</h2></header>
        <Meters locale={locale} rows={data.funnel.map((row) => ({ label: pick(funnelLabel, row.stage, locale), value: row.count, of: registered }))} />
        <p className="panel__note">{t.funnelNote}</p>
      </section>

      <section className="panel">
        <header className="panel__header"><h2>{t.reviewTitle}</h2></header>
        <Stats rows={[
          [t.medianApproval, duration(review.medianHoursToApproval, locale)],
          [t.within24, percent(review.approvedWithin24hPct, locale)],
          [t.edited, percent(review.draftEditedPct, locale)],
          [t.aiDrafted, percent(review.aiDraftPct, locale)],
          [t.aiRejected, n(review.aiDraftRejected)],
        ]} />
      </section>

      <section className="panel analytics-grid__wide">
        <header className="panel__header"><h2>{t.trendTitle}</h2><span className="updated">{t.peak.replace("{n}", n(peak))}</span></header>
        <div className="columns-pair">
          <Columns title={t.registeredPerDay} max={peak} locale={locale} points={data.daily.map((day) => ({ date: day.date, value: day.registered }))} />
          <Columns title={t.approvedPerDay} max={peak} locale={locale} points={data.daily.map((day) => ({ date: day.date, value: day.approved }))} />
        </div>
        <details className="data-table"><summary>{t.table}</summary>
          <table className="table"><thead><tr><th scope="col">{t.date}</th><th scope="col">{t.registeredPerDay}</th><th scope="col">{t.approvedPerDay}</th></tr></thead>
            <tbody>{data.daily.filter((day) => day.registered || day.approved).map((day) => <tr key={day.date}><th scope="row">{formatDate(day.date, locale)}</th><td>{n(day.registered)}</td><td>{n(day.approved)}</td></tr>)}</tbody></table>
        </details>
      </section>

      <section className="panel analytics-grid__wide">
        <header className="panel__header"><h2>{t.deliveryTitle}</h2></header>
        <div className="table-scroll"><table className="table">
          <thead><tr><th scope="col">{t.step}</th><th scope="col">{t.scheduled}</th><th scope="col">{t.delivered}</th><th scope="col">{t.failed}</th><th scope="col">{t.rate}</th></tr></thead>
          <tbody>{data.delivery.map((row) => <tr key={row.kind}><th scope="row">{pick(runKindLabel, row.kind, locale)}</th><td>{n(row.scheduled)}</td><td>{n(row.delivered)}</td><td className={row.failed ? "is-danger" : undefined}>{n(row.failed)}</td><td>{percent(row.successPct, locale)}</td></tr>)}</tbody>
        </table></div>
        {simulated > 0 && <p className="panel__note">{t.simulated.replace("{n}", n(simulated))}</p>}
      </section>

      <section className="panel">
        <header className="panel__header"><h2>{t.callsTitle}</h2></header>
        <Stats rows={[
          [t.callsDone, n(calls.completed)],
          [t.callsTransferred, n(calls.transferred)],
          [t.callsFailed, n(calls.failed)],
          [t.callsPlaced, n(calls.awaitingOutcome)],
          [t.callsScheduled, n(calls.scheduled)],
          [t.escalation, percent(calls.escalationPct, locale)],
        ]} />
      </section>

      <section className="panel">
        <header className="panel__header"><h2>{t.medsTitle}</h2></header>
        <Stats rows={[
          [t.medsTotal, n(medications.total)],
          [t.notDispensed, n(medications.notDispensed)],
          [t.reminders, n(medications.remindersEnabled)],
          [t.times, n(medications.withReminderTimes)],
          [t.strength, n(medications.withConfirmedStrength)],
          [t.languages, <>{languages.join(locale === "ar" ? "، " : ", ")}{dialects.length > 0 && <small> ({dialects.join(locale === "ar" ? "، " : ", ")})</small>}</>],
        ]} />
      </section>

      <section className="panel">
        <header className="panel__header"><h2>{t.photosTitle}</h2></header>
        <Meters locale={locale} rows={[{ label: t.boxes, value: photos.boxesWithPhoto, of: photos.boxesExpected, showTotal: true }]} />
        <Stats rows={[
          [t.firstMatch, percent(photos.firstReadMatchPct, locale)],
          [t.photosReview, n(photos.awaitingReview)],
          [t.reviewTime, duration(photos.medianHoursToReview, locale)],
          [t.fromPatient, n(photos.bySender.patient ?? 0)],
          [t.fromCaregiver, n(photos.bySender.caregiver ?? 0)],
        ]} />
        {photoRows.length === 0 ? <p className="panel__note">{t.noPhotos}</p> : <>
          <h3 className="panel__subhead">{t.byResult}</h3>
          <Meters locale={locale} rows={photoRows.map(([status, count]) => ({ label: pick(photoCheckLabel, status, locale), value: count, of: photos.total }))} />
        </>}
      </section>

      <section className="panel">
        <header className="panel__header"><h2>{t.alertsTitle}</h2></header>
        <div className="table-scroll"><table className="table">
          <thead><tr><th scope="col">{t.type}</th><th scope="col">{t.open}</th><th scope="col">{t.resolved}</th><th scope="col">{t.resolveTime}</th></tr></thead>
          <tbody>{data.alerts.map((row) => <tr key={row.type}>
            <th scope="row">{pick(alertTypeLabel, row.type, locale)}{row.severity && <> <Badge tone={row.severity === "high" ? "danger" : "neutral"} plain>{row.severity === "high" ? t.high : t.low}</Badge></>}</th>
            <td className={row.open && row.severity === "high" ? "is-danger" : undefined}>{n(row.open)}</td><td>{n(row.resolved)}</td><td>{duration(row.medianHoursToResolve, locale)}</td>
          </tr>)}</tbody>
        </table></div>
      </section>
    </div>}

    <p className="analytics-foot"><span>{t.notMeasured}</span><span className="updated">{t.updated.replace("{time}", formatTime(data.generatedAt, locale))}</span></p>
  </div>;
}
