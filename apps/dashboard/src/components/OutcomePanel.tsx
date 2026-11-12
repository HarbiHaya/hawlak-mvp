import { useRef, useState } from "react";

import { describeError } from "../lib/errors";
import { OUTCOME_LABELS, formatDateTime } from "../lib/format";
import { newIdempotencyKey } from "../lib/idempotency";
import type { RecordedReview } from "../lib/queue";
import { OUTCOMES, type Outcome } from "../lib/schemas";
import { Chip, Notice } from "./Notice";

export const DEFAULT_REVIEWER = "demo-pharmacist-01";

export type SubmitOutcome = (input: {
  outcome: Outcome;
  reviewerId: string;
  note: string | null;
  idempotencyKey: string;
}) => Promise<RecordedReview>;

/**
 * One pharmacist decision per event: choose an outcome, then confirm.
 * - A lock blocks double clicks while a request is in flight.
 * - Each confirm gets a new Idempotency-Key, except a retry of the exact same
 *   decision after a failure, which reuses the key so it stays replay-safe.
 * - After success the decision is shown and the controls lock.
 */
export function OutcomePanel({
  review,
  onSubmit,
  simulated = false,
}: {
  review: RecordedReview | null;
  onSubmit: SubmitOutcome;
  simulated?: boolean;
}) {
  const [choice, setChoice] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");
  const [reviewerId, setReviewerId] = useState(DEFAULT_REVIEWER);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const retry = useRef<{ signature: string; key: string } | null>(null);

  if (review) {
    const meta = OUTCOME_LABELS[review.outcome];
    return (
      <section className="outcome outcome--done" aria-label="قرار الصيدلي">
        <div className="outcome__head">
          <h3>قرار الصيدلي</h3>
          <Chip tone={meta.tone}>{meta.label}</Chip>
        </div>
        <p className="muted small">
          سُجّل {formatDateTime(review.recordedAt)} بواسطة <bdi dir="ltr">{review.reviewerId}</bdi>
          {review.simulated ? " · تسجيل محلي في وضع العرض بدون خادم" : null}
        </p>
        {review.note ? <p className="outcome__note">{review.note}</p> : null}
      </section>
    );
  }

  const trimmedNote = note.trim();
  const blockedReason = busy
    ? "جارٍ تسجيل القرار…"
    : !choice
      ? "اختر نتيجة المراجعة أولًا."
      : !reviewerId.trim()
        ? "أدخل معرّف الصيدلي."
        : null;

  async function confirm() {
    if (blockedReason || !choice || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    const body = { outcome: choice, reviewerId: reviewerId.trim(), note: trimmedNote || null };
    const signature = JSON.stringify(body);
    const key = retry.current?.signature === signature ? retry.current.key : newIdempotencyKey("review");
    retry.current = { signature, key };
    try {
      await onSubmit({ ...body, idempotencyKey: key });
      retry.current = null;
    } catch (err) {
      setError(
        describeError(err, {
          conflict: "يوجد قرار مختلف مسجّل لهذا الحدث، أو أن نسخة الحدث لم تعد الأحدث. حدّث القائمة.",
        }),
      );
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="outcome" aria-label="قرار الصيدلي">
      <div className="outcome__head">
        <h3>قرار الصيدلي</h3>
        {simulated ? <Chip tone="grey">يُسجَّل محليًا فقط</Chip> : null}
      </div>
      <div className="outcome__choices" role="radiogroup" aria-label="نتيجة المراجعة">
        {OUTCOMES.map((outcome) => {
          const meta = OUTCOME_LABELS[outcome];
          const on = choice === outcome;
          return (
            <button
              key={outcome}
              type="button"
              role="radio"
              aria-checked={on}
              data-outcome={outcome}
              className={`outcome__choice outcome__choice--${meta.tone} ${on ? "is-on" : ""}`}
              disabled={busy}
              onClick={() => setChoice(outcome)}
            >
              <span className="outcome__label">{meta.label}</span>
              <span className="outcome__hint">{meta.hint}</span>
            </button>
          );
        })}
      </div>
      <label className="field">
        <span className="field__label">ملاحظة (اختيارية)</span>
        <textarea
          className="input textarea"
          value={note}
          maxLength={2000}
          disabled={busy}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
        />
      </label>
      <label className="field field--inline">
        <span className="field__label">معرّف الصيدلي</span>
        <input
          className="input input--ltr"
          dir="ltr"
          value={reviewerId}
          disabled={busy}
          onChange={(e) => setReviewerId(e.target.value)}
        />
      </label>
      <div className="actions">
        <button className="btn btn--primary" type="button" data-testid="confirm-outcome" disabled={!!blockedReason} onClick={confirm}>
          {busy ? "جارٍ التسجيل…" : "تسجيل القرار"}
        </button>
        {blockedReason ? <span className="hint">{blockedReason}</span> : null}
      </div>
      {error ? (
        <Notice tone="red" role="alert" title="لم يُسجَّل القرار">
          {error} يمكنك الضغط مرة أخرى؛ إعادة القرار نفسه آمنة ولن تُكرّره.
        </Notice>
      ) : null}
    </section>
  );
}
