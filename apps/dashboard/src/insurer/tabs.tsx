import { useEffect, useState } from "react";

import type { CallPlan, CallRepeat, DischargeExtraction, DoseFacts, FactSource, HawlakApi, WorkspaceCaseDetail, WorkspaceMedication } from "../api";
import { Icon } from "../Icon";
import { formatDate, formatDateTime, formatShort, pick, type Locale } from "../i18n";
import { dispatchSummary } from "../readiness";
import { Badge, EmptyState, Field, Notice, Segmented } from "../ui";
import { coverageLabel, dialectLabel, factReasonLabel, factSourceLabel, languageLabel, photoCheckLabel, repeatLabel, runKindIcon, runKindLabel, runStatusLabel, runStatusTone, t as texts } from "./text";

type Origin = "generated" | "edited" | "manual";
const originOf = (current: string, generated: string | undefined): Origin => generated === undefined ? "manual" : current.trim() === generated.trim() ? "generated" : "edited";
const callText = (opening: string, questions: { prompt: string }[], completion: string, transfer: string) => [opening, ...questions.map((q) => q.prompt), completion, transfer].join("\n");

function OriginTag({ origin, locale }: { origin: Origin; locale: Locale }) {
  const t = texts[locale];
  return <span className={`origin origin--${origin}`}>{origin === "generated" ? t.originGenerated : origin === "edited" ? t.originEdited : t.originManual}</span>;
}

/** Fetches a case file through the authenticated API and exposes it as an object URL. */
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

/* ---------- Discharge summary ---------- */

// Extraction never changes for a stored document, so it is fetched once per case.
const extractionCache = new Map<string, DischargeExtraction>();

export function SourceTab({ api, detail, locale }: { api: HawlakApi; detail: WorkspaceCaseDetail; locale: Locale }) {
  const t = texts[locale];
  const pdfUrl = useCaseFileUrl(api, detail.caseId, detail.sourceDocument.objectKey);
  const [extraction, setExtraction] = useState<DischargeExtraction | null>(() => extractionCache.get(detail.caseId) ?? null);
  useEffect(() => {
    const cached = extractionCache.get(detail.caseId);
    if (cached) { setExtraction(cached); return; }
    let cancelled = false;
    setExtraction(null);
    api.getCaseExtraction(detail.caseId).then((result) => { extractionCache.set(detail.caseId, result); if (!cancelled) setExtraction(result); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [api, detail.caseId]);
  const docDir = extraction?.language === "ar" ? "rtl" : "ltr";

  return <>
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <dl className="facts" style={{ flex: 1 }}>
        <div><dt>{t.document}</dt><dd><bdi>{detail.sourceDocument.filename}</bdi></dd></div>
        <div><dt>{t.language}</dt><dd>{pick(languageLabel, detail.languageCode, locale)}{detail.languageCode === "ar" && ` · ${pick(dialectLabel, detail.dialectCode, locale)}`}</dd></div>
        <div><dt>{t.preferred}</dt><dd>{detail.preferredFormOfAddress ? <bdi>{detail.preferredFormOfAddress}</bdi> : "—"}</dd></div>
      </dl>
      {pdfUrl && <a className="button button--sm" href={pdfUrl} target="_blank" rel="noreferrer"><Icon name="external" size={14} />{t.openPdf}</a>}
    </div>
    {extraction && (extraction.status !== "parsed"
      ? <Notice tone="warning">{extraction.status === "no_text" ? t.noText : t.unreadable}</Notice>
      : <section className="editor-block">
        <div className="editor-block__head"><h3 className="section-title" style={{ margin: 0 }}>{t.extracted}</h3></div>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          {extraction.medications.length === 0 && <Notice tone="warning">{t.nothingFound}</Notice>}
          <div className="extraction" dir={docDir}>
            {extraction.medications.length > 0 && <div><h3>{t.extractedMeds}</h3><ul>{extraction.medications.map((item, index) => <li key={index}><bdi>{item.name}</bdi>{item.instruction && <> — <bdi>{item.instruction}</bdi></>}</li>)}</ul></div>}
            {extraction.stoppedMedications.length > 0 && <div><h3>{t.extractedStopped}</h3><ul>{extraction.stoppedMedications.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
            {extraction.sections.map((section, index) => <div key={index}><h3>{section.heading}</h3><ul>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></div>)}
            {extraction.notes.length > 0 && <div><h3>{t.extractedNotes}</h3><ul>{extraction.notes.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
          </div>
          <details className="disclosure"><summary>{t.fullText}</summary><pre dir={docDir}>{extraction.text}</pre></details>
        </div>
      </section>)}
    {pdfUrl ? <iframe className="pdf-frame" src={pdfUrl} title={detail.sourceDocument.filename} /> : <div className="skeleton pdf-frame" aria-label={t.loadingPdf} />}
  </>;
}

/* ---------- Coverage ---------- */

export function CoverageTab({ detail, locale, busy, onCheck }: { detail: WorkspaceCaseDetail; locale: Locale; busy: boolean; onCheck: (memberId: string) => void }) {
  const t = texts[locale];
  const insurance = detail.insurance;
  const locked = detail.reviewStatus === "approved";
  const [memberId, setMemberId] = useState(insurance?.memberId ?? "");
  const [touched, setTouched] = useState(false);
  useEffect(() => { setMemberId(detail.insurance?.memberId ?? ""); setTouched(false); }, [detail.caseId, detail.insurance?.memberId]);
  const valid = /^[A-Za-z0-9-]{4,32}$/.test(memberId);
  const rows: Array<[string, string | undefined]> = insurance ? [
    [t.policy, insurance.policyNumber], [t.plan, insurance.plan], [t.network, insurance.network],
    [t.period, insurance.coverageStart && insurance.coverageEnd ? `${formatDate(insurance.coverageStart, locale)} – ${formatDate(insurance.coverageEnd, locale)}` : undefined],
    [t.programme, insurance.program ? t.programName : undefined],
    [t.manager, insurance.caseManager ? `${insurance.caseManager.name} · ${insurance.caseManager.phoneE164}` : undefined],
    [t.checkedAt, insurance.checkedAt ? formatDateTime(insurance.checkedAt, locale) : undefined],
    [t.enrollment, insurance.enrollmentReference],
  ] : [];
  return <>
    {insurance ? <div className={`coverage-head coverage-head--${insurance.status}`}>
      <Icon name={insurance.status === "eligible" ? "check-circle" : "alert"} size={20} />
      <b>{coverageLabel(insurance, locale)}</b>
      <span><bdi className="mono">{insurance.memberId}</bdi>{insurance.reason === "policy_lapsed" && ` · ${t.policyLapsed}`}{insurance.status === "not_found" && ` · ${t.notFoundHint}`}</span>
    </div> : <Notice tone="info">{t.notChecked}</Notice>}
    {rows.some(([, value]) => value) && <dl className="facts">{rows.filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><bdi>{value}</bdi></dd></div>)}</dl>}
    {!locked && <form className="inline-form" onSubmit={(event) => { event.preventDefault(); setTouched(true); if (valid) onCheck(memberId); }}>
      <Field label={t.memberId} error={touched && !valid ? t.memberInvalid : null}>{({ id, describedBy, invalid }) => <input id={id} className="input mono" dir="ltr" value={memberId} aria-describedby={describedBy} aria-invalid={invalid} onBlur={() => setTouched(true)} onChange={(event) => setMemberId(event.target.value.trim().toUpperCase())} placeholder="SYN-4471203" />}</Field>
      <button className={`button ${insurance?.status === "eligible" ? "" : "button--primary"}`} disabled={busy || !memberId}>{busy ? t.checking : insurance ? t.recheck : t.check}</button>
    </form>}
    <p className="muted" style={{ fontSize: 12 }}>{t.coverageSource}</p>
  </>;
}

/* ---------- Messages and call ---------- */

const toLocalInput = (iso: string) => { const date = new Date(iso); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); };
const tomorrowAtTen = () => { const date = new Date(); date.setDate(date.getDate() + 1); date.setHours(10, 0, 0, 0); return date.toISOString(); };

export function ContentTab({ detail, locale, onChange, busy, onRegenerate }: { detail: WorkspaceCaseDetail; locale: Locale; onChange: (next: WorkspaceCaseDetail) => void; busy: boolean; onRegenerate: () => void }) {
  const t = texts[locale];
  const locked = detail.reviewStatus === "approved";
  const plan = detail.callPlan;
  const generated = detail.generatedDraft;
  const voice = detail.dischargeVoiceNote;
  const updateCall = (change: Partial<CallPlan>) => onChange({ ...detail, callPlan: { ...plan, ...change } });
  const updateQuestion = (index: number, prompt: string) => updateCall({ questions: plan.questions.map((item, i) => i === index ? { ...item, prompt } : item) });
  const nextQuestionId = () => { let n = plan.questions.length + 1; while (plan.questions.some((q) => q.id === `q-${n}`)) n += 1; return `q-${n}`; };
  const voiceOrigin = originOf(voice.script, generated?.voiceScript);
  const callOrigin = originOf(callText(plan.openingScript, plan.questions, plan.completionScript, plan.transferScript), generated ? callText(generated.callOpening, generated.callQuestions, generated.callCompletion, generated.callTransfer) : undefined);
  const method = generated?.generator.startsWith("openai") ? t.methodAi : t.methodTemplate;

  return <>
    {!locked && <div className="draft-note">
      <Icon name="sparkle" size={16} />
      <div>
        <span>{generated ? t.generatedBy.replace("{method}", method).replace("{date}", formatDateTime(generated.generatedAt, locale)) : t.notGenerated}</span>
        {generated && generated.sourceLanguage !== detail.languageCode && generated.generator === "template" && <span className="draft-note__warn">{t.mixedLanguage}</span>}
        {generated?.notes.includes("live_draft_rejected") && <span className="draft-note__warn">{t.liveRejected}</span>}
      </div>
      <button type="button" className="button button--sm" disabled={busy} onClick={onRegenerate}><Icon name="refresh" size={14} />{busy ? t.regenerating : generated ? t.regenerate : t.generate}</button>
    </div>}

    <section className="editor-block">
      <div className="editor-block__head">
        <label className="switch"><input type="checkbox" role="switch" checked={voice.enabled} disabled={locked} onChange={(event) => onChange({ ...detail, dischargeVoiceNote: { ...voice, enabled: event.target.checked } })} />{t.voice}</label>
        <OriginTag origin={voiceOrigin} locale={locale} />
      </div>
      {voice.enabled && <div className="editor-block__body">
        <Field full label={t.script} hint={t.voiceHint}>{({ id, describedBy }) => <textarea id={id} aria-describedby={describedBy} className="textarea textarea--script" dir="auto" disabled={locked} value={voice.script} onChange={(event) => onChange({ ...detail, dischargeVoiceNote: { ...voice, script: event.target.value } })} />}</Field>
      </div>}
    </section>

    <section className="editor-block">
      <div className="editor-block__head">
        <label className="switch"><input type="checkbox" role="switch" checked={plan.enabled} disabled={locked} onChange={(event) => updateCall({ enabled: event.target.checked })} />{t.call}</label>
        <OriginTag origin={callOrigin} locale={locale} />
      </div>
      {plan.enabled && <fieldset className="editor-block__body" disabled={locked}>
        <legend className="sr-only">{t.call}</legend>
        <CallSchedule plan={plan} locale={locale} onChange={updateCall} />
        <Field label={t.opening}>{({ id }) => <textarea id={id} className="textarea" dir="auto" value={plan.openingScript} onChange={(event) => updateCall({ openingScript: event.target.value })} />}</Field>
        <Field label={t.completion}>{({ id }) => <textarea id={id} className="textarea" dir="auto" value={plan.completionScript} onChange={(event) => updateCall({ completionScript: event.target.value })} />}</Field>
        <div className="field field--full">
          <span className="field__label">{t.questions}</span>
          <div className="questions">
            {plan.questions.map((question, index) => <div className="question" key={question.id}>
              <span aria-hidden="true">{index + 1}</span>
              <textarea className="textarea" dir="auto" rows={1} aria-label={`${t.questions} ${index + 1}`} value={question.prompt} onChange={(event) => updateQuestion(index, event.target.value)} />
              {!locked && <button type="button" className="button button--ghost button--icon" aria-label={t.removeQuestion.replace("{n}", String(index + 1))} onClick={() => updateCall({ questions: plan.questions.filter((_, i) => i !== index) })}><Icon name="x" size={16} /></button>}
            </div>)}
            {!locked && plan.questions.length < 12 && <button type="button" className="button button--sm" style={{ justifySelf: "start" }} onClick={() => updateCall({ questions: [...plan.questions, { id: nextQuestionId(), prompt: "" }] })}><Icon name="plus" size={14} />{t.addQuestion}</button>}
          </div>
        </div>
        <Field full label={t.transfer}>{({ id }) => <textarea id={id} className="textarea" dir="auto" value={plan.transferScript} onChange={(event) => updateCall({ transferScript: event.target.value })} />}</Field>
        <Field label={t.team}>{({ id }) => <input id={id} className="input" value={plan.transferTarget} onChange={(event) => updateCall({ transferTarget: event.target.value })} />}</Field>
        <Field label={t.responder}>{({ id }) => <input id={id} className="input mono" dir="ltr" inputMode="tel" value={plan.responderPhoneE164} onChange={(event) => updateCall({ responderPhoneE164: event.target.value.replace(/\s/g, "") })} placeholder="+9665XXXXXXXX" />}</Field>
      </fieldset>}
    </section>
  </>;
}

function CallSchedule({ plan, locale, onChange }: { plan: CallPlan; locale: Locale; onChange: (change: Partial<CallPlan>) => void }) {
  const t = texts[locale];
  const repeat = plan.repeat ?? "none";
  const occurrences = repeat === "none" ? 1 : plan.occurrences ?? 1;
  const exact = !!plan.firstCallAt;
  const preset = exact ? "exact" : [24, 48, 72].includes(plan.scheduledAfterHours) ? String(plan.scheduledAfterHours) : "custom";
  const times = dispatchSummary({ insurance: null, medications: [], dischargeVoiceNote: { enabled: false, script: "" }, callPlan: { ...plan, enabled: true } }).calls;
  return <div className="schedule">
    <span className="field__label">{t.schedule}</span>
    <Segmented label={t.schedule} value={preset} onChange={(value) => value === "exact" ? onChange({ firstCallAt: plan.firstCallAt ?? tomorrowAtTen() }) : value !== "custom" && onChange({ firstCallAt: null, scheduledAfterHours: Number(value) })} options={[
      ...[24, 48, 72].map((hours) => ({ value: String(hours), label: t.inHours.replace("{n}", String(hours)) })),
      ...(preset === "custom" ? [{ value: "custom", label: t.inHours.replace("{n}", String(plan.scheduledAfterHours)) }] : []),
      { value: "exact", label: t.pickDate },
    ]} />
    <div className="schedule__fields">
      {exact
        ? <Field label={t.firstCall}>{({ id }) => <input id={id} className="input" type="datetime-local" dir="ltr" min={toLocalInput(new Date().toISOString())} value={toLocalInput(plan.firstCallAt!)} onChange={(event) => event.target.value && onChange({ firstCallAt: new Date(event.target.value).toISOString() })} />}</Field>
        : <Field label={t.hoursAfter}>{({ id }) => <input id={id} className="input" type="number" min="0" max="168" value={plan.scheduledAfterHours} onChange={(event) => onChange({ scheduledAfterHours: Math.min(168, Math.max(0, Number(event.target.value))) })} />}</Field>}
      <Field label={t.repeat}>{({ id }) => <select id={id} className="select" value={repeat} onChange={(event) => { const next = event.target.value as CallRepeat; onChange({ repeat: next, occurrences: next === "none" ? 1 : Math.max(2, occurrences) }); }}>{(Object.keys(repeatLabel) as CallRepeat[]).map((value) => <option key={value} value={value}>{repeatLabel[value][locale]}</option>)}</select>}</Field>
      <Field label={t.occurrences}>{({ id }) => <select id={id} className="select" value={occurrences} disabled={repeat === "none"} onChange={(event) => onChange({ occurrences: Number(event.target.value) })}>{Array.from({ length: 14 }, (_, index) => index + 1).map((count) => <option key={count} value={count}>{count}</option>)}</select>}</Field>
    </div>
    {exact && <ol className="schedule__preview" aria-label={t.schedule}>{times.map((time) => <li key={time.toISOString()}><Badge plain tone="info"><bdi>{formatShort(time, locale)}</bdi></Badge></li>)}</ol>}
  </div>;
}

/* ---------- Medications ---------- */

const CLOCK_TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const parseTimes = (text: string) => text.split(/[,،\s]+/).map((value) => value.padStart(5, "0")).filter((value) => CLOCK_TIME.test(value));

// Each dose detail with its source. Unknown stays unknown: nothing here is inferred in the browser.
function DoseFactsLine({ facts, locale }: { facts: DoseFacts | undefined; locale: Locale }) {
  if (!facts) return null;
  const t = texts[locale];
  const source = (fact: { source: FactSource; reason?: string }) => pick(factSourceLabel, fact.source, locale) + (fact.reason ? `: ${pick(factReasonLabel, fact.reason, locale)}` : "");
  const rows: Array<[string, string | number | null, { source: FactSource; reason?: string }]> = [
    [t.factDose, facts.prescribedDose.value, facts.prescribedDose],
    [t.factUnits, facts.unitsPerDose.value, facts.unitsPerDose],
    [t.factTimes, facts.reminderTimes.value.join(locale === "ar" ? "، " : ", ") || null, facts.reminderTimes],
  ];
  return <p className="field__hint dose-facts">{rows.map(([label, value, fact]) => <span key={label}>{label}: {value !== null && <b dir="ltr">{value}</b>} ({source(fact)})</span>)}<span>{t.factsAfterSave}</span></p>;
}

export function MedicationsTab({ api, detail, locale, onChange }: { api: HawlakApi; detail: WorkspaceCaseDetail; locale: Locale; onChange: (next: WorkspaceCaseDetail) => void }) {
  const t = texts[locale];
  const locked = detail.reviewStatus === "approved";
  const [removed, setRemoved] = useState<{ item: WorkspaceMedication; index: number } | null>(null);
  useEffect(() => setRemoved(null), [detail.caseId]);

  const update = (medicationId: string, change: Partial<WorkspaceMedication>) => onChange({ ...detail, medications: detail.medications.map((item) => item.medicationId === medicationId ? { ...item, ...change } : item) });
  function add() {
    onChange({ ...detail, medications: [...detail.medications, { medicationId: `SYN-MED-${crypto.randomUUID().slice(0, 8)}`, displayName: "", doseInstruction: "", dispensed: true, image: null, reminderEnabled: false, reminderScript: "", unitStrength: null, reminderTimes: [] }] });
    window.requestAnimationFrame(() => document.querySelector<HTMLInputElement>(".med:last-of-type input")?.focus());
  }
  function remove(index: number) {
    setRemoved({ item: detail.medications[index], index });
    onChange({ ...detail, medications: detail.medications.filter((_, i) => i !== index) });
  }
  function undo() {
    if (!removed) return;
    const medications = [...detail.medications];
    medications.splice(Math.min(removed.index, medications.length), 0, removed.item);
    onChange({ ...detail, medications });
    setRemoved(null);
  }
  const patientPhoto = (medicationId: string) => [...(detail.medicinePhotos ?? [])].reverse().find((photo) => photo.medicationId === medicationId && photo.checkStatus !== "unreadable");

  return <div className="med-list">
    {removed && <Notice tone="neutral" icon="trash"><span style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>{t.removed.replace("{name}", removed.item.displayName || t.unnamed)}<button type="button" className="button button--link" onClick={undo}>{t.undo}</button></span></Notice>}
    {detail.medications.length === 0 && <EmptyState compact icon="pill" title={t.noMedications} />}
    {detail.medications.map((item, index) => {
      const generatedReminder = detail.generatedDraft?.reminderScripts[item.medicationId];
      const photo = patientPhoto(item.medicationId);
      return <article className="med" key={item.medicationId} aria-label={item.displayName || t.unnamed}>
        <div className="med__image">
          <MedicineImage api={api} caseId={detail.caseId} objectKey={photo?.objectKey ?? item.image?.objectKey} alt={item.displayName} empty={t.noImage} />
          {item.dispensed && <Badge tone={photo ? "info" : "neutral"} plain>{photo ? t.patientPhoto : t.photoAfterApproval}</Badge>}
        </div>
        <div className="med__fields">
          <Field label={t.medicationName}>{({ id }) => <input id={id} className="input" disabled={locked} value={item.displayName} onChange={(event) => update(item.medicationId, { displayName: event.target.value })} />}</Field>
          <Field label={t.dose}>{({ id }) => <input id={id} className="input" disabled={locked} value={item.doseInstruction} onChange={(event) => update(item.medicationId, { doseInstruction: event.target.value })} />}</Field>
          <div className="med__toggles">
            <label className="switch"><input type="checkbox" role="switch" disabled={locked} checked={item.dispensed} onChange={(event) => update(item.medicationId, { dispensed: event.target.checked, reminderEnabled: event.target.checked ? item.reminderEnabled : false })} />{t.dispensed}</label>
            <label className="switch"><input type="checkbox" role="switch" disabled={locked || !item.dispensed} checked={item.reminderEnabled} onChange={(event) => update(item.medicationId, { reminderEnabled: event.target.checked })} />{t.enableReminder}</label>
            {!item.dispensed && <span className="field__hint" style={{ alignSelf: "center" }}>{t.notDispensedHint}</span>}
          </div>
          {item.dispensed && item.reminderEnabled && <Field full label={t.reminder} aside={<OriginTag origin={originOf(item.reminderScript, generatedReminder)} locale={locale} />}>{({ id }) => <input id={id} className="input" dir="auto" disabled={locked} value={item.reminderScript} onChange={(event) => update(item.medicationId, { reminderScript: event.target.value })} />}</Field>}
          <Field label={t.unitStrength}>{({ id }) => <input id={id} className="input" dir="ltr" disabled={locked} placeholder="40 mg" value={item.unitStrength ?? ""} onChange={(event) => update(item.medicationId, { unitStrength: event.target.value || null })} />}</Field>
          {/* Parsed when the field loses focus, so commas and spaces can be typed freely. */}
          <Field label={t.reminderTimes} hint={t.timesHint}>{({ id, describedBy }) => <input id={id} className="input" dir="ltr" disabled={locked} placeholder="08:00, 20:00" aria-describedby={describedBy} defaultValue={(item.reminderTimes ?? []).join(", ")} onBlur={(event) => { const times = parseTimes(event.target.value); event.target.value = times.join(", "); update(item.medicationId, { reminderTimes: times }); }} />}</Field>
          <DoseFactsLine facts={detail.doseFacts?.[item.medicationId]} locale={locale} />
          {!locked && <div className="med__footer">
            <button type="button" className="button button--sm button--ghost button--danger" onClick={() => remove(index)}><Icon name="trash" size={14} />{t.removeMedication}</button>
          </div>}
        </div>
      </article>;
    })}
    {!locked && <button type="button" className="button" style={{ justifySelf: "start" }} onClick={add}><Icon name="plus" size={16} />{t.addMedication}</button>}
  </div>;
}

export function PhotosTab({ api, detail, locale, busy, onReview }: { api: HawlakApi; detail: WorkspaceCaseDetail; locale: Locale; busy: boolean; onReview: (id: string, decision: "confirmed" | "follow_up") => void }) {
  const t = texts[locale];
  const photos = detail.medicinePhotos ?? [];
  if (photos.length === 0) return <EmptyState compact icon="image" title={t.noPhotos} />;
  const planned = (id: string | null) => detail.medications.find((item) => item.medicationId === id)?.displayName;
  return <>
    <Notice tone="info">{t.photosNote}</Notice>
    <div className="photo-grid">{photos.map((photo) => <article className="photo-review" key={photo.id}>
      <MedicineImage api={api} caseId={detail.caseId} objectKey={photo.objectKey ?? undefined} alt={photo.reading?.name ?? t.photos} empty={t.noImage} />
      <dl className="photo-facts">
        <div><dt>{t.sentBy}</dt><dd>{photo.sender === "caregiver" ? t.fromCaregiver : t.fromPatient} · {formatDate(photo.receivedAt, locale)}</dd></div>
        <div><dt>{t.label}</dt><dd dir="auto">{photo.reading ? [photo.reading.name, photo.reading.strength, photo.reading.form].filter(Boolean).join(" · ") : t.notRead}</dd></div>
        <div><dt>{t.planned}</dt><dd dir="auto">{planned(photo.medicationId) ?? "—"}</dd></div>
        <div><dt>{t.photoStatus}</dt><dd><span className={`photo-state photo-state--${photo.checkStatus}`}>{photoCheckLabel[photo.checkStatus][locale]}</span></dd></div>
      </dl>
      <div className="photo-review__actions">{photo.reviewStatus
        ? <span className={`photo-state photo-state--${photo.reviewStatus}`}>{photo.reviewStatus === "confirmed" ? t.confirmPhoto : t.followUp} · {t.reviewed.replace("{who}", photo.reviewedBy ?? "")}</span>
        : <><button type="button" className="button button--sm" disabled={busy} onClick={() => onReview(photo.id, "follow_up")}>{t.followUp}</button><button type="button" className="button button--sm button--primary" disabled={busy} onClick={() => onReview(photo.id, "confirmed")}>{t.confirmPhoto}</button></>}
      </div>
    </article>)}</div>
  </>;
}

function MedicineImage({ api, caseId, objectKey, alt, empty }: { api: HawlakApi; caseId: string; objectKey?: string; alt: string; empty: string }) {
  const url = useCaseFileUrl(api, caseId, objectKey?.startsWith(`cases/${caseId}/`) ? objectKey : undefined);
  return <div className="med__thumb">{url ? <img src={url} alt={alt} /> : <Icon name="image" size={22} label={empty} />}</div>;
}

/* ---------- Delivery ---------- */

export function DeliveryTab({ detail, locale }: { detail: WorkspaceCaseDetail; locale: Locale }) {
  const t = texts[locale];
  if (detail.deliveryRuns.length === 0) return <EmptyState compact icon="clock" title={t.noRuns} />;
  return <>
    {detail.deliveryMode === "mock" && <Notice tone="info">{t.demoMode}</Notice>}
    {detail.approvedAt && <dl className="facts">
      <div><dt>{t.approvedBy}</dt><dd><bdi>{detail.approvedBy}</bdi></dd></div>
      <div><dt>{t.approvedAt}</dt><dd>{formatDateTime(detail.approvedAt, locale)}</dd></div>
      {detail.insurance?.enrollmentReference && <div><dt>{t.enrollment}</dt><dd><bdi className="mono">{detail.insurance.enrollmentReference}</bdi></dd></div>}
    </dl>}
    <ol className="timeline">{detail.deliveryRuns.map((run) => {
      const simulated = run.providerRef?.startsWith("mock:");
      return <li key={run.id}>
        <span className="row__icon"><Icon name={runKindIcon[run.kind] ?? "clock"} size={15} /></span>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}><b>{pick(runKindLabel, run.kind, locale)}</b>{simulated ? <Badge tone="info">{t.simulated}</Badge> : <Badge tone={runStatusTone[run.status] ?? "neutral"}>{pick(runStatusLabel, run.status, locale)}</Badge>}</div>
        <time dateTime={run.scheduledAt}>{formatDateTime(run.scheduledAt, locale)}</time>
      </li>;
    })}</ol>
  </>;
}
