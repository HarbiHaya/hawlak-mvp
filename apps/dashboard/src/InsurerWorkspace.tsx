import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ALERTS_CHANGED } from "./events";
import { Icon } from "./Icon";
import { AlertsView } from "./insurer/AlertsView";
import { CaseQueue, type QueueFilter } from "./insurer/CaseQueue";
import { ContentTab, CoverageTab, DeliveryTab, MedicationsTab, SourceTab } from "./insurer/tabs";
import { coverageLabel, dialectLabel, languageLabel, t as texts, type CaseTab } from "./insurer/text";
import { HawlakApiError, type HawlakApi, type WorkspaceCaseDetail, type WorkspaceCaseSummary } from "./api";
import { displayError, formatDateTime, formatNumber, formatShort, pick, type Locale } from "./i18n";
import { dispatchSummary, readiness, type ReadinessArea } from "./readiness";
import { queryParam, replaceQueryParam, viewPath, type InsurerSection, type UserRole } from "./routing";
import { Badge, Dialog, EmptyState, PageHeader, Tabs, useToast } from "./ui";

export function InsurerWorkspace({ api, locale, section, reviewer, role, navigate }: { api: HawlakApi; locale: Locale; section: InsurerSection; reviewer: string; role: UserRole; navigate: (path: string) => void }) {
  const casesPath = viewPath(role, "insurer", "cases") ?? "/insurer/cases";
  if (section === "alerts") return <AlertsView api={api} locale={locale} onOpenCase={(caseId) => navigate(`${casesPath}?case=${encodeURIComponent(caseId)}`)} />;
  return <CasesView api={api} locale={locale} reviewer={reviewer} />;
}

const reviewedContent = (detail: WorkspaceCaseDetail) => ({ dischargeVoiceNote: detail.dischargeVoiceNote, medications: detail.medications, callPlan: detail.callPlan });
const snapshot = (detail: WorkspaceCaseDetail | null) => (detail ? JSON.stringify(reviewedContent(detail)) : "");
const areaTab: Record<ReadinessArea, CaseTab> = { coverage: "coverage", medications: "medications", content: "content" };

function initialTab(detail: WorkspaceCaseDetail): CaseTab {
  if (detail.reviewStatus === "approved") return "journey";
  const { blockerArea } = readiness(detail);
  return blockerArea ? areaTab[blockerArea] : "source";
}

function CasesView({ api, locale, reviewer }: { api: HawlakApi; locale: Locale; reviewer: string }) {
  const t = texts[locale];
  const { notify } = useToast();
  const [cases, setCases] = useState<WorkspaceCaseSummary[] | null>(null);
  const [filter, setFilter] = useState<QueueFilter>("review");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(() => queryParam("case"));
  const [detail, setDetail] = useState<WorkspaceCaseDetail | null>(null);
  const [saved, setSaved] = useState("");
  const [tab, setTab] = useState<CaseTab>("source");
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [action, setAction] = useState<"save" | "approve" | "draft" | "eligibility" | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"approve" | "regenerate" | null>(null);

  const dirty = !!detail && detail.reviewStatus === "draft" && snapshot(detail) !== saved;
  const fail = useCallback((caught: unknown) => notify(displayError(caught, locale), "error"), [locale, notify]);

  const applyDetail = useCallback((next: WorkspaceCaseDetail, resetTab = false) => {
    setDetail(next);
    setSaved(snapshot(next));
    if (resetTab) setTab(initialTab(next));
  }, []);

  const refreshList = useCallback(async () => {
    const result = await api.listWorkspaceCases();
    setCases(result.data);
    return result.data;
  }, [api]);

  const openCase = useCallback(async (caseId: string) => {
    setSelectedId(caseId);
    replaceQueryParam("case", caseId);
    setLoadingDetail(true);
    try { applyDetail(await api.getWorkspaceCase(caseId), true); }
    catch (caught) {
      setDetail(null);
      if (caught instanceof HawlakApiError && caught.code === "case_not_found") replaceQueryParam("case", null);
      fail(caught);
    }
    finally { setLoadingDetail(false); }
  }, [api, applyDetail, fail]);

  // Initial load: honour ?case= deep links, otherwise open the first case awaiting review.
  useEffect(() => {
    let cancelled = false;
    refreshList().then((data) => {
      if (cancelled) return;
      const requested = queryParam("case");
      const target = data.find((item) => item.caseId === requested) ?? data.find((item) => item.reviewStatus === "draft") ?? data[0];
      if (!data.some((item) => item.reviewStatus === "draft")) setFilter("all");
      if (target && requested && target.caseId === requested && target.reviewStatus === "approved") setFilter("all");
      if (target) void openCase(target.caseId);
      setLoadError(null);
    }).catch((caught) => { if (!cancelled) setLoadError(displayError(caught, locale)); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  // Poll only while delivery runs are in flight.
  const inFlight = detail?.deliveryRuns.some((run) => run.status === "pending" || run.status === "claimed");
  useEffect(() => {
    if (!detail || !inFlight) return;
    const timer = window.setInterval(() => { api.getWorkspaceCase(detail.caseId).then((next) => applyDetail(next)).catch(() => undefined); }, 5_000);
    return () => window.clearInterval(timer);
  }, [api, detail?.caseId, inFlight, applyDetail]);

  // Warn before leaving the page with unsaved edits.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save(quiet = false): Promise<boolean> {
    if (!detail || detail.reviewStatus === "approved") return true;
    setAction("save");
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      setSaved(snapshot(detail));
      if (!quiet) notify(t.saved);
      void refreshList();
      return true;
    } catch (caught) { fail(caught); return false; }
    finally { setAction(null); }
  }

  // Ctrl/Cmd+S saves the draft.
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); void saveRef.current(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function selectCase(caseId: string) {
    if (caseId === selectedId) return;
    // Switching cases keeps edits: the current draft is saved first.
    if (dirty && !(await save(true))) return;
    await openCase(caseId);
  }

  async function approve() {
    if (!detail) return;
    setConfirm(null);
    setAction("approve");
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      const result = await api.approveWorkspaceCase(detail.caseId, reviewer, `approve-${detail.caseId}-${crypto.randomUUID()}`);
      applyDetail(await api.getWorkspaceCase(detail.caseId));
      setTab("journey");
      setFilter("all"); // keep the approved case visible and selected in the queue
      void refreshList();
      window.dispatchEvent(new Event(ALERTS_CHANGED));
      notify(t.approvedToast.replace("{ref}", result.insurance?.enrollmentReference ?? "—"));
    } catch (caught) { fail(caught); }
    finally { setAction(null); }
  }

  async function regenerate() {
    if (!detail) return;
    setConfirm(null);
    setAction("draft");
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      applyDetail(await api.regenerateDrafts(detail.caseId));
      notify(t.regenerated);
    } catch (caught) { fail(caught); }
    finally { setAction(null); }
  }

  async function checkEligibility(memberId: string) {
    if (!detail) return;
    setAction("eligibility");
    try {
      await api.updateWorkspaceContent(detail.caseId, reviewedContent(detail));
      applyDetail(await api.checkEligibility(detail.caseId, memberId));
      notify(t.checked);
      void refreshList();
    } catch (caught) { fail(caught); }
    finally { setAction(null); }
  }

  const ready = useMemo(() => (detail ? readiness(detail) : null), [detail]);
  const locked = detail?.reviewStatus === "approved";
  const busy = action !== null;

  if (loadError) return <div className="page"><PageHeader title={t.title} /><EmptyState icon="alert" title={loadError}><button className="button" onClick={() => window.location.reload()}><Icon name="refresh" size={16} />{t.retry}</button></EmptyState></div>;

  const tabItems = [
    { id: "source" as const, label: t.source },
    { id: "coverage" as const, label: t.coverage, state: locked || !ready ? undefined : ready.areas.coverage ? "todo" as const : "done" as const },
    { id: "medications" as const, label: t.medications, state: locked || !ready ? undefined : ready.areas.medications ? "todo" as const : "done" as const },
    { id: "content" as const, label: t.content, state: locked || !ready ? undefined : ready.areas.content ? "todo" as const : "done" as const },
    { id: "journey" as const, label: t.journey },
  ];

  return <div className="page page--wide">
    <PageHeader title={t.title} />
    <div className="panel review-layout">
      <CaseQueue cases={cases} locale={locale} filter={filter} onFilter={setFilter} query={query} onQuery={setQuery} selectedId={selectedId} onSelect={(id) => void selectCase(id)} />
      <section className="case" aria-label={t.caseDetails} aria-busy={loadingDetail}>
        {!detail ? (loadingDetail || cases === null ? <CaseSkeleton /> : <EmptyState icon="briefcase-medical" title={cases.length === 0 ? t.noCases : t.selectCase} />) : <>
          <header className="case__header">
            <div className="case__title">
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                <h2>{detail.patientName}</h2>
                <Badge tone={locked ? "success" : "warning"}>{locked ? t.statusApproved : t.statusDraft}</Badge>
                {detail.insurance && <Badge tone={detail.insurance.status === "eligible" ? "success" : "danger"}>{coverageLabel(detail.insurance, locale)}</Badge>}
              </div>
              <div className="case__meta">
                <span className="mono" dir="ltr">{detail.caseId}</span>
                <span className="sep" />
                <span>{pick(languageLabel, detail.languageCode, locale)}{detail.languageCode === "ar" && ` · ${pick(dialectLabel, detail.dialectCode, locale)}`}</span>
                {detail.preferredFormOfAddress && <><span className="sep" /><span>{t.preferred}: <bdi>{detail.preferredFormOfAddress}</bdi></span></>}
                {locked && detail.approvedAt && <><span className="sep" /><span>{t.approvedBy} <bdi>{detail.approvedBy}</bdi> · {formatDateTime(detail.approvedAt, locale)}</span></>}
              </div>
            </div>
            {!locked && <div className="case__actions">
              <span className={`save-state${dirty ? " save-state--dirty" : ""}`} role="status">{action === "save" ? t.saving : dirty ? t.unsaved : t.allSaved}</span>
              <button className="button" disabled={busy || !dirty} onClick={() => void save()} title={locale === "ar" ? "Ctrl+S" : "Ctrl+S"}>{t.save}</button>
              <button className="button button--primary" disabled={busy || !!ready?.blocker} onClick={() => setConfirm("approve")} aria-describedby={ready?.blocker ? "approval-blocker" : undefined}>{action === "approve" ? t.approving : t.approve}</button>
            </div>}
          </header>
          {!locked && ready?.blocker && <div className="blocker" id="approval-blocker" role="status">
            <Icon name="alert" size={16} />
            <span>{displayError(new HawlakApiError(409, ready.blocker), locale)}</span>
            {ready.blockerArea && tab !== areaTab[ready.blockerArea] && <button type="button" className="button button--link" onClick={() => setTab(areaTab[ready.blockerArea!])}>{t.goTo.replace("{tab}", tabItems.find((item) => item.id === areaTab[ready.blockerArea!])!.label)}</button>}
          </div>}
          <Tabs items={tabItems} value={tab} onChange={setTab} label={t.caseDetails} idPrefix="case" locale={locale} />
          <div className="case__body" role="tabpanel" id="case-panel" aria-labelledby={`case-tab-${tab}`}>
            {tab === "source" && <SourceTab api={api} detail={detail} locale={locale} />}
            {tab === "coverage" && <CoverageTab detail={detail} locale={locale} busy={action === "eligibility"} onCheck={(memberId) => void checkEligibility(memberId)} />}
            {tab === "medications" && <MedicationsTab api={api} detail={detail} locale={locale} onChange={setDetail} onError={fail} />}
            {tab === "content" && <ContentTab detail={detail} locale={locale} onChange={setDetail} busy={action === "draft"} onRegenerate={() => (detail.generatedDraft ? setConfirm("regenerate") : void regenerate())} />}
            {tab === "journey" && <DeliveryTab detail={detail} locale={locale} />}
          </div>
        </>}
      </section>
    </div>
    {detail && <ApproveDialog open={confirm === "approve"} detail={detail} locale={locale} onCancel={() => setConfirm(null)} onConfirm={() => void approve()} />}
    <Dialog open={confirm === "regenerate"} title={t.regenerateTitle} onClose={() => setConfirm(null)} footer={<><button className="button" onClick={() => setConfirm(null)}>{t.cancel}</button><button className="button button--primary" onClick={() => void regenerate()}>{t.regenerate}</button></>}>
      <p>{t.regenerateConfirm}</p>
    </Dialog>
  </div>;
}

function ApproveDialog({ open, detail, locale, onCancel, onConfirm }: { open: boolean; detail: WorkspaceCaseDetail; locale: Locale; onCancel: () => void; onConfirm: () => void }) {
  const t = texts[locale];
  const summary = dispatchSummary(detail);
  const count = (n: number, one: string, many: string) => (n === 1 ? one : many.replace("{n}", formatNumber(n, locale)));
  return <Dialog open={open} title={t.approveTitle} onClose={onCancel} footer={<><button className="button" onClick={onCancel}>{t.cancel}</button><button className="button button--primary" onClick={onConfirm} autoFocus>{t.approveConfirm}</button></>}>
    <p>{t.approveIntro.replace("{name}", detail.patientName)}</p>
    <ul className="dispatch-list">
      {summary.voiceNote && <li><Icon name="message" size={16} />{t.dispatchVoice}</li>}
      {summary.reminders > 0 && <li><Icon name="pill" size={16} />{count(summary.reminders, t.dispatchReminders1, t.dispatchReminders)}</li>}
      {summary.calls.length > 0 && <li><Icon name="phone" size={16} /><span>{count(summary.calls.length, t.dispatchCalls1, t.dispatchCalls)} · {t.firstCallShort} <bdi>{formatShort(summary.calls[0], locale)}</bdi></span></li>}
      {summary.notDispensed.length > 0 && <li><Icon name="alert" size={16} /><span>{count(summary.notDispensed.length, t.dispatchAlerts1, t.dispatchAlerts)}</span></li>}
    </ul>
    <p className="muted">{t.approveImmutable}</p>
  </Dialog>;
}

function CaseSkeleton() {
  return <div style={{ padding: 24, display: "grid", gap: 16 }} aria-hidden="true">
    <div className="skeleton" style={{ height: 22, width: "40%" }} />
    <div className="skeleton" style={{ height: 14, width: "60%" }} />
    <div className="skeleton" style={{ height: 36 }} />
    <div className="skeleton" style={{ height: 220 }} />
  </div>;
}
