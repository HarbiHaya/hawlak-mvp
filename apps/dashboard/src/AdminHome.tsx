import { useCallback, useEffect, useState, type MouseEvent } from "react";

import type { HawlakApi, WorkspaceAlert, WorkspaceCaseSummary } from "./api";
import { Icon } from "./Icon";
import { displayError, formatNumber, formatRelative, pick, type Locale } from "./i18n";
import { alertTypeLabel } from "./insurer/text";
import { viewPath, type UserRole } from "./routing";
import { Badge, EmptyState, Notice, PageHeader } from "./ui";

const copy = {
  ar: {
    title: "نظرة عامة", awaiting: "بانتظار المراجعة", approved: "خطط معتمدة", alerts: "تنبيهات مفتوحة",
    queue: "بانتظار المراجعة", alertsTitle: "تنبيهات مفتوحة", viewAll: "عرض الكل", registerCase: "تسجيل حالة", reviewCases: "مراجعة الحالات",
    noDrafts: "لا توجد حالات بانتظار المراجعة.", noAlerts: "لا توجد تنبيهات مفتوحة.", openCase: "فتح", draft: "بانتظار المراجعة", alertsCount: "{n} تنبيه",
    caregiverView: "عرض مرافق المريض",
  },
  en: {
    title: "Overview", awaiting: "Awaiting review", approved: "Approved plans", alerts: "Open alerts",
    queue: "Awaiting review", alertsTitle: "Open alerts", viewAll: "View all", registerCase: "Register case", reviewCases: "Review cases",
    noDrafts: "No cases are awaiting review.", noAlerts: "No open alerts.", openCase: "Open", draft: "Awaiting review", alertsCount: "{n} alerts",
    caregiverView: "Caregiver view",
  },
} as const;

/** Admin landing page: live operational state across workspaces, built only from API data. */
export function AdminHome({ api, locale, role, navigate }: { api: HawlakApi; locale: Locale; role: UserRole; navigate: (path: string) => void }) {
  const t = copy[locale];
  const [cases, setCases] = useState<WorkspaceCaseSummary[] | null>(null);
  const [alerts, setAlerts] = useState<WorkspaceAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const casesPath = viewPath(role, "insurer", "cases") ?? "/admin/insurer/cases";
  const alertsPath = viewPath(role, "insurer", "alerts") ?? "/admin/insurer/alerts";
  const hospitalPath = viewPath(role, "hospital") ?? "/admin/hospital";

  const load = useCallback(async () => {
    try {
      const [caseResult, alertResult] = await Promise.all([api.listWorkspaceCases(), api.listWorkspaceAlerts()]);
      setCases(caseResult.data); setAlerts(alertResult.data); setError(null);
    } catch (caught) { setError(displayError(caught, locale)); }
  }, [api, locale]);
  useEffect(() => { void load(); }, [load]);

  const go = (path: string) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault(); navigate(path);
  };
  const drafts = cases?.filter((item) => item.reviewStatus === "draft") ?? [];
  const openAlerts = alerts?.filter((item) => item.status === "open") ?? [];
  const loading = cases === null && !error;
  const metric = (value: number | undefined, danger = false) => loading ? <span className="skeleton" style={{ display: "block", height: 34, width: 48 }} /> : <b className={danger && value ? "is-danger" : undefined}>{formatNumber(value ?? 0, locale)}</b>;

  return <div className="page">
    <PageHeader title={t.title} actions={<>
      <a className="button" href={hospitalPath} onClick={go(hospitalPath)}><Icon name="file-plus-2" size={16} />{t.registerCase}</a>
      <a className="button button--primary" href={casesPath} onClick={go(casesPath)}>{t.reviewCases}</a>
    </>} />
    {error && <div style={{ marginBottom: 16 }}><Notice tone="danger">{error}</Notice></div>}
    <section className="panel metrics" aria-label={t.title}>
      <a className="metric" href={casesPath} onClick={go(casesPath)}><span>{t.awaiting}</span>{metric(cases ? drafts.length : undefined)}</a>
      <a className="metric" href={casesPath} onClick={go(casesPath)}><span>{t.approved}</span>{metric(cases ? cases.length - drafts.length : undefined)}</a>
      <a className="metric" href={alertsPath} onClick={go(alertsPath)}><span>{t.alerts}</span>{metric(alerts ? openAlerts.length : undefined, true)}</a>
    </section>
    <div className="overview-grid">
      <section className="panel">
        <header className="panel__header"><h2>{t.queue}</h2><a className="button button--link" href={casesPath} onClick={go(casesPath)}>{t.viewAll}</a></header>
        {loading ? <div style={{ padding: 16 }}><div className="skeleton" style={{ height: 96 }} /></div>
          : drafts.length === 0 ? <EmptyState compact icon="check-circle" title={t.noDrafts} />
          : <ul className="rows">{drafts.slice(0, 6).map((item) => {
            const path = `${casesPath}?case=${encodeURIComponent(item.caseId)}`;
            return <li key={item.caseId}><a className="row" href={path} onClick={go(path)}>
              <div className="row__main"><b>{item.patientName}</b><small className="mono" dir="ltr" style={{ justifySelf: "start" }}>{item.caseId}</small></div>
              {item.alertCount > 0 && <Badge tone="danger">{t.alertsCount.replace("{n}", formatNumber(item.alertCount, locale))}</Badge>}
              <Badge tone="warning">{t.draft}</Badge>
              <Icon name="arrow" size={16} />
            </a></li>;
          })}</ul>}
      </section>
      <section className="panel">
        <header className="panel__header"><h2>{t.alertsTitle}</h2><a className="button button--link" href={alertsPath} onClick={go(alertsPath)}>{t.viewAll}</a></header>
        {loading ? <div style={{ padding: 16 }}><div className="skeleton" style={{ height: 96 }} /></div>
          : openAlerts.length === 0 ? <EmptyState compact icon="check-circle" title={t.noAlerts} />
          : <ul className="rows">{openAlerts.slice(0, 6).map((alert) => {
            const path = `${casesPath}?case=${encodeURIComponent(alert.caseId)}`;
            return <li key={alert.id}><a className="row" href={path} onClick={go(path)}>
              <span className="row__icon row__icon--danger"><Icon name={alert.type === "medication_access" ? "pill" : "phone"} size={15} /></span>
              <div className="row__main"><b>{pick(alertTypeLabel, alert.type, locale)}</b><small>{alert.patientName && <><bdi>{alert.patientName}</bdi> · </>}{formatRelative(alert.createdAt, locale)}</small></div>
            </a></li>;
          })}</ul>}
      </section>
    </div>
  </div>;
}
