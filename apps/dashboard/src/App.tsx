import { useCallback, useMemo, useState } from "react";

import { Logo } from "./components/Logo";
import type { MediaLoader } from "./components/MedicinePhoto";
import { Chip } from "./components/Notice";
import type { SubmitOutcome } from "./components/OutcomePanel";
import { ReviewScreen } from "./components/ReviewScreen";
import { SetupScreen } from "./components/SetupScreen";
import { TokenGate, type Session } from "./components/TokenGate";
import { useReviewQueue } from "./hooks/useReviewQueue";
import { OfflineMediaError } from "./lib/errors";
import { newIdempotencyKey } from "./lib/idempotency";
import type { RecordedReview } from "./lib/queue";

export default function App() {
  // Session (and therefore the token inside ApiClient) lives only in memory.
  const [session, setSession] = useState<Session | null>(null);
  if (!session) return <TokenGate onConnect={setSession} />;
  return <Workspace session={session} onLock={() => setSession(null)} />;
}

type Tab = "setup" | "review";

function Workspace({ session, onLock }: { session: Session; onLock: () => void }) {
  const offline = session.kind === "fixture";
  const [tab, setTab] = useState<Tab>(offline ? "review" : "setup");
  const queue = useReviewQueue(session);
  const { markReviewed } = queue;

  const loadMedia: MediaLoader = useMemo(
    () =>
      session.kind === "api"
        ? (mediaId, signal) => session.client.getMedia(mediaId, signal)
        : () => Promise.reject(new OfflineMediaError()),
    [session],
  );

  const submitOutcome = useCallback(
    (eventId: string): SubmitOutcome =>
      async ({ outcome, reviewerId, note, idempotencyKey }) => {
        let review: RecordedReview;
        if (session.kind === "api") {
          const data = await session.client.recordOutcome(
            eventId,
            { eventVersion: 1, outcome, reviewerId, note },
            idempotencyKey,
          );
          review = {
            outcomeId: data.outcomeId,
            outcome: data.outcome,
            reviewerId: data.reviewerId,
            note: data.note,
            recordedAt: data.recordedAt,
            simulated: false,
          };
        } else {
          await new Promise((resolve) => setTimeout(resolve, 300));
          review = {
            outcomeId: newIdempotencyKey("local"),
            outcome,
            reviewerId,
            note,
            recordedAt: new Date().toISOString(),
            simulated: true,
          };
        }
        markReviewed(eventId, review);
        return review;
      },
    [session, markReviewed],
  );

  const pending = queue.tasks.filter((t) => !t.review).length;

  return (
    <div className="app">
      <div className="synthetic-bar">نموذج تجريبي ببيانات اصطناعية فقط · ليس للاستخدام السريري</div>
      <header className="topbar">
        <div className="brand">
          <Logo />
          <span className="brand__name">حولك</span>
          <span className="brand__tag">لوحة التشغيل والمراجعة</span>
        </div>
        <nav className="tabs" role="tablist" aria-label="الأقسام">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "setup"}
            className={`tab ${tab === "setup" ? "is-on" : ""}`}
            onClick={() => setTab("setup")}
          >
            تجهيز الحالة
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "review"}
            className={`tab ${tab === "review" ? "is-on" : ""}`}
            onClick={() => setTab("review")}
          >
            مراجعة الصيدلي
            {pending > 0 ? <span className="tab__badge">{pending}</span> : null}
          </button>
        </nav>
        <div className="topbar__end">
          {offline ? (
            <Chip tone="grey">بدون خادم</Chip>
          ) : (
            <Chip tone="green">
              متصل · <bdi dir="ltr">{session.client.origin}</bdi>
            </Chip>
          )}
          <button className="btn btn--ghost" type="button" onClick={onLock}>
            قفل وإزالة الرمز
          </button>
        </div>
      </header>

      <main className="content">
        {tab === "setup" ? (
          session.kind === "api" ? (
            <SetupScreen client={session.client} />
          ) : (
            <div className="empty">
              <div className="empty__title">التجهيز يتطلب الاتصال بالخادم</div>
              <p className="muted">
                إنشاء الحالة وتوليد النص واعتماده تتم عبر واجهة حولك البرمجية. اقفل اللوحة ثم أدخل رمز العرض للاتصال.
              </p>
            </div>
          )
        ) : (
          <ReviewScreen queue={queue} loadMedia={loadMedia} submitOutcome={submitOutcome} offline={offline} />
        )}
      </main>
    </div>
  );
}
