import { useState, type FormEvent } from "react";

import { ApiClient } from "../lib/api";
import { describeError } from "../lib/errors";
import { Logo } from "./Logo";
import { Notice } from "./Notice";

export type Session = { kind: "api"; client: ApiClient } | { kind: "fixture" };

const DEFAULT_ORIGIN = "http://localhost:3000";

function validOrigin(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Asks for the local demo token at runtime. The token stays in React memory
 * (inside the ApiClient) and is gone after a page reload or "lock".
 */
export function TokenGate({
  onConnect,
  createClient = (origin, token) => new ApiClient(origin, token),
}: {
  onConnect: (session: Session) => void;
  createClient?: (origin: string, token: string) => ApiClient;
}) {
  const [origin, setOrigin] = useState(DEFAULT_ORIGIN);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const originOk = validOrigin(origin.trim());
  const canSubmit = originOk && token.trim().length > 0 && !busy;

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const client = createClient(origin.trim(), token.trim());
    try {
      await client.getVoiceOptions();
      setToken("");
      onConnect({ kind: "api", client });
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  }

  return (
    <main className="gate">
      <form className="gate__card" onSubmit={connect} autoComplete="off">
        <div className="brand">
          <Logo />
          <span className="brand__name">حولك</span>
          <span className="brand__tag">لوحة التشغيل والمراجعة</span>
        </div>
        <h1 className="gate__title">الدخول إلى العرض التجريبي</h1>
        <p className="muted">
          أدخل رمز العرض المحلي من ملف <bdi dir="ltr">.env</bdi> لدى فريق الخادم. يبقى الرمز في ذاكرة الصفحة
          فقط ويُمسح عند تحديثها أو قفل اللوحة.
        </p>

        <label className="field">
          <span className="field__label">عنوان الواجهة البرمجية</span>
          <input
            className="input input--ltr"
            dir="ltr"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            aria-invalid={!originOk}
            spellCheck={false}
          />
          {!originOk ? <span className="field__error">اكتب عنوانًا يبدأ بـ http:// أو https://</span> : null}
        </label>

        <label className="field">
          <span className="field__label">رمز الدخول (Bearer)</span>
          <input
            className="input input--ltr"
            dir="ltr"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            name="hawlak-demo-token"
          />
        </label>

        {error ? (
          <Notice tone="red" role="alert" title="تعذّر الاتصال">
            {error}
          </Notice>
        ) : null}

        <button className="btn btn--primary btn--block" type="submit" disabled={!canSubmit}>
          {busy ? "جارٍ التحقق…" : "اتصال"}
        </button>
        {!canSubmit && !busy ? (
          <p className="hint">{token.trim() ? "صحّح عنوان الواجهة البرمجية." : "أدخل الرمز لتفعيل الاتصال."}</p>
        ) : null}

        <div className="gate__divider">أو</div>
        <button className="btn btn--secondary btn--block" type="button" onClick={() => onConnect({ kind: "fixture" })}>
          العمل بدون خادم (بيانات تجريبية)
        </button>
        <p className="hint">يعرض حدث المراجعة التجريبي لأبو محمد من مجلد fixtures، دون صور ودون إرسال.</p>
      </form>
    </main>
  );
}
