import { useMemo, useState } from "react";

import { CaregiverWorkspace } from "./CaregiverWorkspace";
import { HospitalWorkspace } from "./HospitalWorkspace";
import { InsurerWorkspace } from "./InsurerWorkspace";
import { HawlakApi, HawlakApiError } from "./api";

const API_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:3000";
const PROXY_AUTH = API_URL.startsWith("/");

export type Locale = "ar" | "en";
export type Role = "hospital" | "insurer" | "caregiver";

export const copy = {
  ar: { tagline: "متابعة الخروج، من الخطة إلى المنزل", hospital: "المستشفى", insurer: "شركة التأمين", caregiver: "مقدم الرعاية", language: "English", lock: "خروج", synthetic: "بيانات اصطناعية" },
  en: { tagline: "Discharge follow-up, from plan to home", hospital: "Hospital", insurer: "Insurer", caregiver: "Caregiver", language: "العربية", lock: "Sign out", synthetic: "Synthetic data" },
} as const;

export function displayError(error: unknown, locale: Locale): string {
  if (error instanceof HawlakApiError) return locale === "ar" ? `تعذّر إكمال الطلب (${error.code})` : `The request could not be completed (${error.code})`;
  return locale === "ar" ? "تعذّر الاتصال بالخادم. تحقق من تشغيل الواجهة الخلفية." : "Could not reach the server. Check that the API is running.";
}

function BrandMark() {
  return <div className="brand" aria-label="Hawlak حولك"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M40.31 16.39 A18 18 0 1 1 31.61 7.69" /><circle cx="24" cy="24" r="6.4" /></svg><span>حولك</span></div>;
}

function TokenGate({ onConnect }: { onConnect: (token: string) => Promise<void> }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function connect() {
    setBusy(true); setError(null);
    try { await onConnect(token); } catch (caught) { setError(displayError(caught, "ar")); } finally { setBusy(false); }
  }
  return <main className="gate-shell" dir="rtl">
    <section className="gate-story"><BrandMark /><div className="gate-orbit" aria-hidden="true"><span /></div><div><h1>خطة خروج تصل، تُفهم، وتُتابع.</h1><p>صوت وواتساب ومكالمة متابعة في مسار واحد.</p></div></section>
    <section className="gate-panel"><form onSubmit={(event) => { event.preventDefault(); void connect(); }}><span className="eyebrow">عرض النموذج</span><h2>تسجيل الدخول</h2><label htmlFor="token">رمز الواجهة</label><input id="token" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder="INTERNAL_API_TOKEN" />{error && <div className="notice notice--danger" role="alert">{error}</div>}<button className="button button--primary button--block" disabled={!token || busy}>{busy ? "جارٍ التحقق…" : "فتح حولك"}</button><small>الرمز يبقى في ذاكرة الصفحة فقط.</small></form></section>
  </main>;
}

function RoleRail({ role, locale, onRole, onLocale, onLock }: { role: Role; locale: Locale; onRole: (role: Role) => void; onLocale: () => void; onLock: () => void }) {
  const t = copy[locale];
  const roles: Array<{ value: Role; label: string; symbol: string }> = [{ value: "hospital", label: t.hospital, symbol: "+" }, { value: "insurer", label: t.insurer, symbol: "✓" }, { value: "caregiver", label: t.caregiver, symbol: "♡" }];
  return <aside className="role-rail"><BrandMark /><p>{t.tagline}</p><nav aria-label={locale === "ar" ? "اختيار الدور" : "Choose role"}>{roles.map((item) => <button key={item.value} className={role === item.value ? "active" : ""} onClick={() => onRole(item.value)}><span aria-hidden="true">{item.symbol}</span>{item.label}</button>)}</nav><div className="role-rail__bottom"><span className="synthetic-badge">{t.synthetic}</span><button onClick={onLocale}>{t.language}</button>{!PROXY_AUTH && <button onClick={onLock}>{t.lock}</button>}</div></aside>;
}

export function App() {
  const [token, setToken] = useState<string | null>(PROXY_AUTH ? "" : null);
  const [role, setRole] = useState<Role>("insurer");
  const [locale, setLocale] = useState<Locale>("ar");
  const api = useMemo(() => token !== null ? new HawlakApi(API_URL, token) : null, [token]);
  if (!api) return <TokenGate onConnect={async (nextToken) => { const candidate = new HawlakApi(API_URL, nextToken); await candidate.getVoiceOptions(); setToken(nextToken); }} />;
  return <div className="product-shell" dir={locale === "ar" ? "rtl" : "ltr"} lang={locale}><RoleRail role={role} locale={locale} onRole={setRole} onLocale={() => setLocale((current) => current === "ar" ? "en" : "ar")} onLock={() => setToken(null)} /><main className="product-main">{role === "hospital" && <HospitalWorkspace api={api} locale={locale} />}{role === "insurer" && <InsurerWorkspace api={api} locale={locale} />}{role === "caregiver" && <CaregiverWorkspace api={api} locale={locale} />}</main></div>;
}
