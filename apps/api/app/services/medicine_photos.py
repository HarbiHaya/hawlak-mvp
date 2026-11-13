"""Check a medicine-box photo against the approved plan, without advising anyone.

A vision model reads only what is printed on the box (name, strength, form). Code, not the
model, compares that reading with the approved medicines. The sender only ever gets one of
the fixed replies below; a mismatch goes to a person as an alert.
"""

import asyncio
import base64
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "medicine-label-v1.txt"

# Fixed, pre-approved replies. They never name a medicine, a dose or a judgement.
PHOTO_REPLIES = {
    "ar": {
        "received": "وصلت صورة العلبة {n} من {total}، شكراً.",
        "received_extra": "وصلت الصورة، شكراً.",
        "retake": "الصورة غير واضحة. فضلاً صوّر اسم الدواء المكتوب على العلبة مرة ثانية.",
        "complete": "شكراً، وصلت صور كل الأدوية. بيراجعها الصيدلي ويتواصل معكم إذا احتاج.",
    },
    "en": {
        "received": "Photo {n} of {total} received, thank you.",
        "received_extra": "Photo received, thank you.",
        "retake": "The photo is not clear. Please photograph the medicine name on the box again.",
        "complete": "Thank you, photos of all medicines arrived. A pharmacist will review them "
        "and contact you if needed.",
    },
}

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DOSE = re.compile(r"(\d+(?:\.\d+)?)\s*(mcg|µg|mg|g|ml|iu|units?|%)", re.I)
_WORD = re.compile(r"[^\W\d_]{3,}")
_UNITS = {"mcg", "mg", "ml", "iu", "unit", "units", "tablet", "tablets", "capsule", "capsules"}


@dataclass(frozen=True, slots=True)
class LabelReading:
    readable: bool
    name: str | None
    strength: str | None
    form: str | None

    def to_json(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "readable"}


def _doses(text: str) -> set[str]:
    return {
        f"{float(n):g}{u.lower().rstrip('s')}" for n, u in _DOSE.findall(text.translate(_DIGITS))
    }


def _words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(text)} - _UNITS


def compare_reading(
    reading: LabelReading | None, medications: list[dict]
) -> tuple[str, str | None]:
    """Return (status, medicationId). Statuses: matched, strength_mismatch, not_in_plan,
    unreadable, not_checked (no reader configured, so a person checks it)."""
    if reading is None:
        return "not_checked", None
    if not reading.readable or not reading.name:
        return "unreadable", None
    name_words = _words(reading.name)
    label_doses = _doses(f"{reading.name} {reading.strength or ''}")
    for medication in medications:
        # ponytail: word overlap on the plan's display name; an Arabic-only plan name will not
        # match a Latin box and lands in not_in_plan, which a person then reviews.
        if not name_words & _words(medication["displayName"]):
            continue
        plan_doses = _doses(f"{medication['displayName']} {medication['doseInstruction']}")
        if label_doses and plan_doses and not label_doses & plan_doses:
            return "strength_mismatch", medication["medicationId"]
        return "matched", medication["medicationId"]
    return "not_in_plan", None


class OpenAILabelReader:
    SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["readable", "name", "strength", "form"],
        "properties": {
            "readable": {"type": "boolean"},
            "name": {"type": ["string", "null"]},
            "strength": {"type": ["string", "null"]},
            "form": {"type": ["string", "null"]},
        },
    }

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=30)
        self._model = model

    async def read(self, content: bytes, mime_type: str) -> LabelReading:
        return await asyncio.to_thread(self._read, content, mime_type)

    def _read(self, content: bytes, mime_type: str) -> LabelReading:
        image = f"data:{mime_type};base64,{base64.b64encode(content).decode()}"
        response = self._client.responses.create(
            model=self._model,
            instructions=PROMPT_PATH.read_text(encoding="utf-8"),
            input=[{"role": "user", "content": [{"type": "input_image", "image_url": image}]}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "medicine_label",
                    "schema": self.SCHEMA,
                    "strict": True,
                }
            },
            store=False,
        )
        data = json.loads(response.output_text)
        return LabelReading(
            readable=bool(data["readable"]),
            name=_clip(data["name"]),
            strength=_clip(data["strength"]),
            form=_clip(data["form"]),
        )


def _clip(value: str | None) -> str | None:
    return value.strip()[:120] or None if value else None


def build_label_reader(settings) -> OpenAILabelReader | None:
    """Live mode reads labels; mock mode leaves every photo for a person to check."""
    if settings.demo_provider_mode == "live" and settings.openai_api_key:
        return OpenAILabelReader(
            settings.openai_api_key.get_secret_value(), settings.openai_vision_model
        )
    return None
