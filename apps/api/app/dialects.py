from dataclasses import asdict, dataclass
from typing import Literal, cast

DialectCode = Literal["ar-SA-hijazi", "ar-SA-najdi", "ar-SA-janoubi"]


@dataclass(frozen=True, slots=True)
class DialectProfile:
    code: DialectCode
    label_ar: str
    label_en: str
    region: str
    style: str
    natural_phrasing: tuple[str, ...]
    avoid: tuple[str, ...]

    def as_prompt_input(self) -> dict:
        return asdict(self)


DIALECT_PROFILES: dict[DialectCode, DialectProfile] = {
    "ar-SA-hijazi": DialectProfile(
        code="ar-SA-hijazi",
        label_ar="حجازي",
        label_en="Hijazi",
        region="Jeddah, Makkah and the western Hijaz",
        style=(
            "Warm, easy urban Hijazi Saudi Arabic. Use a light everyday register that sounds "
            "natural in a one-to-one WhatsApp voice note, not a caricature."
        ),
        natural_phrasing=("هذي تعليماتك", "خليك منتبه", "دحين", "إذا حسّيت"),
        avoid=("heavy Modern Standard Arabic", "Egyptian wording", "exaggerated slang"),
    ),
    "ar-SA-najdi": DialectProfile(
        code="ar-SA-najdi",
        label_ar="نجدي",
        label_en="Najdi",
        region="Riyadh and central Saudi Arabia",
        style=(
            "Clear contemporary Najdi Saudi Arabic. Keep it warm, direct and respectful, as a "
            "Saudi clinician would speak naturally to one patient."
        ),
        natural_phrasing=("هذي تعليماتك", "خذ الدوا", "خلك منتبه", "إذا حسّيت"),
        avoid=("heavy Modern Standard Arabic", "Bedouin caricature", "Gulf dialect mixing"),
    ),
    "ar-SA-janoubi": DialectProfile(
        code="ar-SA-janoubi",
        label_ar="جنوبي",
        label_en="Southern Saudi",
        region="Southern Saudi Arabia",
        style=(
            "Light, broadly understandable Southern Saudi Arabic. Keep the regional flavor "
            "gentle because southern speech is diverse; clarity and respect come first."
        ),
        natural_phrasing=("هذي تعليماتك", "خلك منتبه", "لا تنسى", "إذا حسّيت"),
        avoid=("heavy Modern Standard Arabic", "invented spellings", "regional caricature"),
    ),
}


def get_dialect_profile(code: str) -> DialectProfile:
    try:
        return DIALECT_PROFILES[cast(DialectCode, code)]
    except KeyError as exc:
        raise ValueError(f"unsupported dialect code: {code}") from exc


def dialect_options() -> list[dict[str, str]]:
    return [
        {
            "code": profile.code,
            "labelAr": profile.label_ar,
            "labelEn": profile.label_en,
        }
        for profile in DIALECT_PROFILES.values()
    ]
