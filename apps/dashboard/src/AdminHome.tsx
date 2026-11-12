import { Icon } from "./Icon";
import type { Locale } from "./App";

const copy = {
  ar: { title: "إدارة بيئة العرض", description: "انتقل إلى مساحة عمل كل دور لمراجعة رحلة المريض كاملة.", notice: "بيئة عرض تستخدم بيانات اصطناعية فقط. يُمنع إدخال بيانات مرضى حقيقية.", hospital: "مساحة المستشفى", hospitalText: "تسجيل حالات الخروج ورفع ملخصات الخروج للمراجعة.", insurer: "مساحة الرعاية المتكاملة", insurerText: "التحقق من التغطية ومراجعة المحتوى واعتماد خطط المتابعة ومتابعة التنبيهات.", caregiver: "مساحة مرافق المريض", caregiverText: "متابعة حالة الأدوية ومواعيد المكالمات والتنبيهات المفتوحة.", open: "فتح مساحة العمل", demo: "بيئة عرض" },
  en: { title: "Demo administration", description: "Open each role's workspace to review the complete patient journey.", notice: "This demo environment uses synthetic data only. Do not enter real patient data.", hospital: "Hospital workspace", hospitalText: "Register discharge cases and upload discharge summaries for review.", insurer: "Integrated care workspace", insurerText: "Verify coverage, review content, approve follow-up plans and monitor alerts.", caregiver: "Caregiver workspace", caregiverText: "Follow medication status, call times and open alerts.", open: "Open workspace", demo: "Demo environment" },
} as const;

export function AdminHome({ locale, navigate }: { locale: Locale; navigate: (path: string) => void }) {
  const t = copy[locale];
  const areas = [{ title: t.hospital, text: t.hospitalText, path: "/admin/hospital", icon: "hospital" }, { title: t.insurer, text: t.insurerText, path: "/admin/insurer/cases", icon: "briefcase-medical" }, { title: t.caregiver, text: t.caregiverText, path: "/admin/caregiver", icon: "heart-handshake" }];
  return <div className="workspace admin-home"><header className="page-title-block"><div><h1>{t.title}</h1><p>{t.description}</p></div><span className="status-chip status-chip--demo">{t.demo}</span></header><div className="compliance-note"><Icon name="shield" /><span>{t.notice}</span></div><section className="admin-access-grid" aria-label={t.title}>{areas.map((area) => <article className="access-card" key={area.path}><span className="access-card__icon"><Icon name={area.icon} size={22} /></span><div><h2>{area.title}</h2><p>{area.text}</p></div><button className="text-action" onClick={() => navigate(area.path)}>{t.open}<Icon name="arrow" size={16} /></button></article>)}</section></div>;
}
