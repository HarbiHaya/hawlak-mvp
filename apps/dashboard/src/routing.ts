export type UserRole = "admin" | "hospital" | "insurer" | "caregiver";
export type ProductView = "admin" | "hospital" | "insurer" | "caregiver";
export type InsurerSection = "cases" | "alerts" | "analytics";
export type HospitalSection = "cases";

export interface ProductRoute {
  path: string;
  view: ProductView;
  insurerSection?: InsurerSection;
  /** Absent on the intake form, which is the hospital's home. */
  hospitalSection?: HospitalSection;
}

export interface NavItem {
  path: string;
  labelAr: string;
  labelEn: string;
  icon: string;
  /** Admin navigation groups items under the workspace they belong to. */
  group?: "hospital" | "insurer" | "caregiver";
  showsAlertCount?: boolean;
}

const routesByRole: Record<UserRole, ProductRoute[]> = {
  hospital: [
    { path: "/hospital/intake", view: "hospital" },
    { path: "/hospital/cases", view: "hospital", hospitalSection: "cases" },
  ],
  insurer: [
    { path: "/insurer/cases", view: "insurer", insurerSection: "cases" },
    { path: "/insurer/alerts", view: "insurer", insurerSection: "alerts" },
    { path: "/insurer/analytics", view: "insurer", insurerSection: "analytics" },
  ],
  caregiver: [{ path: "/caregiver/status", view: "caregiver" }],
  admin: [
    { path: "/admin", view: "admin" },
    { path: "/admin/hospital", view: "hospital" },
    { path: "/admin/hospital/cases", view: "hospital", hospitalSection: "cases" },
    { path: "/admin/insurer/cases", view: "insurer", insurerSection: "cases" },
    { path: "/admin/insurer/alerts", view: "insurer", insurerSection: "alerts" },
    { path: "/admin/insurer/analytics", view: "insurer", insurerSection: "analytics" },
    { path: "/admin/caregiver", view: "caregiver" },
  ],
};

const navByRole: Record<UserRole, NavItem[]> = {
  hospital: [
    { path: "/hospital/intake", labelAr: "تسجيل حالة", labelEn: "Register case", icon: "file-plus-2" },
    { path: "/hospital/cases", labelAr: "الحالات المرسلة", labelEn: "Submitted cases", icon: "list" },
  ],
  insurer: [
    { path: "/insurer/cases", labelAr: "الحالات", labelEn: "Cases", icon: "briefcase-medical" },
    { path: "/insurer/alerts", labelAr: "التنبيهات", labelEn: "Alerts", icon: "bell", showsAlertCount: true },
    { path: "/insurer/analytics", labelAr: "التحليلات", labelEn: "Analytics", icon: "chart" },
  ],
  caregiver: [
    { path: "/caregiver/status", labelAr: "متابعة الحالة", labelEn: "Patient follow-up", icon: "heart-handshake" },
  ],
  admin: [
    { path: "/admin", labelAr: "نظرة عامة", labelEn: "Overview", icon: "layout-dashboard" },
    { path: "/admin/hospital", labelAr: "تسجيل حالة", labelEn: "Register case", icon: "file-plus-2", group: "hospital" },
    { path: "/admin/hospital/cases", labelAr: "الحالات المرسلة", labelEn: "Submitted cases", icon: "list", group: "hospital" },
    { path: "/admin/insurer/cases", labelAr: "الحالات", labelEn: "Cases", icon: "briefcase-medical", group: "insurer" },
    { path: "/admin/insurer/alerts", labelAr: "التنبيهات", labelEn: "Alerts", icon: "bell", group: "insurer", showsAlertCount: true },
    { path: "/admin/insurer/analytics", labelAr: "التحليلات", labelEn: "Analytics", icon: "chart", group: "insurer" },
    { path: "/admin/caregiver", labelAr: "متابعة الحالة", labelEn: "Patient follow-up", icon: "heart-handshake", group: "caregiver" },
  ],
};

export function homePath(role: UserRole): string {
  return routesByRole[role][0].path;
}

export function resolveRoute(pathname: string, role: UserRole): ProductRoute {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  return routesByRole[role].find((route) => route.path === normalized) ?? routesByRole[role][0];
}

export function navItems(role: UserRole): NavItem[] {
  return navByRole[role];
}

/** Path of a sibling view in the same role scope, e.g. insurer cases from the alerts page. */
export function viewPath(role: UserRole, view: ProductView, insurerSection?: InsurerSection): string | null {
  return routesByRole[role].find((route) => route.view === view && (insurerSection === undefined || route.insurerSection === insurerSection))?.path ?? null;
}

export function queryParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

/** Updates one query parameter without adding a history entry. */
export function replaceQueryParam(name: string, value: string | null) {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
}
