import { useRef, useState, type DragEvent, type FormEvent } from "react";

import { Icon } from "./Icon";
import { type DialectCode, type HawlakApi } from "./api";
import { displayError, type Locale } from "./i18n";
import { CopyButton, Field, Notice, PageHeader, Segmented } from "./ui";

const labels = {
  ar: {
    title: "تسجيل حالة خروج", subtitle: "تراجع شركة التأمين كل حالة قبل إرسال أي رسالة إلى المريض.",
    patient: "المريض", contact: "التواصل والتغطية", communication: "لغة التواصل", document: "ملخص الخروج",
    name: "الاسم الكامل كما هو مسجل", address: "صيغة المخاطبة", addressHint: "مثال: أبو محمد. تُستخدم في الرسائل الصوتية.", optional: "اختياري",
    phone: "رقم الجوال", phoneHint: "بالصيغة الدولية، مثل ‎+9665XXXXXXXX", phoneError: "أدخل الرقم بالصيغة الدولية مبدوءاً بـ +.",
    member: "رقم عضوية التأمين", memberHint: "كما في بطاقة التأمين", memberError: "من ٤ إلى ٣٢ حرفاً أو رقماً أو شرطة.",
    language: "اللغة", dialect: "اللهجة", nameError: "أدخل اسم المريض.",
    pick: "اسحب ملف PDF هنا أو اختر ملفاً", pickHint: "PDF بحد أقصى ٥ ميجابايت", change: "تغيير", fileError: "اختر ملف PDF لا يتجاوز ٥ ميجابايت.",
    submit: "إرسال للمراجعة", sending: "جارٍ الإرسال…", required: "جميع الحقول مطلوبة ما لم يُذكر خلاف ذلك.",
    done: "أُرسلت الحالة للمراجعة", reference: "رقم الحالة", newCase: "تسجيل حالة أخرى", share: "شارك رقم الحالة مع مرافق المريض لمتابعة سيرها.",
  },
  en: {
    title: "Register a discharge case", subtitle: "The insurer reviews every case before any message reaches the patient.",
    patient: "Patient", contact: "Contact and coverage", communication: "Communication", document: "Discharge summary",
    name: "Full name, as registered", address: "Form of address", addressHint: "For example: Abu Mohammed. Used in voice messages.", optional: "optional",
    phone: "Mobile number", phoneHint: "International format, e.g. +9665XXXXXXXX", phoneError: "Enter the number in international format, starting with +.",
    member: "Insurance member ID", memberHint: "As shown on the insurance card", memberError: "4–32 letters, digits or hyphens.",
    language: "Language", dialect: "Dialect", nameError: "Enter the patient's name.",
    pick: "Drop a PDF here or choose a file", pickHint: "PDF, up to 5 MB", change: "Change", fileError: "Choose a PDF file of up to 5 MB.",
    submit: "Submit for review", sending: "Submitting…", required: "All fields are required unless marked optional.",
    done: "Case submitted for review", reference: "Case reference", newCase: "Register another case", share: "Share the case reference with the patient's caregiver so they can follow its progress.",
  },
} as const;

const MAX_PDF_BYTES = 5 * 1024 * 1024;
const dialects: Array<{ value: DialectCode; ar: string; en: string }> = [
  { value: "ar-SA-najdi", ar: "نجدي", en: "Najdi" },
  { value: "ar-SA-hijazi", ar: "حجازي", en: "Hijazi" },
  { value: "ar-SA-janoubi", ar: "جنوبي", en: "Southern" },
];

const formatSize = (bytes: number) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const isPdf = (file: File) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

export function HospitalWorkspace({ api, locale }: { api: HawlakApi; locale: Locale }) {
  const t = labels[locale];
  const [patientName, setPatientName] = useState("");
  const [preferredAddress, setPreferredAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [memberId, setMemberId] = useState("");
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [dialect, setDialect] = useState<DialectCode>("ar-SA-najdi");
  const [document, setDocument] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const errors = {
    name: patientName.trim() ? null : t.nameError,
    phone: /^\+[1-9]\d{7,14}$/.test(phone) ? null : t.phoneError,
    member: /^[A-Za-z0-9-]{4,32}$/.test(memberId) ? null : t.memberError,
    file: document && isPdf(document) && document.size <= MAX_PDF_BYTES ? null : t.fileError,
  };
  const shown = (key: keyof typeof errors) => (touched[key] ? errors[key] : null);
  const touch = (key: string) => setTouched((current) => ({ ...current, [key]: true }));

  function chooseFile(file: File | undefined) {
    if (!file) return;
    setDocument(file);
    touch("file");
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched({ name: true, phone: true, member: true, file: true });
    const firstInvalid = (Object.keys(errors) as Array<keyof typeof errors>).find((key) => errors[key]);
    if (firstInvalid || !document) {
      formRef.current?.querySelector<HTMLElement>(`[data-field="${firstInvalid}"]`)?.focus();
      return;
    }
    setBusy(true); setError(null);
    try {
      const result = await api.submitDischargePacket({ document, patientFullName: patientName.trim(), preferredAddress: preferredAddress.trim(), phoneE164: phone, memberId, languageCode: language, dialectCode: dialect });
      setCreated(result.caseId);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setBusy(false); }
  }

  function reset() {
    setPatientName(""); setPreferredAddress(""); setPhone(""); setMemberId(""); setDocument(null);
    setTouched({}); setError(null); setCreated(null);
  }

  if (created) return <div className="page page--narrow">
    <section className="panel result" aria-live="polite">
      <span className="result__icon"><Icon name="check" size={24} /></span>
      <h1 tabIndex={-1} data-page-title>{t.done}</h1>
      <span className="muted">{t.reference}</span>
      <span className="reference"><code dir="ltr">{created}</code><CopyButton value={created} locale={locale} /></span>
      <p>{t.share}</p>
      <button className="button button--primary" onClick={reset}><Icon name="plus" size={16} />{t.newCase}</button>
    </section>
  </div>;

  return <div className="page page--narrow">
    <PageHeader title={t.title} description={t.subtitle} />
    {error && <div style={{ marginBottom: 16 }}><Notice tone="danger">{error}</Notice></div>}
    <form ref={formRef} className="panel" onSubmit={(event) => void submit(event)} noValidate>
      <section className="form-section">
        <h2>{t.patient}</h2>
        <div className="form-section__fields">
          <Field label={t.name} error={shown("name")}>{({ id, describedBy, invalid }) => <input id={id} data-field="name" className="input" autoComplete="off" value={patientName} aria-describedby={describedBy} aria-invalid={invalid} aria-required="true" onBlur={() => touch("name")} onChange={(event) => setPatientName(event.target.value)} />}</Field>
          <Field label={t.address} optional={t.optional} hint={t.addressHint}>{({ id, describedBy }) => <input id={id} className="input" autoComplete="off" value={preferredAddress} aria-describedby={describedBy} onChange={(event) => setPreferredAddress(event.target.value)} />}</Field>
        </div>
      </section>
      <section className="form-section">
        <h2>{t.contact}</h2>
        <div className="form-section__fields">
          <Field label={t.phone} hint={t.phoneHint} error={shown("phone")}>{({ id, describedBy, invalid }) => <input id={id} data-field="phone" className="input" dir="ltr" type="tel" inputMode="tel" autoComplete="off" value={phone} aria-describedby={describedBy} aria-invalid={invalid} aria-required="true" onBlur={() => touch("phone")} onChange={(event) => setPhone(event.target.value.replace(/[\s-]/g, ""))} placeholder="+9665XXXXXXXX" />}</Field>
          <Field label={t.member} hint={t.memberHint} error={shown("member")}>{({ id, describedBy, invalid }) => <input id={id} data-field="member" className="input mono" dir="ltr" autoComplete="off" value={memberId} aria-describedby={describedBy} aria-invalid={invalid} aria-required="true" onBlur={() => touch("member")} onChange={(event) => setMemberId(event.target.value.trim().toUpperCase())} placeholder="SYN-4471203" />}</Field>
        </div>
      </section>
      <section className="form-section">
        <h2>{t.communication}</h2>
        <div className="form-section__fields">
          <div className="field"><span className="field__label">{t.language}</span><Segmented block label={t.language} value={language} onChange={setLanguage} options={[{ value: "ar", label: "العربية" }, { value: "en", label: "English" }]} /></div>
          {language === "ar" && <div className="field"><span className="field__label">{t.dialect}</span><Segmented block label={t.dialect} value={dialect} onChange={setDialect} options={dialects.map((item) => ({ value: item.value, label: item[locale] }))} /></div>}
        </div>
      </section>
      <section className="form-section">
        <h2>{t.document}</h2>
        <div className="field">
          <div className={`dropzone${dragging ? " is-dragging" : ""}${document ? " has-file" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
            <span className="dropzone__icon"><Icon name={document ? "file" : "upload"} size={18} /></span>
            <span className="dropzone__text">
              <b>{document ? document.name : t.pick}</b>
              <small>{document ? formatSize(document.size) : t.pickHint}</small>
            </span>
            {document && <span className="button button--sm" aria-hidden="true">{t.change}</span>}
            <input id="discharge-file" data-field="file" type="file" accept="application/pdf,.pdf" aria-label={t.document} aria-invalid={!!shown("file")} aria-describedby={shown("file") ? "discharge-file-error" : undefined} onChange={(event) => chooseFile(event.target.files?.[0])} />
          </div>
          {shown("file") && <span id="discharge-file-error" className="field__error">{t.fileError}</span>}
        </div>
      </section>
      <footer className="form-footer">
        <span className="muted">{t.required}</span>
        <button className="button button--primary button--lg" disabled={busy}>{busy ? t.sending : t.submit}</button>
      </footer>
    </form>
  </div>;
}
