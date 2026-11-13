"""Check a medicine-box photo against the approved plan, without advising anyone.

Hawlak asks for the approved medicines one at a time, so each photo is linked to the
medicine it was requested for (its slot), never by model guess. A vision model then reads
only what is printed on the box, and code checks it against that one medicine. The sender
only ever gets one of the fixed replies below; a mismatch goes to a person as an alert.
"""

import asyncio
import base64
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "medicine-label-v1.txt"

# Fixed replies. {name} is only ever an insurer-approved medicine name; no reply gives a
# verdict on the photo.
PHOTO_REPLIES = {
    "ar": {
        "request": "فضلاً صوّر علبة الدواء {n} من {total}: {name}، وأرسل الصورة هنا.",
        "next": "وصلت الصورة، شكراً. الآن صوّر علبة الدواء {n} من {total}: {name}.",
        "retake": "الصورة غير واضحة. فضلاً صوّر اسم الدواء المكتوب على علبة {name} مرة ثانية.",
        "complete": "شكراً، وصلت صور كل الأدوية. بيراجعها الصيدلي ويتواصل معكم إذا احتاج.",
        "received_extra": "وصلت الصورة، شكراً.",
    },
    "en": {
        "request": "Please photograph medicine box {n} of {total}: {name}, and send it here.",
        "next": "Photo received, thank you. Now photograph medicine box {n} of {total}: {name}.",
        "retake": "The photo is not clear. Please photograph the name printed on the {name} "
        "box again.",
        "complete": "Thank you, photos of all medicines arrived. A pharmacist will review them "
        "and contact you if needed.",
        "received_extra": "Photo received, thank you.",
    },
}
MISMATCH = {"strength_mismatch", "different_medicine"}

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
        return asdict(self)


def _doses(text: str) -> set[str]:
    return {
        f"{float(n):g}{u.lower().rstrip('s')}" for n, u in _DOSE.findall(text.translate(_DIGITS))
    }


def _words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(text)} - _UNITS


def compare_reading(reading: LabelReading | None, medication: dict) -> str:
    """Check the box against the one medicine it was requested for. Returns matched,
    strength_mismatch, different_medicine, unreadable, or not_checked (no reader, so a
    person checks it)."""
    if reading is None:
        return "not_checked"
    if not reading.readable or not reading.name:
        return "unreadable"
    # ponytail: word overlap with the approved display name; an Arabic-only plan name will not
    # match a Latin box and lands in different_medicine, which a person then reviews.
    if not _words(reading.name) & _words(medication["displayName"]):
        return "different_medicine"
    label_doses = _doses(f"{reading.name} {reading.strength or ''}")
    plan_doses = _doses(f"{medication['displayName']} {medication['doseInstruction']}")
    if label_doses and plan_doses and not label_doses & plan_doses:
        return "strength_mismatch"
    return "matched"


def reply(language: str, kind: str, **values) -> str:
    return PHOTO_REPLIES.get(language, PHOTO_REPLIES["ar"])[kind].format(**values)


def photo_request_text(medications: list[dict], language: str) -> str | None:
    """The first request, sent after approval. None when no medicine was dispensed."""
    dispensed = [m for m in medications if m["dispensed"]]
    if not dispensed:
        return None
    return reply(language, "request", n=1, total=len(dispensed), name=dispensed[0]["displayName"])


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
            # Low detail keeps each read to a small fixed image budget; box print is large text.
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_image", "image_url": image, "detail": "low"}],
                }
            ],
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
