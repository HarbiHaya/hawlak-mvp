export type UserRole = "admin" | "hospital" | "insurer" | "caregiver";
export type ProductView = "admin" | "hospital" | "insurer" | "caregiver";
export type InsurerSection = "cases" | "alerts";

export interface ProductRoute {
  path: string;
  view: ProductView;
  insurerSection?: InsurerSection;
}

export interface NavItem {
  path: string;
  labelAr: string;
  labelEn: string;
  icon: string;
}

const routesByRole: Record<UserRole, ProductRoute[]> = {
  hospital: [{ path: "/hospital/intake", view: "hospital" }],
  insurer: [
    { path: "/insurer/cases", view: "insurer", insurerSection: "cases" },
    { path: "/insurer/alerts", view: "insurer", insurerSection: "alerts" },
  ],
  caregiver: [{ path: "/caregiver/status", view: "caregiver" }],
  admin: [
    { path: "/admin", view: "admin" },
    { path: "/admin/hospital", view: "hospital" },
    { path: "/admin/insurer/cases", view: "insurer", insurerSection: "cases" },
    { path: "/admin/insurer/alerts", view: "insurer", insurerSection: "alerts" },
    { path: "/admin/caregiver", view: "caregiver" },
  ],
};

const navByRole: Record<UserRole, NavItem[]> = {
  hospital: [
    { path: "/hospital/intake", labelAr: "إدخال حالة", labelEn: "New case", icon: "file-plus-2" },
  ],
  insurer: [
    { path: "/insurer/cases", labelAr: "الحالات", labelEn: "Cases", icon: "briefcase-medical" },
    { path: "/insurer/alerts", labelAr: "التنبيهات", labelEn: "Alerts", icon: "bell" },
  ],
  caregiver: [
    { path: "/caregiver/status", labelAr: "حالة المتابعة", labelEn: "Follow-up status", icon: "heart-handshake" },
  ],
  admin: [
    { path: "/admin", labelAr: "نظرة عامة", labelEn: "Overview", icon: "layout-dashboard" },
    { path: "/admin/hospital", labelAr: "المستشفى", labelEn: "Hospital", icon: "hospital" },
    { path: "/admin/insurer/cases", labelAr: "حالات التأمين", labelEn: "Insurer cases", icon: "briefcase-medical" },
    { path: "/admin/insurer/alerts", labelAr: "التنبيهات", labelEn: "Alerts", icon: "bell" },
    { path: "/admin/caregiver", labelAr: "مقدم الرعاية", labelEn: "Caregiver", icon: "heart-handshake" },
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
