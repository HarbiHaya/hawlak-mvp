import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type MouseEvent } from "react";

import { AdminHome } from "./AdminHome";
import { HawlakLogo } from "./Brand";
import { CaregiverWorkspace } from "./CaregiverWorkspace";
import { HospitalCases, HospitalWorkspace } from "./HospitalWorkspace";
import { Icon } from "./Icon";
import { InsurerWorkspace } from "./InsurerWorkspace";
import { HawlakApi, type DemoSession } from "./api";
import { ALERTS_CHANGED, SESSION_EXPIRED } from "./events";
import { displayError, type Locale } from "./i18n";
import { homePath, navItems, resolveRoute, type NavItem, type UserRole } from "./routing";
import { ToastProvider, useToast } from "./ui";

export type { Locale } from "./i18n";
export { displayError } from "./i18n";

const API_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:3000";
const SESSION_KEY = "hawlak.demo.session";
const LOCALE_KEY = "hawlak.locale";

const roleNames: Record<UserRole, { ar: string; en: string }> = {
  admin: { ar: "إدارة بيئة العرض", en: "Demo administration" },
  hospital: { ar: "المستشفى", en: "Hospital" },
  insurer: { ar: "الرعاية المتكاملة", en: "Integrated care" },
  caregiver: { ar: "مرافق المريض", en: "Caregiver" },
};

const groupNames = {
  hospital: { ar: "المستشفى", en: "Hospital" },
  insurer: { ar: "الرعاية المتكاملة", en: "Integrated care" },
  caregiver: { ar: "مرافق المريض", en: "Caregiver" },
} as const;

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
    try { sessionStorage.removeItem(SESSION_KEY); } catch { /* storage unavailable */ }
    return null;
  }
}

function useLocation() {
  const [location, setLocation] = useState(() => ({ pathname: window.location.pathname, search: window.location.search }));
  useEffect(() => {
    const update = () => setLocation({ pathname: window.location.pathname, search: window.location.search });
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const navigate = useCallback((target: string, replace = false) => {
    window.history[replace ? "replaceState" : "pushState"]({}, "", target);
    const url = new URL(target, window.location.origin);
    setLocation({ pathname: url.pathname, search: url.search });
  }, []);
  return { ...location, navigate };
}

function LoginScreen({ locale, onLocale, onLogin }: { locale: Locale; onLocale: () => void; onLogin: (session: DemoSession) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const ar = locale === "ar";
  const accounts: UserRole[] = ["hospital", "insurer", "caregiver", "admin"];
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const session = await HawlakApi.login(API_URL, username.trim().toLowerCase(), password);
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
      onLogin(session);
    } catch (caught) { setError(displayError(caught, locale)); }
    finally { setBusy(false); }
  }
  function chooseAccount(role: UserRole) {
    setUsername(role);
    passwordRef.current?.focus();
  }
  return <main className="login-page">
    <div className="login-card">
      <div className="login-card__top">
        <HawlakLogo />
        <button type="button" className="button button--ghost button--sm" onClick={onLocale} lang={ar ? "en" : "ar"}><Icon name="languages" size={16} />{ar ? "English" : "العربية"}</button>
      </div>
      <form className="login-panel" onSubmit={(event) => void submit(event)} noValidate>
        <h1>{ar ? "تسجيل الدخول" : "Sign in"}</h1>
        {error && <div className="notice notice--danger" role="alert"><Icon name="alert" size={16} /><div>{error}</div></div>}
        <div className="field"><label className="field__label" htmlFor="login-username">{ar ? "اسم المستخدم" : "Username"}</label><input id="login-username" className="input" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={(event) => setUsername(event.target.value)} dir="ltr" autoFocus /></div>
        <div className="field"><label className="field__label" htmlFor="login-password">{ar ? "كلمة المرور" : "Password"}</label><input id="login-password" ref={passwordRef} className="input" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} dir="ltr" /></div>
        <button className="button button--primary button--lg button--block" disabled={!username.trim() || !password || busy}>{busy ? (ar ? "جارٍ التحقق…" : "Signing in…") : (ar ? "دخول" : "Sign in")}</button>
        <div className="demo-accounts">
          <span className="demo-accounts__label">{ar ? "حسابات العرض" : "Demo accounts"}</span>
          <div className="demo-accounts__list">{accounts.map((role) => <button type="button" key={role} className="chip" aria-pressed={username === role} onClick={() => chooseAccount(role)}>{role === "admin" ? (ar ? "الإدارة" : "Administration") : roleNames[role][locale]}</button>)}</div>
        </div>
      </form>
      <p className="login-footnote"><Icon name="shield" size={14} />{ar ? "بيئة عرض ببيانات اصطناعية فقط." : "Demo environment. Synthetic data only."}</p>
    </div>
  </main>;
}

function NavLink({ item, active, locale, count, onNavigate }: { item: NavItem; active: boolean; locale: Locale; count: number; onNavigate: (event: MouseEvent<HTMLAnchorElement>, path: string) => void }) {
  return <a href={item.path} aria-current={active ? "page" : undefined} onClick={(event) => onNavigate(event, item.path)}>
    <Icon name={item.icon} />
    <span>{locale === "ar" ? item.labelAr : item.labelEn}</span>
    {item.showsAlertCount && count > 0 && <span className="count count--danger" aria-label={locale === "ar" ? `${count} تنبيهات مفتوحة` : `${count} open alerts`}>{count}</span>}
  </a>;
}

function ProductShell({ session, locale, onLocale, onLogout }: { session: DemoSession; locale: Locale; onLocale: () => void; onLogout: (expired?: boolean) => void }) {
  const { pathname, search, navigate } = useLocation();
  const route = resolveRoute(pathname, session.role);
  const [menuOpen, setMenuOpen] = useState(false);
  const [openAlerts, setOpenAlerts] = useState(0);
  const ar = locale === "ar";

  // Any 401 from the API ends the session instead of leaving dead screens.
  const api = useMemo(() => {
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await globalThis.fetch(input, init);
      if (response.status === 401) window.dispatchEvent(new Event(SESSION_EXPIRED));
      return response;
    };
    return new HawlakApi(API_URL, session.accessToken, fetcher);
  }, [session.accessToken]);
  useEffect(() => {
    const expire = () => onLogout(true);
    window.addEventListener(SESSION_EXPIRED, expire);
    return () => window.removeEventListener(SESSION_EXPIRED, expire);
  }, [onLogout]);

  useEffect(() => { if (route.path !== pathname) navigate(`${route.path}${search}`, true); }, [pathname, route.path]);

  // Move focus to the page heading on navigation so screen readers announce the new page.
  const firstRender = useRef(true);
  useEffect(() => {
    setMenuOpen(false);
    if (firstRender.current) { firstRender.current = false; return; }
    window.requestAnimationFrame(() => document.querySelector<HTMLElement>("[data-page-title]")?.focus({ preventScroll: false }));
  }, [route.path]);

  const items = navItems(session.role);
  const showsAlerts = items.some((item) => item.showsAlertCount);
  const refreshAlerts = useCallback(() => {
    if (!showsAlerts) return;
    api.listWorkspaceAlerts().then((result) => setOpenAlerts(result.data.filter((alert) => alert.status === "open").length)).catch(() => undefined);
  }, [api, showsAlerts]);
  useEffect(() => {
    refreshAlerts();
    window.addEventListener(ALERTS_CHANGED, refreshAlerts);
    return () => window.removeEventListener(ALERTS_CHANGED, refreshAlerts);
  }, [refreshAlerts]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);

  function onNavigate(event: MouseEvent<HTMLAnchorElement>, path: string) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(path);
  }

  const ungrouped = items.filter((item) => !item.group);
  const groups = (["hospital", "insurer", "caregiver"] as const).map((group) => ({ group, items: items.filter((item) => item.group === group) })).filter((entry) => entry.items.length > 0);

  return <div className="app-frame">
    <a className="skip-link" href="#main">{ar ? "تخطي إلى المحتوى" : "Skip to content"}</a>
    <header className="mobile-bar">
      <HawlakLogo />
      <button type="button" className="button button--ghost button--icon" aria-expanded={menuOpen} aria-controls="sidebar" aria-label={ar ? "القائمة" : "Menu"} onClick={() => setMenuOpen(true)}><Icon name="menu" size={20} /></button>
    </header>
    <div className={`scrim${menuOpen ? " is-open" : ""}`} onClick={() => setMenuOpen(false)} />
    <aside id="sidebar" className={`sidebar${menuOpen ? " is-open" : ""}`} aria-label={ar ? "التنقل" : "Navigation"}>
      <div className="sidebar__brand"><HawlakLogo /><span className="env-tag">{ar ? "بيئة العرض" : "Demo environment"}</span></div>
      <nav className="nav" aria-label={ar ? "التنقل الرئيسي" : "Main navigation"}>
        {ungrouped.map((item) => <NavLink key={item.path} item={item} active={route.path === item.path} locale={locale} count={openAlerts} onNavigate={onNavigate} />)}
        {groups.map(({ group, items: groupItems }) => <div key={group} role="group" aria-labelledby={`nav-${group}`} style={{ display: "contents" }}>
          <span className="nav__label" id={`nav-${group}`}>{groupNames[group][locale]}</span>
          {groupItems.map((item) => <NavLink key={item.path} item={item} active={route.path === item.path} locale={locale} count={openAlerts} onNavigate={onNavigate} />)}
        </div>)}
      </nav>
      <div className="sidebar__footer">
        <div className="account"><span className="account__avatar" aria-hidden="true">{session.username.slice(0, 1)}</span><div><b>{roleNames[session.role][locale]}</b><small dir="ltr">{session.username}</small></div></div>
        <button type="button" className="sidebar__action" onClick={onLocale} lang={ar ? "en" : "ar"}><Icon name="languages" size={16} />{ar ? "English" : "العربية"}</button>
        <button type="button" className="sidebar__action" onClick={() => onLogout()}><Icon name="logout" size={16} />{ar ? "تسجيل الخروج" : "Sign out"}</button>
      </div>
    </aside>
    <main id="main" className="app-main" tabIndex={-1}>
      {route.view === "admin" && <AdminHome api={api} locale={locale} role={session.role} navigate={navigate} />}
      {route.view === "hospital" && (route.hospitalSection === "cases" ? <HospitalCases api={api} locale={locale} /> : <HospitalWorkspace api={api} locale={locale} />)}
      {route.view === "insurer" && <InsurerWorkspace api={api} locale={locale} reviewer={session.username} role={session.role} section={route.insurerSection ?? "cases"} navigate={navigate} />}
      {route.view === "caregiver" && <CaregiverWorkspace api={api} locale={locale} />}
    </main>
  </div>;
}

function readLocale(): Locale {
  try { return localStorage.getItem(LOCALE_KEY) === "en" ? "en" : "ar"; } catch { return "ar"; }
}

function Root({ locale, setLocale }: { locale: Locale; setLocale: (update: (current: Locale) => Locale) => void }) {
  const [session, setSession] = useState<DemoSession | null>(() => loadSession());
  const { notify } = useToast();

  useEffect(() => {
    try { localStorage.setItem(LOCALE_KEY, locale); } catch { /* per-viewer preference only */ }
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    document.title = locale === "ar" ? "حولك | لوحة التحكم" : "Hawlak | Dashboard";
  }, [locale]);

  const logout = useCallback((expired = false) => {
    try { sessionStorage.removeItem(SESSION_KEY); } catch { /* storage unavailable */ }
    window.history.replaceState({}, "", "/login");
    setSession(null);
    if (expired) notify(locale === "ar" ? "انتهت صلاحية الجلسة. سجّل الدخول مرة أخرى." : "Your session has expired. Sign in again.", "info");
  }, [locale, notify]);

  const toggleLocale = () => setLocale((current) => current === "ar" ? "en" : "ar");
  if (!session) return <LoginScreen locale={locale} onLocale={toggleLocale} onLogin={(next) => { setSession(next); window.history.replaceState({}, "", homePath(next.role)); }} />;
  return <ProductShell session={session} locale={locale} onLocale={toggleLocale} onLogout={logout} />;
}

export function App() {
  const [locale, setLocale] = useState<Locale>(readLocale);
  return <ToastProvider locale={locale}><Root locale={locale} setLocale={setLocale} /></ToastProvider>;
}
