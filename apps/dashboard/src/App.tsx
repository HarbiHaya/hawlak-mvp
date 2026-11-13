import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AdminHome } from "./AdminHome";
import { HawlakLogo } from "./Brand";
import { CaregiverWorkspace } from "./CaregiverWorkspace";
import { HospitalWorkspace } from "./HospitalWorkspace";
import { Icon } from "./Icon";
import { InsurerWorkspace } from "./InsurerWorkspace";
import { HawlakApi, HawlakApiError, type DemoSession } from "./api";
import { homePath, navItems, resolveRoute, type UserRole } from "./routing";

const API_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:3000";
const SESSION_KEY = "hawlak.demo.session";

export type Locale = "ar" | "en";

const roleNames: Record<UserRole, { ar: string; en: string }> = {
  admin: { ar: "إدارة بيئة العرض", en: "Demo administration" },
  hospital: { ar: "المستشفى", en: "Hospital" },
  insurer: { ar: "الرعاية المتكاملة", en: "Integrated care" },
  caregiver: { ar: "مرافق المريض", en: "Caregiver" },
};

export function displayError(error: unknown, locale: Locale): string {
  const messages: Record<string, { ar: string; en: string }> = {
    invalid_credentials: { ar: "اسم المستخدم أو كلمة المرور غير صحيحة.", en: "The username or password is incorrect." },
    Forbidden: { ar: "لا يملك هذا الحساب صلاحية الوصول إلى هذه الصفحة.", en: "This account is not authorised to access this page." },
    Unauthorized: { ar: "انتهت صلاحية الجلسة. يُرجى تسجيل الدخول مرة أخرى.", en: "Your session has expired. Please sign in again." },
    approved_content_is_immutable: { ar: "لا يمكن تعديل المحتوى بعد اعتماده.", en: "Approved content cannot be modified." },
    already_approved: { ar: "سبق اعتماد هذه الحالة.", en: "This case has already been approved." },
    eligibility_not_verified: { ar: "يجب التحقق من أهلية العضو في تبويب التغطية قبل الاعتماد.", en: "Verify the member's eligibility in the Coverage tab before approval." },
    member_not_eligible: { ar: "العضو غير مؤهل لبرنامج الرعاية بعد الخروج، لذا لا يمكن اعتماد الحالة.", en: "The member is not eligible for the post-discharge care programme, so the case cannot be approved." },
    medications_required: { ar: "يجب إضافة دواء واحد على الأقل قبل الاعتماد.", en: "Add at least one medication before approval." },
    medication_details_required: { ar: "يُرجى استكمال اسم الدواء وتعليمات الجرعة لجميع الأدوية.", en: "Complete the name and dose instruction for every medication." },
    reminder_script_required: { ar: "يُرجى إدخال نص التذكير لكل دواء فُعّل له التذكير.", en: "Enter the reminder text for every medication with a reminder enabled." },
    voice_script_required: { ar: "يُرجى إدخال نص الرسالة الصوتية أو إيقاف إرسالها.", en: "Enter the voice message text or turn the voice message off." },
    call_plan_incomplete: { ar: "يُرجى استكمال نصوص مكالمة المتابعة ورقم فريق الاستجابة، أو إيقاف المكالمة.", en: "Complete the follow-up call scripts and the responder number, or turn the call off." },
    call_time_in_past: { ar: "موعد المكالمة الأولى في الماضي. يُرجى اختيار موعد لاحق.", en: "The first call is scheduled in the past. Select a later time." },
    patient_text_contains_identifier: { ar: "يحتوي نص موجّه للمريض على بيانات تعريفية (الاسم الكامل أو رقم الجوال أو رقم الهوية أو الإقامة أو رقم العضوية أو الوثيقة أو رقم الحالة أو اسم الملف). يُرجى حذفها قبل الاعتماد.", en: "Patient-facing text contains an identifier (full name, phone number, national or Iqama number, member or policy number, case ID or file name). Remove it before approval." },
    no_channel_enabled: { ar: "يجب تفعيل قناة تواصل واحدة على الأقل: الرسالة الصوتية أو تذكير الدواء أو مكالمة المتابعة.", en: "Enable at least one channel: voice message, medication reminder or follow-up call." },
    document_not_readable: { ar: "تعذّرت قراءة نص ملخص الخروج، لذا لا يمكن إنشاء المسودات تلقائياً.", en: "The discharge summary text could not be read, so drafts cannot be generated automatically." },
    case_not_found: { ar: "لم يُعثر على الحالة. يُرجى التحقق من رقم الحالة.", en: "No case was found. Check the case reference." },
    file_not_found: { ar: "تعذّر فتح الملف.", en: "The file could not be opened." },
    validation_failed: { ar: "بعض الحقول غير صالحة. يُرجى مراجعة الأرقام والنصوص المدخلة.", en: "Some fields are invalid. Review the numbers and text entered." },
    pdf_required: { ar: "يُقبل ملف PDF فقط.", en: "Only PDF files are accepted." },
    pdf_filename_required: { ar: "يُقبل ملف PDF فقط.", en: "Only PDF files are accepted." },
    invalid_pdf: { ar: "الملف المرفوع ليس ملف PDF صالحاً.", en: "The uploaded file is not a valid PDF." },
    document_too_large: { ar: "يتجاوز حجم الملف الحد المسموح (٥ ميجابايت).", en: "The file exceeds the 5 MB limit." },
    image_required: { ar: "يُرجى رفع صورة بصيغة JPEG أو PNG أو WebP.", en: "Upload a JPEG, PNG or WebP image." },
    invalid_image: { ar: "الصورة المرفوعة غير صالحة.", en: "The uploaded image is not valid." },
    image_size_invalid: { ar: "يجب ألا يتجاوز حجم الصورة ١٠ ميجابايت.", en: "The image must not exceed 10 MB." },
    storage_unavailable: { ar: "خدمة التخزين غير متاحة حالياً. يُرجى المحاولة لاحقاً.", en: "File storage is temporarily unavailable. Please try again later." },
  };
  if (error instanceof HawlakApiError) return messages[error.code]?.[locale] ?? (locale === "ar" ? "تعذّر إكمال الطلب. يُرجى المحاولة مرة أخرى." : "The request could not be completed. Please try again.");
  return locale === "ar" ? "تعذّر الاتصال بالخادم. يُرجى التحقق من الاتصال والمحاولة مرة أخرى." : "The server could not be reached. Check your connection and try again.";
}

function loadSession(): DemoSession | null {
  try {
    const stored = sessionStorage.getItem(SESSION_KEY);
    if (!stored) return null;
    const session = JSON.parse(stored) as DemoSession;
    if (new Date(session.expiresAt).getTime() <= Date.now()) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

function usePathname() {
  const [pathname, setPathname] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  function navigate(path: string, replace = false) {
    window.history[replace ? "replaceState" : "pushState"]({}, "", path);
    setPathname(path);
  }
  return { pathname, navigate };
}

function LoginScreen({ locale, onLocale, onLogin }: { locale: Locale; onLocale: () => void; onLogin: (session: DemoSession) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ar = locale === "ar";
  const accounts = [["admin", ar ? "إدارة بيئة العرض" : "Administration"], ["hospital", ar ? "المستشفى" : "Hospital"], ["insurer", ar ? "الرعاية المتكاملة" : "Integrated care"], ["caregiver", ar ? "مرافق المريض" : "Caregiver"]];
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const session = await HawlakApi.login(API_URL, username.trim().toLowerCase(), password);
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
      onLogin(session);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setBusy(false); }
  }
  return <main className="login-page" dir={ar ? "rtl" : "ltr"} lang={locale}>
    <section className="login-brand-panel"><HawlakLogo inverse /><div className="login-context"><span>{ar ? "منصة متابعة ما بعد الخروج" : "Post-discharge follow-up platform"}</span><h1>{ar ? "دخول آمن حسب الدور" : "Secure role-based access"}</h1><p>{ar ? "كل حساب يفتح مساحة العمل المصرح بها فقط." : "Each account opens only its authorized workspace."}</p></div><div className="login-disclaimer"><Icon name="shield" /><span>{ar ? "بيئة عرض ببيانات اصطناعية. لا تستخدم بيانات مرضى حقيقية." : "Synthetic demo environment. Do not use real patient data."}</span></div></section>
    <section className="login-form-panel"><button className="language-button" onClick={onLocale}><Icon name="languages" />{ar ? "English" : "العربية"}</button><form className="login-form" onSubmit={(event) => void submit(event)}><div className="login-heading"><h2>{ar ? "تسجيل الدخول" : "Sign in"}</h2><p>{ar ? "استخدم حساب الدور المخصص للعرض." : "Use the account assigned to your demo role."}</p></div><label>{ar ? "اسم المستخدم" : "Username"}<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} dir="ltr" /></label><label>{ar ? "كلمة المرور" : "Password"}<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} dir="ltr" /></label>{error && <div className="notice notice--danger" role="alert">{error}</div>}<button className="button button--primary button--block button--large" disabled={!username || password.length < 12 || busy}>{busy ? (ar ? "جارٍ التحقق…" : "Checking…") : (ar ? "دخول" : "Sign in")}</button><div className="demo-accounts"><span>{ar ? "حسابات العرض" : "Demo accounts"}</span><div>{accounts.map(([value, label]) => <button type="button" key={value} onClick={() => setUsername(value)}><b>{label}</b><code>{value}</code></button>)}</div></div></form></section>
  </main>;
}

function ProductShell({ session, locale, onLocale, onLogout }: { session: DemoSession; locale: Locale; onLocale: () => void; onLogout: () => void }) {
  const { pathname, navigate } = usePathname();
  const route = resolveRoute(pathname, session.role);
  const api = useMemo(() => new HawlakApi(API_URL, session.accessToken), [session.accessToken]);
  useEffect(() => { if (route.path !== pathname) navigate(route.path, true); }, [pathname, route.path]);
  const items = navItems(session.role);
  const ar = locale === "ar";
  return <div className="app-frame" dir={ar ? "rtl" : "ltr"} lang={locale}><aside className="app-sidebar"><div className="sidebar-brand"><HawlakLogo /><span>{roleNames[session.role][locale]}</span></div><nav className="app-nav" aria-label={ar ? "التنقل الرئيسي" : "Main navigation"}>{items.map((item) => <button key={item.path} className={route.path === item.path ? "active" : ""} aria-current={route.path === item.path ? "page" : undefined} onClick={() => navigate(item.path)}><Icon name={item.icon} /><span>{ar ? item.labelAr : item.labelEn}</span></button>)}</nav><div className="sidebar-footer"><div className="signed-user"><span><Icon name="user" /></span><div><b>{roleNames[session.role][locale]}</b><small>{session.username}</small></div></div><button className="sidebar-action" onClick={onLocale}><Icon name="languages" />{ar ? "English" : "العربية"}</button><button className="sidebar-action sidebar-action--danger" onClick={onLogout}><Icon name="logout" />{ar ? "تسجيل الخروج" : "Sign out"}</button></div></aside><div className="app-content"><header className="topbar"><div><span className="environment-dot" />{ar ? "بيئة العرض" : "Demo environment"}</div><span>{roleNames[session.role][locale]}</span></header><main>{route.view === "admin" && <AdminHome locale={locale} navigate={navigate} />}{route.view === "hospital" && <HospitalWorkspace api={api} locale={locale} />}{route.view === "insurer" && <InsurerWorkspace api={api} locale={locale} reviewer={session.username} section={route.insurerSection ?? "cases"} />}{route.view === "caregiver" && <CaregiverWorkspace api={api} locale={locale} />}</main></div></div>;
}

export function App() {
  const [session, setSession] = useState<DemoSession | null>(() => loadSession());
  const [locale, setLocale] = useState<Locale>(() => { try { return localStorage.getItem("hawlak.locale") === "en" ? "en" : "ar"; } catch { return "ar"; } });
  useEffect(() => { try { localStorage.setItem("hawlak.locale", locale); } catch { /* per-viewer preference only */ } }, [locale]);
  function logout() {
    sessionStorage.removeItem(SESSION_KEY);
    window.history.replaceState({}, "", "/login");
    setSession(null);
  }
  if (!session) return <LoginScreen locale={locale} onLocale={() => setLocale((current) => current === "ar" ? "en" : "ar")} onLogin={(next) => { setSession(next); window.history.replaceState({}, "", homePath(next.role)); }} />;
  return <ProductShell session={session} locale={locale} onLocale={() => setLocale((current) => current === "ar" ? "en" : "ar")} onLogout={logout} />;
}
