import { Icon } from "./Icon";
import type { CaregiverCase } from "./api";
import type { Locale } from "./i18n";

export type CaregiverMedication = CaregiverCase["medications"][number];

const copy = {
  ar: {
    needed: "مطلوب صورة العلبة",
    received: "وصلت الصورة",
    needs_attention: "يراجعها الصيدلي",
    confirmed: "أكّدها الصيدلي",
    missing: "لم تصل صورة",
    take: "صوّر علبة الدواء",
    retake: "أعد تصوير العلبة",
    hint: "احرص على أن يظهر الاسم والتركيز بوضوح في الصورة.",
    scheduled: "التذكير مفعّل",
    needs_support: "يتطلب دعماً",
  },
  en: {
    needed: "Box photo needed",
    received: "Photo received",
    needs_attention: "Pharmacist reviewing",
    confirmed: "Confirmed by pharmacist",
    missing: "No photo yet",
    take: "Take a box photo",
    retake: "Retake box photo",
    hint: "Keep the printed name and strength clearly in frame.",
    scheduled: "Reminder active",
    needs_support: "Support required",
  },
} as const;

export function photoProgress(items: CaregiverMedication[]): { received: number; total: number } {
  return {
    received: items.filter((item) => item.photoStatus && item.photoStatus !== "missing").length,
    total: items.length,
  };
}

export function CaregiverMedicineCard({
  item,
  locale,
  busy,
  onPhoto,
}: {
  item: CaregiverMedication;
  locale: Locale;
  busy: boolean;
  onPhoto: (file: File | undefined) => void;
}) {
  const t = copy[locale];
  const status = item.photoStatus ?? "missing";
  const needsRetake = status === "needs_attention";

  return <article className={`care-med care-med--${status}`}>
    <div className="care-med__identity">
      <span className="care-med__number" aria-hidden="true"><Icon name="pill" size={18} /></span>
      <div>
        <h3>{item.displayName}</h3>
        <span className={`photo-state photo-state--${status}`}>{t[status]}</span>
      </div>
    </div>
    {item.canUploadPhoto && status !== "confirmed" && <p>{t.hint}</p>}
    <div className="care-med__footer">
      <span className="care-med__reminder"><Icon name="clock" size={14} />{t[item.status]}</span>
      {item.canUploadPhoto && <label className="camera-action" aria-disabled={busy}>
        <Icon name="camera" size={19} />
        <span>{needsRetake ? t.retake : t.take}</span>
        <input
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          capture="environment"
          disabled={busy}
          onChange={(event) => {
            onPhoto(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </label>}
      {!item.canUploadPhoto && status === "missing" && <span className="care-med__waiting">{t.needed}</span>}
    </div>
  </article>;
}

