import { useEffect, useState } from "react";

import type { ApiClient, CreateCaseResult } from "../lib/api";
import { DEMO_PLAN, DEMO_RECIPIENT_PLACEHOLDER, PHONE_PATTERN, buildCaseRequest } from "../lib/demoCase";
import { describeError } from "../lib/errors";
import { formatDateTime, shortHash } from "../lib/format";
import type { GeneratedScript, VoiceOptions } from "../lib/schemas";
import { ApprovalStep } from "./ApprovalStep";
import { Chip, Notice, Spinner } from "./Notice";

type Load<T> = { status: "idle" } | { status: "busy" } | { status: "done"; data: T } | { status: "error"; error: string };

const facts = DEMO_PLAN.approvedPlan.clinicalFacts;

function PlanSummary() {
  return (
    <div className="plan">
      <div className="plan__head">
        <div>
          <div className="plan__alias">{DEMO_PLAN.case.patientAlias}</div>
          <div className="muted small">
            خطة معتمدة · الإصدار {DEMO_PLAN.approvedPlan.version} · اعتمدها{" "}
            <bdi dir="ltr">{DEMO_PLAN.approvedPlan.approvedBy}</bdi> · {formatDateTime(DEMO_PLAN.approvedPlan.approvedAt)}
          </div>
        </div>
        <Chip tone="amber">بيانات اصطناعية</Chip>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>الدواء</th>
            <th>التركيز</th>
            <th>الجرعة</th>
            <th>التكرار</th>
            <th>التوقيت</th>
          </tr>
        </thead>
        <tbody>
          {facts.newMedicines.map((m) => (
            <tr key={m.itemId}>
              <td>
                <bdi dir="ltr">{m.name}</bdi>
              </td>
              <td>
                <bdi dir="ltr">{m.strength}</bdi>
              </td>
              <td>
                <bdi dir="ltr">{m.dose}</bdi>
              </td>
              <td>
                <bdi dir="ltr">{m.frequency}</bdi>
              </td>
              <td>
                <bdi dir="ltr">{m.timing}</bdi>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="plan__grid">
        <div>
          <div className="label">أدوية أوقفها الطبيب</div>
          {facts.stoppedMedicines.map((name) => (
            <div key={name}>
              <bdi dir="ltr">{name}</bdi>
            </div>
          ))}
        </div>
        <div>
          <div className="label label--red">علامات الخطر · اتصل بـ {facts.emergencyNumber}</div>
          {facts.redFlags.map((flag) => (
            <div key={flag}>
              <bdi dir="ltr">{flag}</bdi>
            </div>
          ))}
        </div>
        <div>
          <div className="label">تعليمات</div>
          {[...facts.activityInstructions, ...facts.dietInstructions].map((line) => (
            <div key={line}>
              <bdi dir="ltr">{line}</bdi>
            </div>
          ))}
        </div>
      </div>
      <div className="muted small">
        بصمة المصدر <code dir="ltr">{shortHash(DEMO_PLAN.approvedPlan.source.sourceHash)}</code>
      </div>
    </div>
  );
}

export function SetupScreen({ client }: { client: ApiClient }) {
  const [options, setOptions] = useState<Load<VoiceOptions>>({ status: "busy" });
  const [dialect, setDialect] = useState<string | null>(null);
  const [recipient, setRecipient] = useState(DEMO_RECIPIENT_PLACEHOLDER);
  const [caseState, setCaseState] = useState<Load<CreateCaseResult>>({ status: "idle" });
  const [script, setScript] = useState<Load<GeneratedScript>>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setOptions({ status: "busy" });
    client
      .getVoiceOptions(ctrl.signal)
      .then((data) => {
        setOptions({ status: "done", data });
        setDialect((current) => {
          if (current) return current;
          const preferred = data.dialects.find((d) => d.code === DEMO_PLAN.case.dialectCode);
          return (preferred ?? data.dialects[0]).code;
        });
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setOptions({ status: "error", error: describeError(err) });
      });
    return () => ctrl.abort();
  }, [client, attempt]);

  const phoneOk = PHONE_PATTERN.test(recipient.trim());
  const caseId = caseState.status === "done" ? caseState.data.data.caseId : null;

  function resetDownstream() {
    setCaseState({ status: "idle" });
    setScript({ status: "idle" });
  }

  async function createCase() {
    if (!dialect || !phoneOk || caseState.status === "busy") return;
    setCaseState({ status: "busy" });
    setScript({ status: "idle" });
    try {
      const data = await client.createCase(buildCaseRequest(dialect, recipient.trim()));
      setCaseState({ status: "done", data });
    } catch (err) {
      setCaseState({
        status: "error",
        error: describeError(err, {
          conflict: "توجد حالة بنفس المعرّف لكن ببيانات مختلفة (غالبًا رقم مختلف). استخدم الرقم السابق نفسه.",
        }),
      });
    }
  }

  async function generate() {
    if (!caseId || script.status === "busy") return;
    setScript({ status: "busy" });
    try {
      setScript({ status: "done", data: await client.generateScript(caseId) });
    } catch (err) {
      setScript({
        status: "error",
        error: describeError(err, {
          conflict: "رفض الخادم النص المولَّد لأن الحقائق السريرية تغيّرت أو الحالة غير جاهزة. أعد المحاولة.",
        }),
      });
    }
  }

  const voice = options.status === "done" ? options.data.voice : null;

  return (
    <div className="setup">
      <header className="page-head">
        <div>
          <h1>تجهيز الحالة التجريبية</h1>
          <p className="muted">
            اختر اللهجة، أنشئ الحالة، ولّد النص، ثم اعتمده بنفسك. لا يصل شيء إلى الهاتف قبل اعتماد النص الكامل.
          </p>
        </div>
      </header>

      <section className="step">
        <div className="step__num">1</div>
        <div className="step__body">
          <h2>لهجة الملاحظة الصوتية</h2>
          {options.status === "busy" ? <Spinner label="جارٍ تحميل اللهجات…" /> : null}
          {options.status === "error" ? (
            <Notice tone="red" role="alert" title="تعذّر تحميل اللهجات">
              {options.error}{" "}
              <button className="link" type="button" onClick={() => setAttempt((n) => n + 1)}>
                إعادة المحاولة
              </button>
            </Notice>
          ) : null}
          {options.status === "done" ? (
            <>
              <div className="choices" role="radiogroup" aria-label="اللهجة">
                {options.data.dialects.map((d) => (
                  <label key={d.code} className={`choice ${dialect === d.code ? "choice--on" : ""}`}>
                    <input
                      type="radio"
                      name="dialect"
                      value={d.code}
                      checked={dialect === d.code}
                      onChange={() => {
                        setDialect(d.code);
                        resetDownstream();
                      }}
                    />
                    <span className="choice__ar">{d.labelAr}</span>
                    <span className="choice__en" dir="ltr">
                      {d.labelEn} · {d.code}
                    </span>
                  </label>
                ))}
              </div>
              {voice ? (
                <p className="muted small">
                  الصوت المُعدّ في الخادم: <bdi dir="ltr">{voice.voiceLabel}</bdi> · النموذج{" "}
                  <bdi dir="ltr">{voice.modelId}</bdi> · اللغة <bdi dir="ltr">{voice.languageCode}</bdi>
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </section>

      <section className="step">
        <div className="step__num">2</div>
        <div className="step__body">
          <h2>الحالة والخطة المعتمدة</h2>
          <PlanSummary />
          <label className="field">
            <span className="field__label">رقم هاتف العرض (رقم اختبار مسموح فقط)</span>
            <input
              className="input input--ltr"
              dir="ltr"
              value={recipient}
              aria-invalid={!phoneOk}
              onChange={(e) => {
                setRecipient(e.target.value);
                resetDownstream();
              }}
              spellCheck={false}
            />
            {!phoneOk ? (
              <span className="field__error">بصيغة دولية مثل +9665XXXXXXXX</span>
            ) : (
              <span className="hint">لا تُدخل رقم مريض حقيقي.</span>
            )}
          </label>
          <div className="actions">
            <button
              className="btn btn--primary"
              type="button"
              disabled={!dialect || !phoneOk || caseState.status === "busy" || caseState.status === "done"}
              onClick={createCase}
            >
              {caseState.status === "busy" ? "جارٍ الإنشاء…" : "إنشاء الحالة التجريبية"}
            </button>
            {!dialect ? <span className="hint">اختر اللهجة أولًا.</span> : null}
          </div>
          {caseState.status === "error" ? (
            <Notice tone="red" role="alert" title="لم تُنشأ الحالة">
              {caseState.error}
            </Notice>
          ) : null}
          {caseState.status === "done" ? (
            <Notice tone="green" role="status" title={caseState.data.created ? "أُنشئت الحالة" : "الحالة موجودة مسبقًا بالبيانات نفسها"}>
              <code dir="ltr">{caseState.data.data.caseId}</code> · الخطة{" "}
              <code dir="ltr">{caseState.data.data.planId}</code> · الإصدار {caseState.data.data.version} · الحالة{" "}
              <bdi dir="ltr">{caseState.data.data.status}</bdi>
            </Notice>
          ) : null}
        </div>
      </section>

      <section className={`step ${caseId ? "" : "step--locked"}`}>
        <div className="step__num">3</div>
        <div className="step__body">
          <h2>توليد النص ومراجعته</h2>
          {!caseId ? <p className="hint">أنشئ الحالة أولًا.</p> : null}
          {caseId ? (
            <div className="actions">
              <button className="btn btn--secondary" type="button" disabled={script.status === "busy"} onClick={generate}>
                {script.status === "busy" ? "جارٍ التوليد…" : script.status === "done" ? "توليد نص جديد" : "توليد النص"}
              </button>
              {script.status === "done" ? <span className="hint">توليد نص جديد يُلغي النص الحالي ويتطلب اعتمادًا جديدًا.</span> : null}
            </div>
          ) : null}
          {script.status === "error" ? (
            <Notice tone="red" role="alert" title="تعذّر توليد النص">
              {script.error}
            </Notice>
          ) : null}
          {script.status === "done" ? <ScriptReview script={script.data} /> : null}
        </div>
      </section>

      <section className={`step ${script.status === "done" ? "" : "step--locked"}`}>
        <div className="step__num">4</div>
        <div className="step__body">
          <h2>الاعتماد والإرسال</h2>
          {script.status === "done" && caseId ? (
            <ApprovalStep
              key={script.data.artifactId}
              artifactId={script.data.artifactId}
              scriptChecksum={script.data.scriptChecksum}
              factPassed={script.data.factReport.passed}
              onApprove={(body, key) => client.approveAndSend(caseId, body, key)}
            />
          ) : (
            <p className="hint">يظهر الاعتماد بعد توليد النص ومراجعته.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function ScriptReview({ script }: { script: GeneratedScript }) {
  const { passed, differences } = script.factReport;
  return (
    <div className="script">
      <div className="script__meta">
        {passed ? <Chip tone="green">فحص الحقائق السريرية: مطابق</Chip> : <Chip tone="red">فحص الحقائق السريرية: غير مطابق</Chip>}
        <span className="muted small">
          بصمة النص <code dir="ltr">{script.scriptChecksum}</code>
        </span>
      </div>
      <div className="script__text" lang="ar" dir="rtl">
        {script.spokenTextAr}
      </div>
      <p className="hint">النص للقراءة فقط. لتغييره ولّد نصًا جديدًا؛ التعديل في المتصفح غير مسموح.</p>
      {differences.length > 0 ? (
        <Notice tone={passed ? "amber" : "red"} title={`فروقات في الحقائق (${differences.length})`}>
          <ul className="diff">
            {differences.map((d, i) => (
              <li key={`${d.path}-${i}`}>
                <code dir="ltr">{d.path}</code> · {d.kind}: <bdi dir="ltr">{JSON.stringify(d.source)}</bdi> ←{" "}
                <bdi dir="ltr">{JSON.stringify(d.output)}</bdi>
              </li>
            ))}
          </ul>
        </Notice>
      ) : (
        <p className="muted small">لا توجد فروقات بين النص والخطة المعتمدة.</p>
      )}
    </div>
  );
}
