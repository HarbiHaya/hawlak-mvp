"""Find personal identifiers in text that will reach the patient.

Patient-facing scripts may greet with an approved form of address, but must never carry the
registered full name, a phone number, a national or Iqama number, insurer member or policy
numbers, the internal case ID or the source file name.
"""

import re
from collections.abc import Iterable

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIGIT_RUN = re.compile(r"\d[\d\s\-().]*\d")
# ponytail: Saudi national ID (1…) and Iqama (2…) are 10 digits; other countries' IDs need
# their own pattern if Hawlak serves them.
_NATIONAL_ID = re.compile(r"[12]\d{9}")


def _normalize(text: str) -> str:
    return " ".join(text.translate(_DIGITS).casefold().split())


def find_identifier(
    texts: Iterable[str],
    *,
    full_name: str | None = None,
    phone_e164: str | None = None,
    member_id: str | None = None,
    policy_number: str | None = None,
    case_id: str | None = None,
    filename: str | None = None,
) -> str | None:
    """Return the kind of the first identifier found, or None when the texts are clean."""
    text = _normalize(" \n ".join(texts))
    digit_runs = [re.sub(r"\D", "", run) for run in _DIGIT_RUN.findall(text)]

    name = _normalize(full_name or "")
    if len(name.split()) >= 2 and name in text:
        return "full_name"
    phone = re.sub(r"\D", "", phone_e164 or "")[-9:]
    if len(phone) == 9 and any(phone in run for run in digit_runs):
        return "phone_number"
    for kind, value in (
        ("member_id", member_id),
        ("policy_number", policy_number),
        ("case_id", case_id),
        ("source_filename", filename),
    ):
        if value and len(value) >= 4 and _normalize(value) in text:
            return kind
    if any(_NATIONAL_ID.fullmatch(run) for run in digit_runs):
        return "national_id"
    return None
