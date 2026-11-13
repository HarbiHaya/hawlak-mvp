import { describe, expect, it } from "vitest";

import { homePath, navItems, resolveRoute } from "./routing";

describe("role-scoped product routing", () => {
  it("gives every role a distinct default URL", () => {
    expect(homePath("hospital")).toBe("/hospital/intake");
    expect(homePath("insurer")).toBe("/insurer/cases");
    expect(homePath("caregiver")).toBe("/caregiver/status");
    expect(homePath("admin")).toBe("/admin");
  });

  it("does not expose another role's route", () => {
    expect(resolveRoute("/insurer/cases", "hospital")).toEqual({
      path: "/hospital/intake",
      view: "hospital",
    });
    expect(resolveRoute("/hospital/intake", "caregiver")).toEqual({
      path: "/caregiver/status",
      view: "caregiver",
    });
  });

  it("lets the admin open every workspace under admin URLs", () => {
    expect(resolveRoute("/admin/hospital", "admin").view).toBe("hospital");
    expect(resolveRoute("/admin/insurer/alerts", "admin")).toMatchObject({
      view: "insurer",
      insurerSection: "alerts",
    });
    expect(resolveRoute("/admin/caregiver", "admin").view).toBe("caregiver");
  });

  it("builds navigation only for the signed-in role", () => {
    expect(navItems("hospital").map((item) => item.path)).toEqual([
      "/hospital/intake",
      "/hospital/cases",
    ]);
    expect(navItems("insurer").map((item) => item.path)).toEqual([
      "/insurer/cases",
      "/insurer/alerts",
      "/insurer/analytics",
    ]);
    expect(navItems("admin").map((item) => item.path)).toEqual([
      "/admin",
      "/admin/hospital",
      "/admin/hospital/cases",
      "/admin/insurer/cases",
      "/admin/insurer/alerts",
      "/admin/insurer/analytics",
      "/admin/caregiver",
    ]);
  });

  it("keeps analytics with the care team and submissions with the hospital", () => {
    expect(resolveRoute("/insurer/analytics", "insurer").insurerSection).toBe("analytics");
    expect(resolveRoute("/insurer/analytics", "hospital").path).toBe("/hospital/intake");
    expect(resolveRoute("/hospital/cases", "hospital").hospitalSection).toBe("cases");
    expect(resolveRoute("/hospital/cases", "caregiver").path).toBe("/caregiver/status");
  });
});
