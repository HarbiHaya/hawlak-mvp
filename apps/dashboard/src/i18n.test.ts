import { describe, expect, it } from "vitest";

import { plural } from "./i18n";

const plans = { zero: "لا خطط", one: "خطة واحدة", two: "خطتان", few: "{n} خطط", many: "{n} خطةً", other: "{n} خطة" };

describe("plural", () => {
  it("agrees the Arabic noun with the number", () => {
    expect([0, 1, 2, 3, 10, 11, 99, 100].map((n) => plural(n, "ar", plans))).toEqual([
      "لا خطط", "خطة واحدة", "خطتان", "٣ خطط", "١٠ خطط", "١١ خطةً", "٩٩ خطةً", "١٠٠ خطة",
    ]);
  });

  it("falls back to other and uses English rules for English", () => {
    expect(plural(5, "ar", { other: "{n} حالة" })).toBe("٥ حالة");
    expect(plural(1, "en", { one: "{n} plan", other: "{n} plans" })).toBe("1 plan");
    expect(plural(0, "en", { one: "{n} plan", other: "{n} plans" })).toBe("0 plans");
  });
});
