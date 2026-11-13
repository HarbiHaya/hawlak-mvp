import { useCallback, useEffect, useState } from "react";

import type { HawlakApi, WorkspaceAlert } from "../api";
import { ALERTS_CHANGED } from "../events";
import { Icon } from "../Icon";
import { displayError, formatDateTime, formatNumber, formatRelative, pick, type Locale } from "../i18n";
import { Badge, EmptyState, PageHeader, Segmented, useToast } from "../ui";
import { alertTypeLabel, answerKindLabel, t as texts } from "./text";

type AlertFilter = "open" | "resolved";

function alertDetail(alert: WorkspaceAlert, locale: Locale): string {
  if (alert.type === "medication_access") return alert.summary.split(": ").slice(1).join(": ");
  const kind = /Call escalation: (\w+)/.exec(alert.summary)?.[1];
  return kind ? pick(answerKindLabel, kind, locale) : alert.summary;
}

export function AlertsView({ api, locale, onOpenCase }: { api: HawlakApi; locale: Locale; onOpenCase: (caseId: string) => void }) {
  const t = texts[locale];
  const { notify } = useToast();
  const [alerts, setAlerts] = useState<WorkspaceAlert[] | null>(null);
  const [filter, setFilter] = useState<AlertFilter>("open");
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setAlerts((await api.listWorkspaceAlerts()).data); setError(null); }
    catch (caught) { setError(displayError(caught, locale)); }
  }, [api, locale]);
  useEffect(() => { void load(); }, [load]);

  async function resolve(alertId: string) {
    setResolving(alertId);
    try {
      await api.resolveWorkspaceAlert(alertId);
      setAlerts((items) => items?.map((item) => item.id === alertId ? { ...item, status: "resolved" } : item) ?? null);
      window.dispatchEvent(new Event(ALERTS_CHANGED));
      notify(t.resolvedToast);
    } catch (caught) { notify(displayError(caught, locale), "error"); }
    finally { setResolving(null); }
  }

  const open = alerts?.filter((item) => item.status === "open") ?? [];
  const resolved = alerts?.filter((item) => item.status === "resolved") ?? [];
  const visible = filter === "open" ? open : resolved;

  return <div className="page">
    <PageHeader title={t.alerts} actions={<button type="button" className="button" onClick={() => void load()}><Icon name="refresh" size={15} />{locale === "ar" ? "تحديث" : "Refresh"}</button>} />
    <div className="alerts-toolbar">
      <Segmented label={t.alerts} value={filter} onChange={setFilter} options={[
        { value: "open", label: <>{t.open}<span className={`count${open.length ? " count--danger" : ""}`}>{formatNumber(open.length, locale)}</span></> },
        { value: "resolved", label: <>{t.resolved}<span className="count">{formatNumber(resolved.length, locale)}</span></> },
      ]} />
    </div>
    {error && <div className="notice notice--danger" role="alert" style={{ marginBottom: 16 }}><Icon name="alert" size={16} /><div>{error}</div></div>}
    <section className="panel">
      {alerts === null && !error ? <div style={{ padding: 16, display: "grid", gap: 10 }} aria-hidden="true">{[0, 1].map((key) => <div key={key} className="skeleton" style={{ height: 44 }} />)}</div>
        : visible.length === 0 ? (filter === "open" ? <EmptyState icon="check-circle" title={t.noOpenAlerts}><p>{t.noAlertsHint}</p></EmptyState> : <EmptyState compact icon="bell" title={t.noResolved} />)
        : <ul className="rows">{visible.map((alert) => <li key={alert.id} className="row">
          <span className={`row__icon row__icon--${alert.status === "open" ? "danger" : "success"}`}><Icon name={alert.type === "medication_access" ? "pill" : "phone"} size={15} /></span>
          <div className="row__main">
            <b>{pick(alertTypeLabel, alert.type, locale)}{alertDetail(alert, locale) && <span style={{ fontWeight: 400 }}> — <bdi>{alertDetail(alert, locale)}</bdi></span>}</b>
            <small>{alert.patientName && <><bdi>{alert.patientName}</bdi> · </>}<time dateTime={alert.createdAt} title={formatDateTime(alert.createdAt, locale)}>{formatRelative(alert.createdAt, locale)}</time></small>
          </div>
          {alert.status === "resolved" && <Badge tone="success">{t.resolved}</Badge>}
          <button type="button" className="button button--sm button--ghost" onClick={() => onOpenCase(alert.caseId)}>{t.openCase}</button>
          {alert.status === "open" && <button type="button" className="button button--sm" disabled={resolving === alert.id} onClick={() => void resolve(alert.id)}><Icon name="check" size={14} />{t.resolve}</button>}
        </li>)}</ul>}
    </section>
  </div>;
}
