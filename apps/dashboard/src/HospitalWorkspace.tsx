import { useState, type FormEvent } from "react";

import { displayError, type Locale } from "./App";
import { type DialectCode, type HawlakApi } from "./api";

const labels = {
  ar: { kicker: "المستشفى", title: "إرسال خطة الخروج", subtitle: "أضف الملف واختر لغة المريض. تكمل شركة التأمين المراجعة.", name: "اسم المريض المسجل", address: "طريقة النداء (اختياري)", addressHint: "مثال: أبو محمد — للاستخدام الصوتي فقط", phone: "رقم الجوال", language: "اللغة", dialect: "اللهجة", file: "ملف الخروج PDF", pick: "اختيار الملف", submit: "إرسال للمراجعة", sending: "جارٍ الإرسال…", done: "وصلت الحالة إلى قائمة مراجعة شركة التأمين.", newCase: "إضافة حالة أخرى" },
  en: { kicker: "Hospital", title: "Send discharge plan", subtitle: "Add the document and patient language. The insurer completes review.", name: "Registered patient name", address: "Preferred form of address (optional)", addressHint: "Example: Abu Mohammed — voice use only", phone: "Mobile number", language: "Language", dialect: "Dialect", file: "Discharge PDF", pick: "Choose file", submit: "Send for review", sending: "Sending…", done: "The case is now in the insurer review queue.", newCase: "Add another case" },
} as const;

export function HospitalWorkspace({ api, locale }: { api: HawlakApi; locale: Locale }) {
  const t = labels[locale];
  const [patientName, setPatientName] = useState("");
  const [preferredAddress, setPreferredAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [dialect, setDialect] = useState<DialectCode>("ar-SA-najdi");
  const [document, setDocument] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const phoneValid = /^\+[1-9]\d{7,14}$/.test(phone);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!document || !phoneValid) return;
    setBusy(true); setError(null);
    try {
      const result = await api.submitDischargePacket({ document, patientFullName: patientName, preferredAddress, phoneE164: phone, languageCode: language, dialectCode: dialect });
      setCreated(result.caseId);
    } catch (caught) { setError(displayError(caught, locale)); } finally { setBusy(false); }
  }

  if (created) return <section className="success-state"><span className="success-ring">✓</span><h1>{t.done}</h1><code>{created}</code><button className="button button--primary" onClick={() => setCreated(null)}>{t.newCase}</button></section>;

  return <div className="workspace workspace--narrow">
    <header className="page-header"><span>{t.kicker}</span><h1>{t.title}</h1><p>{t.subtitle}</p></header>
    {error && <div className="notice notice--danger" role="alert">{error}</div>}
    <form className="form-panel" onSubmit={(event) => void submit(event)}><div className="form-grid">
      <label>{t.name}<input required value={patientName} onChange={(event) => setPatientName(event.target.value)} /></label>
      <label>{t.address}<input value={preferredAddress} onChange={(event) => setPreferredAddress(event.target.value)} placeholder={t.addressHint} /></label>
      <label>{t.phone}<input required dir="ltr" inputMode="tel" value={phone} onChange={(event) => setPhone(event.target.value.replace(/\s/g, ""))} placeholder="+9665XXXXXXXX" /></label>
      <label>{t.language}<select value={language} onChange={(event) => setLanguage(event.target.value as "ar" | "en")}><option value="ar">العربية</option><option value="en">English</option></select></label>
      <label className="field-span">{t.dialect}<select value={dialect} onChange={(event) => setDialect(event.target.value as DialectCode)}><option value="ar-SA-najdi">نجدي · Najdi</option><option value="ar-SA-hijazi">حجازي · Hijazi</option><option value="ar-SA-janoubi">جنوبي · Southern</option></select></label>
      <label className="upload-field field-span"><span>{t.file}</span><input type="file" accept="application/pdf,.pdf" required onChange={(event) => setDocument(event.target.files?.[0] ?? null)} /><b>{document?.name ?? t.pick}</b></label>
    </div><footer><button className="button button--primary" disabled={busy || !patientName || !phoneValid || !document}>{busy ? t.sending : t.submit}</button></footer></form>
  </div>;
}
