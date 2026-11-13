import { useEffect, useRef } from "react";

import type { WorkspaceCaseSummary } from "../api";
import { Icon } from "../Icon";
import { formatNumber, formatRelative, formatShort, type Locale } from "../i18n";
import { Badge, Segmented } from "../ui";
import { t as texts } from "./text";

export type QueueFilter = "review" | "approved" | "all";

export function CaseQueue({ cases, locale, filter, onFilter, query, onQuery, selectedId, onSelect }: {
  cases: WorkspaceCaseSummary[] | null; locale: Locale; filter: QueueFilter; onFilter: (filter: QueueFilter) => void;
  query: string; onQuery: (query: string) => void; selectedId: string | null; onSelect: (caseId: string) => void;
}) {
  const t = texts[locale];
  const listRef = useRef<HTMLUListElement>(null);
  // Keep the open case visible in the queue, e.g. after following a deep link.
  useEffect(() => { listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" }); }, [selectedId, filter, cases]);
  const list = cases ?? [];
  const counts = { review: list.filter((item) => item.reviewStatus === "draft").length, approved: list.filter((item) => item.reviewStatus === "approved").length, all: list.length };
  const needle = query.trim().toLocaleLowerCase();
  const visible = list
    .filter((item) => filter === "all" || (filter === "review" ? item.reviewStatus === "draft" : item.reviewStatus === "approved"))
    .filter((item) => !needle || `${item.patientName} ${item.caseId}`.toLocaleLowerCase().includes(needle));
  const label = (key: QueueFilter, text: string) => <>{text}<span className={`count${filter === key ? " count--active" : ""}`}>{formatNumber(counts[key], locale)}</span></>;

  return <aside className="queue" aria-label={t.filter}>
    <div className="queue__tools">
      <Segmented block label={t.filter} value={filter} onChange={onFilter} options={[
        { value: "review", label: label("review", t.toReview) },
        { value: "approved", label: label("approved", t.approvedFilter) },
        { value: "all", label: label("all", t.all) },
      ]} />
      <div className="search"><Icon name="search" size={15} /><input className="input" type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder={t.search} aria-label={t.search} /></div>
    </div>
    {cases === null ? <div style={{ padding: 12, display: "grid", gap: 8 }} aria-hidden="true">{[0, 1, 2].map((key) => <div key={key} className="skeleton" style={{ height: 46 }} />)}</div>
      : visible.length === 0 ? <p className="muted" style={{ padding: 16, fontSize: 13, textAlign: "center" }}>{needle ? t.noMatches : filter === "review" ? t.queueEmptyReview : t.noMatches}</p>
      : <ul className="queue__list" ref={listRef}>{visible.map((item) => <li key={item.caseId}>
        <button type="button" className="queue-item" aria-current={selectedId === item.caseId ? "true" : undefined} onClick={() => onSelect(item.caseId)}>
          <b>{item.patientName}</b>
          <span className="queue-item__meta">
            {item.alertCount > 0 && <span className="count count--danger" title={t.openAlerts.replace("{n}", String(item.alertCount))} aria-label={t.openAlerts.replace("{n}", String(item.alertCount))}>{formatNumber(item.alertCount, locale)}</span>}
            {item.stage === "needs_attention" && <Badge tone="danger" plain>{t.needsAttention}</Badge>}
            {!!item.failedRunCount && <Badge tone="warning" plain>{t.failedSteps.replace("{n}", formatNumber(item.failedRunCount, locale))}</Badge>}
            {filter === "all" && <Badge tone={item.reviewStatus === "approved" ? "success" : "warning"} plain>{item.reviewStatus === "approved" ? t.statusApproved : t.statusDraft}</Badge>}
          </span>
          <small className="mono" dir="ltr" style={{ justifySelf: "start" }}>{item.caseId}</small>
          {item.reviewStatus === "draft" && item.createdAt ? <small className="queue-item__when" title={t.registered}>{formatRelative(item.createdAt, locale)}</small>
            : item.nextStepAt ? <small className="queue-item__when">{t.nextStep} <bdi>{formatShort(item.nextStepAt, locale)}</bdi></small> : null}
        </button>
      </li>)}</ul>}
  </aside>;
}
