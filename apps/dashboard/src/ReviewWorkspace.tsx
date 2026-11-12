import { useCallback, useEffect, useState } from "react";
import type { PharmacistReviewRequested } from "@hawlak/contracts";

import {
  HawlakApi,
  HawlakApiError,
  type ReviewOutcome,
  type TimelineEntry,
} from "./api";
import { mergeReviewEvents } from "./review-queue";

const outcomeLabels: Record<ReviewOutcome, string> = {
  matched: "مطابق للخطة",
  mismatch_found: "يوجد اختلاف",
  unclear_photo: "الصورة غير واضحة",
  contact_patient: "تواصل مع المريض",
};

const deliveryLabels: Record<string, string> = {
  queued: "في قائمة الإرسال",
  sent: "أُرسل من المزوّد",
  delivered: "وصل إلى الهاتف",
  read: "قُرئ",
  failed: "فشل التسليم",
  undelivered: "لم يصل",
};

function errorMessage(error: unknown): string {
  if (error instanceof HawlakApiError) {
    return `تعذّر إكمال الطلب (${error.code}).`;
  }
  if (error instanceof Error && error.name === "ZodError") {
    return "وصلت بيانات لا تطابق عقد حولك. أوقِفي العرض وراجعي الخادم.";
  }
  return "تعذّر الاتصال بالخادم. تأكدي أن الواجهة الخلفية تعمل.";
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

function CaseAuditSummary({
  api,
  caseId,
  refreshSignal,
}: {
  api: HawlakApi;
  caseId: string;
  refreshSignal?: string;
}) {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await api.getCaseTimeline(caseId);
        if (active) setEntries(result.data);
      } catch {
        // The task remains actionable even if the audit poll is temporarily unavailable.
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, caseId, refreshSignal]);

  const reminders = entries.filter(
    (entry) =>
      entry.type.startsWith("whatsapp_outbound_") &&
      String(entry.details.step ?? "").startsWith("medication_"),
  );
  const latestReminder = reminders.at(-1);
  const latestChoice = entries.filter((entry) => entry.details.choice).at(-1);

  return (
    <div className="case-audit" aria-live="polite">
      <div>
        <b>سجل التذكير</b>
        <span>
          {latestReminder
            ? deliveryLabels[latestReminder.details.deliveryStatus ?? "queued"] ?? latestReminder.details.deliveryStatus
            : "لم يُرسل تذكير لهذه الحالة بعد"}
        </span>
      </div>
      <div>
        <b>آخر رد من المريض</b>
        <span>
          {latestChoice?.details.choice === "taken"
            ? "١ · أخذتها"
            : latestChoice?.details.choice === "not_yet"
              ? "٢ · لم آخذها بعد"
              : "بانتظار الضغط على ١ أو ٢"}
        </span>
      </div>
    </div>
  );
}

export function ReviewWorkspace({
  api,
  onCountChange,
}: {
  api: HawlakApi;
  onCountChange: (count: number) => void;
}) {
  const [events, setEvents] = useState<PharmacistReviewRequested[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeEvent, setActiveEvent] = useState<string | null>(null);
  const [completed, setCompleted] = useState<Record<string, ReviewOutcome>>({});
  const [reminders, setReminders] = useState<Record<string, "sending" | "sent">>({});
  const [selectedPhotos, setSelectedPhotos] = useState<Record<string, string>>({});

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

  useEffect(() => {
    onCountChange(events.filter((event) => !completed[event.eventId]).length);
  }, [completed, events, onCountChange]);

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
    const selectedId = selectedPhotos[event.eventId] ?? event.medicinePhotos[0]?.mediaId;
    if (!selectedId) return;
    setReminders((current) => ({ ...current, [event.eventId]: "sending" }));
    setError(null);
    try {
      const occurrence = `demo-${Date.now().toString(36)}`;
      await api.sendPhotoReminder(
        event.case.caseId,
        selectedId,
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
        {events.map((event) => {
          const selectedId = selectedPhotos[event.eventId] ?? event.medicinePhotos[0]?.mediaId;
          return (
            <article className="review-task" key={event.eventId}>
              <header>
                <div className="avatar avatar--blue">{event.case.patientAlias.slice(0, 1)}</div>
                <div><h2>{event.case.patientAlias}</h2><p>{event.case.phoneE164Masked} · الخطة {event.approvedPlan.version}</p></div>
                <div className="photo-count"><b>{event.case.receivedBoxCount}/{event.case.expectedBoxCount}</b><span>صور مستلمة</span></div>
              </header>
              <div className="photo-strip" aria-label="اختاري صورة الدواء للتذكير">
                {event.medicinePhotos.map((photo) => (
                  <button
                    type="button"
                    key={photo.mediaId}
                    className={`medicine-photo ${selectedId === photo.mediaId ? "selected" : ""}`}
                    aria-pressed={selectedId === photo.mediaId}
                    onClick={() => setSelectedPhotos((current) => ({ ...current, [event.eventId]: photo.mediaId }))}
                  >
                    <MedicinePhoto api={api} mediaId={photo.mediaId} />
                    <span>{selectedId === photo.mediaId ? "✓ صورة التذكير" : "اختيار للتذكير"}</span>
                  </button>
                ))}
              </div>
              <div className="reminder-action">
                <div>
                  <b>اختبار تذكير الجرعة</b>
                  <span>يرسل صوتاً يشرح: ١ أخذتها، ٢ لسه — ثم الصورة المختارة أعلاه.</span>
                </div>
                <button
                  className="button button--ghost"
                  disabled={!selectedId || reminders[event.eventId] === "sending" || reminders[event.eventId] === "sent"}
                  onClick={() => void sendReminder(event)}
                >
                  {reminders[event.eventId] === "sending" ? "جارٍ الإرسال…" : reminders[event.eventId] === "sent" ? "✓ قُبل طلب التذكير" : "إرسال التذكير الآن"}
                </button>
              </div>
              <CaseAuditSummary
                api={api}
                caseId={event.case.caseId}
                refreshSignal={reminders[event.eventId]}
              />
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
          );
        })}
      </div>
    </div>
  );
}
