import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CaregiverMedicineCard, photoProgress } from "./CaregiverMedicineCard";

describe("caregiver medicine capture", () => {
  it("opens the rear camera for a medicine that still needs a usable photo", () => {
    const html = renderToStaticMarkup(
      <CaregiverMedicineCard
        item={{
          medicationId: "med-1",
          displayName: "Zentorin 5 mg",
          status: "scheduled",
          photoStatus: "missing",
          canUploadPhoto: true,
        }}
        locale="en"
        busy={false}
        onPhoto={() => undefined}
      />,
    );

    expect(html).toContain('capture="environment"');
    expect(html).toContain("Take a box photo");
    expect(html).toContain("image/jpeg,image/png,image/webp,image/heic,image/heif");
  });

  it("reports progress without treating a missing photo as complete", () => {
    expect(photoProgress([
      { medicationId: "a", displayName: "A", status: "scheduled", photoStatus: "confirmed" },
      { medicationId: "b", displayName: "B", status: "scheduled", photoStatus: "received" },
      { medicationId: "c", displayName: "C", status: "scheduled", photoStatus: "missing" },
    ])).toEqual({ received: 2, total: 3 });
  });
});

