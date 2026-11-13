"""Dose details a patient hears come from fixed fields, and each field says where it came from.

- prescribed: written in the discharge instructions.
- calculated: worked out by code from a prescribed dose and a confirmed strength.
- reminder_preference: a reminder time somebody chose.
- unknown: missing. Nobody, person or model, fills it in by guessing.

The model only phrases these in the patient's dialect; it never calculates.
"""

import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

# ponytail: Saudi time is UTC+3 all year (no daylight saving); per-patient zones if patients
# live elsewhere.
RIYADH = timezone(timedelta(hours=3))
REMINDER_TIME = r"^([01]\d|2[0-3]):[0-5]\d$"

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_UNITS = {
    "mcg": "mcg", "µg": "mcg", "ميكروغرام": "mcg", "مكغ": "mcg",
    "mg": "mg", "ملغ": "mg", "ملجم": "mg", "مجم": "mg", "مغ": "mg",
    "g": "g", "غرام": "g", "جرام": "g", "جم": "g",
    "ml": "ml", "مل": "ml",
    "iu": "iu", "units": "unit", "unit": "unit", "وحدة": "unit",
}  # fmt: skip
# Longest spelling first, and never the start of a longer word ("2 green" is not 2 g).
_QUANTITY = re.compile(
    r"(\d+(?:\.\d+)?)\s*(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")(?![^\W\d_])",
    re.IGNORECASE,
)
_SOLID = {"mcg", "mg", "g"}  # a tablet or capsule count only makes sense for a mass
# "Two 500 mg tablets": the instruction already gives the count, and its number is the
# strength, not the dose. Dividing would say one tablet. A false hit here only yields unknown.
_COUNT_WORD = re.compile(r"tab|cap|pill|حب|قرص|قراص|كبسول", re.IGNORECASE)


def _quantity(text: str | None) -> tuple[Decimal, str] | None:
    """The one quantity in the text. None when there is none, or more than one."""
    found = {
        (Decimal(amount), _UNITS[unit.lower()])
        for amount, unit in _QUANTITY.findall((text or "").translate(_DIGITS))
    }
    return found.pop() if len(found) == 1 else None


def _unknown(reason: str | None = None) -> dict:
    return {"value": None, "source": "unknown"} | ({"reason": reason} if reason else {})


def _units_per_dose(instruction: str, dose, strength) -> dict:
    if dose is None:
        return _unknown("prescribed_dose_unknown")
    if _COUNT_WORD.search(instruction):
        return _unknown("count_already_prescribed")
    if strength is None:
        return _unknown("unit_strength_unknown")
    # ponytail: same unit only; no mg-to-g conversion until a real plan needs it.
    if dose[1] != strength[1] or dose[1] not in _SOLID or strength[0] <= 0:
        return _unknown("unit_mismatch")
    count = dose[0] / strength[0]
    # A part of a tablet is never offered: whether it may be split is a pharmacist's call.
    if count != count.to_integral_value():
        return _unknown("not_whole_unit")
    return {"value": int(count), "source": "calculated"}


def dose_facts(medication: dict) -> dict:
    """The prescribed dose, the units per dose and the reminder times, each with its source."""
    instruction = medication.get("doseInstruction") or ""
    dose = _quantity(instruction)
    times = list(medication.get("reminderTimes") or [])
    return {
        "prescribedDose": (
            {"value": f"{dose[0]:f} {dose[1]}", "source": "prescribed"} if dose else _unknown()
        ),
        "unitsPerDose": _units_per_dose(
            instruction, dose, _quantity(medication.get("unitStrength"))
        ),
        "reminderTimes": {
            "value": times,
            "source": "reminder_preference" if times else "unknown",
        },
    }


def reminder_run_times(times: list[str], approved_at: datetime) -> list[tuple[str, datetime]]:
    """The next occurrence of each chosen clock time, in Saudi time, after approval."""
    # ponytail: one reminder per chosen time. Daily repeats need the course length, which the
    # discharge document does not give.
    local = approved_at.astimezone(RIYADH)
    runs = []
    for value in times:
        at = datetime.combine(local.date(), time.fromisoformat(value), RIYADH)
        at = at if at > local else at + timedelta(days=1)
        runs.append((value, at.astimezone(approved_at.tzinfo)))
    return runs


def reminder_medication_id(content_ref: str) -> str:
    """medications:<id> or medications:<id>@HH:MM -> <id>."""
    return re.sub(r"@\d\d:\d\d$", "", content_ref.split(":", 1)[-1])
