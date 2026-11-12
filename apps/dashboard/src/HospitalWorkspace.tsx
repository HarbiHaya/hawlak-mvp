import { useState, type FormEvent } from "react";

import { displayError, type Locale } from "./App";
import { type DialectCode, type HawlakApi } from "./api";

const labels = {
  ar: { title: "تسجيل حالة خروج", subtitle: "أدخل بيانات المريض وارفع ملخص الخروج. يراجع فريق الرعاية المتكاملة لدى شركة التأمين كل حالة قبل إرسال أي رسالة إلى المريض.", name: "الاسم الكامل للمريض كما هو مسجل", address: "صيغة المخاطبة المفضلة (اختياري)", addressHint: "مثال: أبو محمد. تُستخدم في الرسائل الصوتية فقط.", phone: "رقم جوال المريض", member: "رقم عضوية التأمين", memberHint: "كما يظهر في بطاقة التأمين", language: "لغة التواصل", dialect: "اللهجة", file: "ملخص الخروج (PDF)", pick: "اختيار ملف PDF", submit: "إرسال لمراجعة شركة التأمين", sending: "جارٍ الإرسال…", done: "أُرسلت الحالة لمراجعة شركة التأمين", reference: "رقم الحالة", newCase: "تسجيل حالة أخرى", share: "شارك رقم الحالة مع مرافق المريض ليتمكن من متابعة سيرها." },
  en: { title: "Register a discharge case", subtitle: "Enter the patient's details and upload the discharge summary. The insurer's integrated care team reviews every case before any message is sent to the patient.", name: "Patient full name, as registered", address: "Preferred form of address (optional)", addressHint: "For example: Abu Mohammed. Used in voice messages only.", phone: "Patient mobile number", member: "Insurance member ID", memberHint: "As shown on the insurance card", language: "Communication language", dialect: "Arabic dialect", file: "Discharge summary (PDF)", pick: "Select a PDF file", submit: "Submit for insurer review", sending: "Submitting…", done: "Case submitted for insurer review", reference: "Case reference", newCase: "Register another case", share: "Share this case reference with the patient's caregiver so they can follow its progress." },
} as const;

export function HospitalWorkspace({ api, locale }: { api: HawlakApi; locale: Locale }) {
  const t = labels[locale];
  const [patientName, setPatientName] = useState("");
  const [preferredAddress, setPreferredAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [memberId, setMemberId] = useState("");
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [dialect, setDialect] = useState<DialectCode>("ar-SA-najdi");
  const [document, setDocument] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const phoneValid = /^\+[1-9]\d{7,14}$/.test(phone);
  const memberValid = /^[A-Za-z0-9-]{4,32}$/.test(memberId);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!document || !phoneValid || !memberValid) return;
    setBusy(true); setError(null);
    try {
      const result = await api.submitDischargePacket({ document, patientFullName: patientName, preferredAddress, phoneE164: phone, memberId, languageCode: language, dialectCode: dialect });
      setCreated(result.caseId);
    } catch (caught) { setError(displayError(caught, locale)); } finally { setBusy(false); }
  }

  if (created) return <section className="success-state"><span className="success-ring">✓</span><h1>{t.done}</h1><small>{t.reference}</small><code>{created}</code><p>{t.share}</p><button className="button button--primary" onClick={() => setCreated(null)}>{t.newCase}</button></section>;

  return <div className="workspace workspace--narrow">
    <header className="page-title-block"><div><h1>{t.title}</h1><p>{t.subtitle}</p></div></header>
    {error && <div className="notice notice--danger" role="alert">{error}</div>}
    <form className="form-panel" onSubmit={(event) => void submit(event)}><div className="form-grid">
      <label>{t.name}<input required value={patientName} onChange={(event) => setPatientName(event.target.value)} /></label>
      <label>{t.address}<input value={preferredAddress} onChange={(event) => setPreferredAddress(event.target.value)} placeholder={t.addressHint} /></label>
      <label>{t.phone}<input required dir="ltr" inputMode="tel" value={phone} onChange={(event) => setPhone(event.target.value.replace(/\s/g, ""))} placeholder="+9665XXXXXXXX" /></label>
      <label>{t.member}<input required dir="ltr" value={memberId} onChange={(event) => setMemberId(event.target.value.trim().toUpperCase())} placeholder="SYN-4471203" aria-describedby="member-hint" /><small id="member-hint" className="field-hint">{t.memberHint}</small></label>
      <label>{t.language}<select value={language} onChange={(event) => setLanguage(event.target.value as "ar" | "en")}><option value="ar">العربية</option><option value="en">English</option></select></label>
      {language === "ar" && <label className="field-span">{t.dialect}<select value={dialect} onChange={(event) => setDialect(event.target.value as DialectCode)}><option value="ar-SA-najdi">نجدي · Najdi</option><option value="ar-SA-hijazi">حجازي · Hijazi</option><option value="ar-SA-janoubi">جنوبي · Southern</option></select></label>}
      <label className="upload-field field-span"><span>{t.file}</span><input type="file" accept="application/pdf,.pdf" required onChange={(event) => setDocument(event.target.files?.[0] ?? null)} /><b>{document?.name ?? t.pick}</b></label>
    </div><footer><button className="button button--primary" disabled={busy || !patientName || !phoneValid || !memberValid || !document}>{busy ? t.sending : t.submit}</button></footer></form>
  </div>;
}
