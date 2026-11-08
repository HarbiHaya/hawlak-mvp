import { useCallback, useEffect, useMemo, useState } from "react";
import type { PharmacistReviewRequested } from "@hawlak/contracts";

import fixture from "../../../fixtures/approved-plan.abu-mohammed.json";
import {
  HawlakApi,
  HawlakApiError,
  type AudioFirstDraft,
  type DialectCode,
  type ReviewOutcome,
  type SyntheticPlan,
  type VoiceOptions,
} from "./api";
import { mergeReviewEvents } from "./review-queue";

const API_URL = "http://127.0.0.1:3000";
const SYNTHETIC_PLAN = fixture as unknown as SyntheticPlan;

type Workspace = "send" | "review" | "connection";
type DemoStage = "setup" | "generating" | "review" | "sending" | "sent";

const outcomeLabels: Record<ReviewOutcome, string> = {
  matched: "مطابق للخطة",
  mismatch_found: "يوجد اختلاف",
  unclear_photo: "الصورة غير واضحة",
  contact_patient: "تواصل مع المريض",
};

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "brand--compact" : ""}`} aria-label="حولك">
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M40.31 16.39 A18 18 0 1 1 31.61 7.69" />
        <circle cx="24" cy="24" r="6.4" />
      </svg>
      <span>حولك</span>
      {!compact && <small>hawlak</small>}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof HawlakApiError) {
    const known: Record<string, string> = {
      case_conflict: "بيانات هذه الحالة تغيّرت. ابدئي تجربة جديدة.",
      script_checksum_conflict: "تغيّر النص بعد المراجعة. أعيدي إنشاء المسودة.",
      audio_first_generation_conflict: "تعذّر إنشاء الحزمة الصوتية لهذه الحالة.",
      storage_unavailable: "مخزن الصور غير متاح الآن.",
      request_failed_401: "رمز الدخول غير صحيح.",
    };
    return known[error.code] ?? `تعذّر إكمال الطلب (${error.code}).`;
  }
  if (error instanceof Error && error.name === "ZodError") {
    return "وصلت بيانات لا تطابق عقد حولك. أوقِفي العرض وراجعي الخادم.";
  }
  return "تعذّر الاتصال بالخادم. تأكدي أن الواجهة الخلفية تعمل.";
}

function TokenGate({ onConnect }: { onConnect: (token: string, options: VoiceOptions) => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const options = await new HawlakApi(API_URL, token).getVoiceOptions();
      onConnect(token, options);
      setToken("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="gate-shell">
      <section className="gate-story" aria-label="تعريف حولك">
        <BrandMark />
        <div className="voice-orbit" aria-hidden="true">
          <span className="orbit-dot orbit-dot--one" />
          <span className="orbit-dot orbit-dot--two" />
          <span className="orbit-dot orbit-dot--three" />
          <div className="orbit-core">
            <span>صوت</span>
            <b>صورة</b>
            <span>متابعة</span>
          </div>
        </div>
        <div>
          <p className="lead">خطة خروج يسمعها المريض، ويتابعها الفريق.</p>
          <p className="sublead">نموذج ببيانات اصطناعية فقط · لا يُستخدم للرعاية الطبية.</p>
        </div>
      </section>

      <section className="gate-panel">
        <div className="gate-panel__content">
          <p className="section-index">الدخول إلى العرض</p>
          <h1>ابدئي من هنا</h1>
          <p>شغّلي الواجهة الخلفية، ثم الصقي رمز العرض المحلي. يبقى الرمز في ذاكرة الصفحة فقط.</p>
          <label htmlFor="token">رمز الواجهة الخلفية</label>
          <input
            id="token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && token && void connect()}
            placeholder="ألصقي INTERNAL_API_TOKEN"
          />
          {error && <div className="notice notice--error">{error}</div>}
          <button className="button button--primary" disabled={!token || busy} onClick={() => void connect()}>
            {busy ? "جارٍ التحقق…" : "فتح لوحة حولك"}
          </button>
          <div className="privacy-note">
            <span aria-hidden="true">●</span>
            لا نحفظ الرمز في المتصفح ولا نضعه في عنوان الصفحة.
          </div>
        </div>
      </section>
    </main>
  );
}

function Sidebar({
  workspace,
  onChange,
  reviewCount,
  onLock,
}: {
  workspace: Workspace;
  onChange: (workspace: Workspace) => void;
  reviewCount: number;
  onLock: () => void;
}) {
  return (
    <aside className="sidebar">
      <BrandMark compact />
      <nav aria-label="مساحات العمل">
        <button className={workspace === "send" ? "active" : ""} onClick={() => onChange("send")}>
          <span>إرسال خطة الخروج</span><b>＋</b>
        </button>
        <button className={workspace === "review" ? "active" : ""} onClick={() => onChange("review")}>
          <span>مراجعة الصيدلي</span><b className="count">{reviewCount}</b>
        </button>
        <button className={workspace === "connection" ? "active" : ""} onClick={() => onChange("connection")}>
          <span>ربط واتساب</span><b className="status-dot" aria-label="وضع تجريبي" />
        </button>
      </nav>
      <div className="sidebar__bottom">
        <span className="synthetic-chip">بيانات اصطناعية</span>
        <button className="lock-button" onClick={onLock}>قفل اللوحة</button>
      </div>
    </aside>
  );
}

function SendWorkspace({ api, options }: { api: HawlakApi; options: VoiceOptions }) {
  const [recipient, setRecipient] = useState("");
  const [dialect, setDialect] = useState<DialectCode>("ar-SA-najdi");
  const [draft, setDraft] = useState<AudioFirstDraft | null>(null);
  const [stage, setStage] = useState<DemoStage>("setup");
  const [approved, setApproved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageIds, setMessageIds] = useState<string[]>([]);

  const validPhone = /^\+[1-9]\d{7,14}$/.test(recipient);

  async function generate() {
    setStage("generating");
    setError(null);
    try {
      const runId = `${Date.now().toString(36)}${crypto.randomUUID().slice(0, 6)}`;
      const created = await api.createCase(SYNTHETIC_PLAN, recipient, dialect, runId);
      const generated = await api.generateAudioFirst(created.caseId);
      setDraft(generated);
      setStage("review");
    } catch (caught) {
      setError(errorMessage(caught));
      setStage("setup");
    }
  }

  async function approveAndSend() {
    if (!draft || !approved) return;
    setStage("sending");
    setError(null);
    try {
      const result = await api.approveAudioFirst(
        draft,
        "demo-operator-haya",
        `voice-pack-${crypto.randomUUID()}`,
      );
      setMessageIds(result.messageIds);
      setStage("sent");
    } catch (caught) {
      setError(errorMessage(caught));
      setStage("review");
    }
  }

  function reset() {
    setDraft(null);
    setApproved(false);
    setMessageIds([]);
    setError(null);
    setStage("setup");
  }

  return (
    <div className="workspace">
      <header className="workspace-header">
        <div>
          <p>مسار المريض · عرض حي</p>
          <h1>أرسلي الخطة بصوت يفهمه المريض</h1>
        </div>
        <div className="provider-badge">
          <span className="live-pulse" />
          {options.voice.voiceLabel}
          <small>{options.voice.modelId}</small>
        </div>
      </header>

      <div className="step-track" aria-label="تقدم الإرسال">
        {["إعداد الحالة", "مراجعة الصوت", "إرسال آمن"].map((label, index) => {
          const current = stage === "setup" || stage === "generating" ? 0 : stage === "review" || stage === "sending" ? 1 : 2;
          return <div key={label} className={index <= current ? "done" : ""}><span>{index + 1}</span>{label}</div>;
        })}
      </div>

      {error && <div className="notice notice--error">{error}</div>}

      {(stage === "setup" || stage === "generating") && (
        <div className="setup-grid">
          <section className="panel panel--patient">
            <div className="panel-title"><span>١</span><div><h2>رقم الاختبار</h2><p>الرقم الذي انضم إلى Twilio Sandbox</p></div></div>
            <label htmlFor="recipient">رقم واتساب بصيغة دولية</label>
            <input
              id="recipient"
              dir="ltr"
              inputMode="tel"
              value={recipient}
              onChange={(event) => setRecipient(event.target.value.replace(/\s/g, ""))}
              placeholder="+9665XXXXXXXX"
            />
            {recipient && !validPhone && <small className="field-error">ابدئي بـ + ثم رمز الدولة والرقم.</small>}
            <div className="patient-brief">
              <div className="avatar">أم</div>
              <div><b>أبو محمد</b><span>حالة اصطناعية · ٣ علب دواء</span></div>
            </div>
          </section>

          <section className="panel panel--dialect">
            <div className="panel-title"><span>٢</span><div><h2>اللهجة الصوتية</h2><p>نفس الحقائق السريرية، بصياغة مألوفة</p></div></div>
            <div className="dialect-list" role="radiogroup" aria-label="اختيار اللهجة">
              {options.dialects.map((item) => (
                <button
                  key={item.code}
                  type="button"
                  role="radio"
                  aria-checked={dialect === item.code}
                  className={dialect === item.code ? "selected" : ""}
                  onClick={() => setDialect(item.code)}
                >
                  <span>{item.labelAr}</span><small>{item.labelEn}</small><i>{dialect === item.code ? "✓" : ""}</i>
                </button>
              ))}
            </div>
            <div className="safety-rule"><b>قاعدة حولك</b><span>الذكاء الاصطناعي يغيّر الصياغة فقط. لا يضيف أو يفسّر أي معلومة طبية.</span></div>
          </section>

          <button className="button button--primary button--wide" disabled={!validPhone || stage === "generating"} onClick={() => void generate()}>
            {stage === "generating" ? "جارٍ إعداد المسودتين الصوتيتين…" : "إنشاء حزمة الصوت للمراجعة"}
          </button>
        </div>
      )}

      {(stage === "review" || stage === "sending") && draft && (
        <section className="voice-review">
          <div className="review-intro">
            <div><p>جاهزة للمراجعة</p><h2>استمعي بعين المريض قبل الإرسال</h2></div>
            <div className={draft.factReport.passed ? "fact-pass" : "fact-fail"}>{draft.factReport.passed ? "✓ الحقائق مطابقة" : "توجد فروقات"}</div>
          </div>
          <div className="script-stack">
            {draft.scripts.map((script, index) => (
              <article className="script-card" key={script.artifactId}>
                <div className="voice-number"><span>{index + 1}</span><i /><i /><i /><i /></div>
                <div>
                  <p>{script.kind === "session_summary" ? "ملخص الجلسة وطلب الصور" : "التعافي وعلامات الخطر"}</p>
                  <blockquote>{script.spokenTextAr}</blockquote>
                  <small>بصمة النص: {script.scriptChecksum.slice(0, 22)}…</small>
                </div>
              </article>
            ))}
          </div>
          <label className="approval-check">
            <input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} />
            <span><b>راجعت النصّين كاملين وأوافق على إرسالهما كما هما</b><small>أي تعديل يتطلب إنشاء بصمة وموافقة جديدة.</small></span>
          </label>
          <div className="action-row">
            <button className="button button--ghost" onClick={reset}>إلغاء وإنشاء جديد</button>
            <button className="button button--primary" disabled={!approved || stage === "sending"} onClick={() => void approveAndSend()}>
              {stage === "sending" ? "جارٍ إنشاء الصوت والإرسال…" : "اعتماد وإرسال الصوتين"}
            </button>
          </div>
        </section>
      )}

      {stage === "sent" && (
        <section className="sent-state">
          <div className="sent-rings"><span>✓</span></div>
          <p>تم الإرسال إلى رقم الاختبار</p>
          <h2>وصلت رسالتان صوتيتان، والخطوة التالية هي صور علب الدواء.</h2>
          <div className="message-receipts">{messageIds.map((id, index) => <span key={id}>الصوت {index + 1} · {id.slice(-10)}</span>)}</div>
          <button className="button button--primary" onClick={reset}>بدء تجربة جديدة</button>
        </section>
      )}
    </div>
  );
}

function MedicinePhoto({ api, mediaId }: { api: HawlakApi; mediaId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let active = true;
    void api.getMedia(mediaId).then((blob) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => active && setFailed(true));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, mediaId]);

  if (failed) return <div className="photo-fallback">تعذّر تحميل الصورة</div>;
  if (!url) return <div className="photo-loading" aria-label="جارٍ تحميل الصورة" />;
  return <img src={url} alt="صورة علبة دواء أرسلها المريض" />;
}

function ReviewWorkspace({ api }: { api: HawlakApi }) {
  const [events, setEvents] = useState<PharmacistReviewRequested[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeEvent, setActiveEvent] = useState<string | null>(null);
  const [completed, setCompleted] = useState<Record<string, ReviewOutcome>>({});
  const [reminders, setReminders] = useState<Record<string, "sending" | "sent">>({});

  const poll = useCallback(async () => {
    try {
      const page = await api.listReviewEvents(cursor);
      setEvents((current) => mergeReviewEvents(current, page.data));
      setCursor(page.nextCursor);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [api, cursor]);

  useEffect(() => {
    void poll();
    const timer = window.setInterval(() => void poll(), 8000);
    return () => window.clearInterval(timer);
  }, [poll]);

  async function decide(event: PharmacistReviewRequested, outcome: ReviewOutcome) {
    setActiveEvent(event.eventId);
    setError(null);
    try {
      await api.recordOutcome(
        event.eventId,
        outcome,
        "demo-pharmacist-retaj",
        null,
        `review-${event.eventId}-${crypto.randomUUID()}`,
      );
      setCompleted((current) => ({ ...current, [event.eventId]: outcome }));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setActiveEvent(null);
    }
  }

  async function sendReminder(event: PharmacistReviewRequested) {
    const photo = event.medicinePhotos[0];
    if (!photo) return;
    setReminders((current) => ({ ...current, [event.eventId]: "sending" }));
    setError(null);
    try {
      const occurrence = `demo-${Date.now().toString(36)}`;
      await api.sendPhotoReminder(
        event.case.caseId,
        photo.mediaId,
        occurrence,
        `reminder-${event.eventId}-${crypto.randomUUID()}`,
      );
      setReminders((current) => ({ ...current, [event.eventId]: "sent" }));
    } catch (caught) {
      setReminders((current) => {
        const next = { ...current };
        delete next[event.eventId];
        return next;
      });
      setError(errorMessage(caught));
    }
  }

  return (
    <div className="workspace">
      <header className="workspace-header">
        <div><p>قائمة العمل · تتحدث تلقائياً</p><h1>صور تحتاج قرار الصيدلي</h1></div>
        <button className="button button--ghost" disabled={loading} onClick={() => void poll()}>{loading ? "جارٍ التحديث…" : "تحديث الآن"}</button>
      </header>
      {error && <div className="notice notice--error">{error}</div>}
      {!loading && events.length === 0 && (
        <section className="empty-state"><span>◎</span><h2>لا توجد صور تنتظر المراجعة</h2><p>عندما يرسل المريض الصور المطلوبة، تظهر هنا تلقائياً.</p></section>
      )}
      <div className="review-list">
        {events.map((event) => (
          <article className="review-task" key={event.eventId}>
            <header>
              <div className="avatar avatar--blue">{event.case.patientAlias.slice(0, 1)}</div>
              <div><h2>{event.case.patientAlias}</h2><p>{event.case.phoneE164Masked} · الخطة {event.approvedPlan.version}</p></div>
              <div className="photo-count"><b>{event.case.receivedBoxCount}/{event.case.expectedBoxCount}</b><span>صور مستلمة</span></div>
            </header>
            <div className="photo-strip">
              {event.medicinePhotos.map((photo) => <MedicinePhoto key={photo.mediaId} api={api} mediaId={photo.mediaId} />)}
            </div>
            <div className="reminder-action">
              <div>
                <b>اختبار تذكير الجرعة</b>
                <span>يرسل صوتاً يشرح: ١ أخذتها، ٢ لسه — ثم نفس صورة الدواء.</span>
              </div>
              <button
                className="button button--ghost"
                disabled={!event.medicinePhotos.length || reminders[event.eventId] === "sending" || reminders[event.eventId] === "sent"}
                onClick={() => void sendReminder(event)}
              >
                {reminders[event.eventId] === "sending" ? "جارٍ الإرسال…" : reminders[event.eventId] === "sent" ? "✓ أُرسل التذكير" : "إرسال التذكير الآن"}
              </button>
            </div>
            {completed[event.eventId] ? (
              <div className="decision-complete">✓ سُجل القرار: {outcomeLabels[completed[event.eventId]]}</div>
            ) : (
              <div className="decision-grid">
                {(Object.keys(outcomeLabels) as ReviewOutcome[]).map((outcome) => (
                  <button
                    key={outcome}
                    disabled={activeEvent === event.eventId}
                    className={outcome === "matched" ? "decision decision--positive" : outcome === "mismatch_found" ? "decision decision--danger" : "decision"}
                    onClick={() => void decide(event, outcome)}
                  >
                    {outcomeLabels[outcome]}
                  </button>
                ))}
              </div>
            )}
            <footer><span>وصلت {new Date(event.occurredAt).toLocaleString("ar-SA")}</span><span>القرار الطبي يبقى للصيدلي</span></footer>
          </article>
        ))}
      </div>
    </div>
  );
}

function ConnectionWorkspace() {
  return (
    <div className="workspace">
      <header className="workspace-header"><div><p>الربط · قرار المنتج</p><h1>من الاختبار إلى هوية حولك</h1></div></header>
      <div className="connection-grid">
        <section className="connection-card connection-card--active">
          <span className="connection-state">يعمل الآن</span>
          <h2>Twilio Sandbox</h2>
          <p>مناسب للعرض واختبار الدورة كاملة، لكنه رقم مشترك ويعرض اسم وصورة Twilio.</p>
          <ul><li>لا يحتاج اعتماد شركة</li><li>المستلم ينضم بكلمة join</li><li>جلسة الاختبار تُجدد كل ٣ أيام</li></ul>
        </section>
        <section className="connection-card">
          <span className="connection-state connection-state--next">الخطوة التالية</span>
          <h2>رقم حولك وهوية حولك</h2>
          <p>يتطلب تسجيل WhatsApp Sender في Twilio. بعدها يمكن وضع الاسم والصورة وربط webhook نفسه.</p>
          <ol><li>رقم يستقبل SMS أو مكالمة OTP</li><li>Twilio Self Sign-up وربط Meta</li><li>رفع صورة مربعة 640×640</li><li>تغيير TWILIO_WHATSAPP_FROM فقط</li></ol>
        </section>
      </div>
      <section className="profile-preview">
        <div className="profile-icon"><BrandMark compact /></div>
        <div><p>الاسم المقترح للمرسل</p><h2>حولك | Hawlak</h2><span>مساعد متابعة الخروج — نموذج تجريبي</span></div>
        <div className="profile-note">لن تظهر هذه الهوية على Sandbox. جهزناها للمرسل الحقيقي.</div>
      </section>
    </div>
  );
}

export function App() {
  const [token, setToken] = useState<string | null>(null);
  const [options, setOptions] = useState<VoiceOptions | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>("send");

  const api = useMemo(() => token ? new HawlakApi(API_URL, token) : null, [token]);

  if (!token || !options || !api) {
    return <TokenGate onConnect={(nextToken, nextOptions) => { setToken(nextToken); setOptions(nextOptions); }} />;
  }

  return (
    <div className="app-shell">
      <Sidebar workspace={workspace} onChange={setWorkspace} reviewCount={0} onLock={() => { setToken(null); setOptions(null); }} />
      <main className="app-main">
        {workspace === "send" && <SendWorkspace api={api} options={options} />}
        {workspace === "review" && <ReviewWorkspace api={api} />}
        {workspace === "connection" && <ConnectionWorkspace />}
      </main>
    </div>
  );
}
