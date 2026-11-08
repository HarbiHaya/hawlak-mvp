import { useEffect, useState } from "react";

import type { ReviewQueueHandle } from "../hooks/useReviewQueue";
import { DEMO_PLAN } from "../lib/demoCase";
import { OUTCOME_LABELS, REASON_LABELS, formatDateTime, formatTime, shortHash } from "../lib/format";
import type { ReviewTask } from "../lib/queue";
import { MedicinePhoto, type MediaLoader } from "./MedicinePhoto";
import { Chip, Notice, Spinner } from "./Notice";
import { OutcomePanel, type SubmitOutcome } from "./OutcomePanel";

export function ReviewScreen({
  queue,
  loadMedia,
  submitOutcome,
  offline,
}: {
  queue: ReviewQueueHandle;
  loadMedia: MediaLoader;
  submitOutcome: (eventId: string) => SubmitOutcome;
  offline: boolean;
}) {
  const { tasks, sync, state } = queue;
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Select the first pending task once something arrives.
  useEffect(() => {
    if (selectedId && state.tasks[selectedId]) return;
    if (tasks.length > 0) setSelectedId(tasks[0].event.eventId);
  }, [tasks, selectedId, state.tasks]);

  const selected = selectedId ? state.tasks[selectedId] : undefined;
  const pending = tasks.filter((t) => !t.review).length;
  const firstLoad = state.lastSyncAt === null;

  return (
    <div className="review">
      <header className="page-head">
        <div>
          <h1>قائمة مراجعة الصيدلي</h1>
          <p className="muted">
            {pending > 0 ? `${pending} بانتظار المراجعة` : "لا يوجد ما ينتظر المراجعة"}
            {state.lastSyncAt ? ` · آخر تحديث ${formatTime(state.lastSyncAt)}` : ""}
            {offline ? " · وضع العرض بدون خادم" : " · تحديث تلقائي كل 5 ثوانٍ"}
          </p>
        </div>
        <div className="page-head__actions">
          {sync.phase === "loading" ? <Spinner label="جارٍ التحديث…" /> : null}
          <button className="btn btn--secondary" type="button" onClick={queue.refresh} disabled={sync.phase === "loading"}>
            تحديث الآن
          </button>
        </div>
      </header>

      {sync.phase === "error" && sync.error ? (
        <Notice tone="red" role="alert" title={sync.unauthorized ? "توقف التحديث التلقائي" : "تعذّر تحديث القائمة"}>
          {sync.error}
          {!sync.unauthorized ? " ستُعاد المحاولة تلقائيًا." : null}
        </Notice>
      ) : null}

      {state.invalid.length > 0 ? (
        <Notice tone="amber" role="alert" title={`عناصر رُفضت لأنها لا تطابق العقد (${state.invalid.length})`}>
          <p>لم تُضف هذه العناصر إلى القائمة. أبلغ فريق الخادم بها.</p>
          <ul className="diff">
            {state.invalid.map((item) => (
              <li key={item.key}>
                <code dir="ltr">{item.eventId ?? "بدون eventId"}</code>: <bdi dir="ltr">{item.issues.slice(0, 3).join(" · ")}</bdi>
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {firstLoad && sync.phase !== "error" ? <Spinner label="جارٍ تحميل قائمة المراجعة…" /> : null}

      {!firstLoad && tasks.length === 0 ? (
        <div className="empty">
          <div className="empty__title">لا توجد طلبات مراجعة بعد</div>
          <p className="muted">يظهر الطلب هنا عندما يرسل المريض صور العلب المتوقعة.</p>
        </div>
      ) : null}

      {tasks.length > 0 ? (
        <div className="review__layout">
          <nav className="queue" aria-label="طلبات المراجعة">
            {tasks.map((task) => (
              <QueueItem
                key={task.event.eventId}
                task={task}
                selected={task.event.eventId === selectedId}
                onSelect={() => setSelectedId(task.event.eventId)}
              />
            ))}
          </nav>
          {selected ? (
            <ReviewDetail
              key={selected.event.eventId}
              task={selected}
              loadMedia={loadMedia}
              onSubmit={submitOutcome(selected.event.eventId)}
              offline={offline}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function QueueItem({ task, selected, onSelect }: { task: ReviewTask; selected: boolean; onSelect: () => void }) {
  const { event, review } = task;
  const incomplete = event.case.receivedBoxCount < event.case.expectedBoxCount;
  return (
    <button type="button" className={`queue__item ${selected ? "is-on" : ""}`} aria-current={selected} onClick={onSelect}>
      <span className="queue__top">
        <span className="queue__alias">{event.case.patientAlias}</span>
        {review ? (
          <Chip tone={OUTCOME_LABELS[review.outcome].tone}>{OUTCOME_LABELS[review.outcome].label}</Chip>
        ) : (
          <Chip tone="amber">بانتظار المراجعة</Chip>
        )}
      </span>
      <span className="queue__meta">
        <bdi dir="ltr">{event.case.phoneE164Masked}</bdi> · {formatTime(event.occurredAt)}
      </span>
      <span className={`queue__meta ${incomplete ? "text-amber" : ""}`}>
        الصور {event.case.receivedBoxCount} من {event.case.expectedBoxCount}
      </span>
    </button>
  );
}

function ReviewDetail({
  task,
  loadMedia,
  onSubmit,
  offline,
}: {
  task: ReviewTask;
  loadMedia: MediaLoader;
  onSubmit: SubmitOutcome;
  offline: boolean;
}) {
  const { event } = task;
  const { case: c, approvedPlan } = event;
  const incomplete = c.receivedBoxCount < c.expectedBoxCount;
  const knownPlan = approvedPlan.sourceHash === DEMO_PLAN.approvedPlan.source.sourceHash ? DEMO_PLAN : null;

  return (
    <article className="detail">
      <header className="detail__head">
        <div>
          <h2 className="detail__alias">{c.patientAlias}</h2>
          <div className="muted">
            <bdi dir="ltr">{c.phoneE164Masked}</bdi> · الحالة <code dir="ltr">{c.caseId}</code>
          </div>
        </div>
        <div className="detail__chips">
          <Chip tone="blue">{REASON_LABELS[event.reviewReason]}</Chip>
          <Chip tone={incomplete ? "amber" : "grey"}>
            الصور {c.receivedBoxCount} من {c.expectedBoxCount}
          </Chip>
        </div>
      </header>

      <dl className="kv kv--grid">
        <dt>الخطة المعتمدة</dt>
        <dd>
          <code dir="ltr">{approvedPlan.planId}</code> · الإصدار {approvedPlan.version}
        </dd>
        <dt>بصمة المصدر</dt>
        <dd>
          <code dir="ltr" title={approvedPlan.sourceHash}>
            {shortHash(approvedPlan.sourceHash)}
          </code>
        </dd>
        <dt>وقت الحدث (التدقيق)</dt>
        <dd>{formatDateTime(event.occurredAt)}</dd>
        <dt>معرّف الحدث</dt>
        <dd>
          <code dir="ltr">{event.eventId}</code> · v{event.eventVersion}
        </dd>
      </dl>

      {knownPlan ? (
        <div className="plan-ref">
          <div className="label">أدوية الخطة المعتمدة (البصمة مطابقة لملف الحالة التجريبية)</div>
          <ul>
            {knownPlan.approvedPlan.clinicalFacts.newMedicines.map((m) => (
              <li key={m.itemId}>
                <bdi dir="ltr">{`${m.name} ${m.strength} · ${m.dose} · ${m.frequency} · ${m.timing}`}</bdi>
              </li>
            ))}
            {knownPlan.approvedPlan.clinicalFacts.stoppedMedicines.map((name) => (
              <li key={name} className="text-red">
                أوقفه الطبيب: <bdi dir="ltr">{name}</bdi>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {incomplete ? (
        <Notice tone="amber" title="صور ناقصة">
          وصلت {c.receivedBoxCount} من {c.expectedBoxCount} صور متوقعة.
        </Notice>
      ) : null}

      <Notice tone="blue">قارن كل صورة بالخطة المعتمدة. لا تُفسَّر الصور آليًا؛ القرار للصيدلي وحده.</Notice>

      {event.medicinePhotos.length === 0 ? (
        <p className="muted">لا توجد صور مرفقة بهذا الحدث.</p>
      ) : (
        <div className="photos">
          {event.medicinePhotos.map((photo, i) => (
            <MedicinePhoto key={photo.mediaId} mediaId={photo.mediaId} index={i + 1} load={loadMedia} />
          ))}
        </div>
      )}

      <OutcomePanel review={task.review} onSubmit={onSubmit} simulated={offline} />
    </article>
  );
}
