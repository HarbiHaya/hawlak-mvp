import { useRef, useState } from "react";

import { describeError } from "../lib/errors";
import { newIdempotencyKey } from "../lib/idempotency";
import type { ApproveRequest, ApproveResponse } from "../lib/schemas";
import { Notice } from "./Notice";

export const DEFAULT_APPROVER = "demo-operator-01";

/**
 * Explicit human approval of one exact script. Nothing is sent until the
 * operator ticks the acknowledgement and clicks approve. The checksum is sent
 * exactly as generated. Remount (key={artifactId}) when a new script arrives.
 */
export function ApprovalStep({
  artifactId,
  scriptChecksum,
  factPassed,
  onApprove,
}: {
  artifactId: string;
  scriptChecksum: string;
  factPassed: boolean;
  onApprove: (body: ApproveRequest, idempotencyKey: string) => Promise<ApproveResponse>;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [approver, setApprover] = useState(DEFAULT_APPROVER);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApproveResponse | null>(null);
  const lock = useRef(false);

  const blockedReason = result
    ? "تم الاعتماد والإرسال لهذا النص."
    : !factPassed
      ? "لا يمكن الاعتماد: فحص الحقائق السريرية لم ينجح."
      : !acknowledged
        ? "اقرأ النص كاملًا ثم أكّد الإقرار لتفعيل الاعتماد."
        : !approver.trim()
          ? "أدخل معرّف المعتمِد."
          : busy
            ? "جارٍ الاعتماد والإرسال…"
            : null;

  async function approve() {
    if (blockedReason || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const response = await onApprove(
        { artifactId, scriptChecksum, approvedBy: approver.trim() },
        newIdempotencyKey("approve"),
      );
      setResult(response);
    } catch (err) {
      setError(
        describeError(err, {
          conflict: "رفض الخادم الاعتماد لأن النص تغيّر أو لا يطابق آخر نسخة. ولّد النص من جديد ثم راجعه.",
        }),
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="approval">
      <label className="check">
        <input
          type="checkbox"
          checked={acknowledged}
          disabled={!!result || busy || !factPassed}
          onChange={(e) => setAcknowledged(e.target.checked)}
        />
        <span>قرأت النص كاملًا وأوافق على تحويله إلى صوت وإرساله كما هو، دون أي تعديل.</span>
      </label>

      <label className="field field--inline">
        <span className="field__label">معرّف المعتمِد</span>
        <input
          className="input input--ltr"
          dir="ltr"
          value={approver}
          disabled={!!result || busy}
          onChange={(e) => setApprover(e.target.value)}
        />
      </label>

      <div className="actions">
        <button className="btn btn--approve" type="button" disabled={!!blockedReason} onClick={approve}>
          {busy ? "جارٍ الإرسال…" : "اعتماد النص وإرساله"}
        </button>
        {blockedReason && !result ? <span className="hint">{blockedReason}</span> : null}
      </div>

      {error ? (
        <Notice tone="red" role="alert" title="لم يكتمل الاعتماد">
          {error}
        </Notice>
      ) : null}

      {result ? (
        <Notice tone="green" role="status" title="تم الاعتماد والإرسال">
          <p>أُرسلت الرسائل بالترتيب: الإفصاح، ثم الملاحظة الصوتية، ثم طلب صور العلب.</p>
          <dl className="kv">
            <dt>بصمة النص المعتمد</dt>
            <dd>
              <code dir="ltr">{result.scriptChecksum}</code>
            </dd>
            <dt>بصمة الصوت</dt>
            <dd>
              <code dir="ltr">{result.audioChecksum}</code>
            </dd>
            <dt>معرّفات الرسائل ({result.messageIds.length})</dt>
            <dd>
              {result.messageIds.map((id) => (
                <code key={id} dir="ltr" className="block-code">
                  {id}
                </code>
              ))}
            </dd>
          </dl>
          <p className="hint">قبول واتساب للرسالة لا يعني وصولها؛ تأكد من الهاتف.</p>
        </Notice>
      ) : null}
    </div>
  );
}
