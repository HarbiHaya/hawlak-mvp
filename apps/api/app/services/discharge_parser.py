"""Read a discharge PDF into a draft the insurer reviews.

Deterministic only: text is copied from the hospital's document, never generated.
Nothing extracted here reaches a patient until the insurer approves the exact content.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal

from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_PAGES = 20
MAX_MEDICATIONS = 20

# Order matters: "stopped" phrases start with words that also open medication headings.
STOPPED_HEADINGS = (
    "stopped medicines", "stopped medications", "discontinued", "stop taking",
    "الأدوية الموقوفة", "الأدوية المتوقفة", "أدوية موقوفة", "أدوية متوقفة", "إيقاف", "ايقاف",
)  # fmt: skip
MEDICATION_HEADINGS = (
    "new medicines", "new medications", "discharge medications", "discharge medicines",
    "home medications", "medications", "medicines",
    "الأدوية الجديدة", "أدوية الخروج", "الأدوية", "الادوية",
)  # fmt: skip
OTHER_HEADINGS = (
    "activity", "diet", "warning signs", "red flags", "follow-up", "follow up", "instructions",
    "علامات الخطر", "علامات التحذير", "النشاط", "الحمية", "النظام الغذائي", "التغذية",
    "المتابعة", "التعليمات",
)  # fmt: skip

_BULLET = re.compile(r"^(?:[-•*·▪●–—]|\(?[0-9٠-٩]{1,3}[.)\-]|[A-Za-z][.)])\s+")
_MED_SEPARATOR = re.compile(r"\s*:\s*|\s+[-–—]\s+")
_DIGIT = re.compile(r"[0-9٠-٩]")

Kind = Literal["medications", "stopped", "other"]


@dataclass(frozen=True, slots=True)
class ExtractedMedication:
    name: str
    instruction: str


@dataclass(slots=True)
class Section:
    heading: str
    items: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DischargeExtraction:
    status: Literal["parsed", "no_text", "unreadable"]
    text: str = ""
    language: Literal["ar", "en"] = "en"
    medications: list[ExtractedMedication] = field(default_factory=list)
    stopped_heading: str = ""
    stopped_medications: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_api(self) -> dict:
        return {
            "status": self.status,
            "language": self.language,
            "text": self.text,
            "medications": [
                {"name": m.name, "instruction": m.instruction} for m in self.medications
            ],
            "stoppedMedications": self.stopped_medications,
            "sections": [{"heading": s.heading, "items": s.items} for s in self.sections],
            "notes": self.notes,
        }


def parse_discharge_pdf(content: bytes) -> DischargeExtraction:
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
    except Exception:  # pypdf raises many types for malformed or encrypted files
        logger.info("Discharge PDF could not be read")
        return DischargeExtraction(status="unreadable")
    text = "\n".join(pages)
    if not text.strip():
        # ponytail: scanned PDFs have no text layer; add OCR when hospitals send scans.
        return DischargeExtraction(status="no_text")
    return parse_discharge_text(text)


def parse_discharge_text(text: str) -> DischargeExtraction:
    text = unicodedata.normalize("NFKC", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    result = DischargeExtraction(status="parsed", text=text.strip(), language=_language(text))
    kind: Kind | None = None  # None until the first known heading: skips the letterhead
    section: Section | None = None
    meds: list[list[str]] = []

    for line in filter(None, lines):
        heading_kind = _heading_kind(line, kind is not None)
        if heading_kind is not None:
            kind = heading_kind
            heading = line.rstrip(":：").strip()
            if kind == "stopped":
                result.stopped_heading = result.stopped_heading or heading
            elif kind == "other":
                section = Section(heading)
                result.sections.append(section)
            continue
        if kind is None:
            continue

        bullet = _BULLET.match(line)
        item = line[bullet.end() :].strip() if bullet else line
        if kind == "medications":
            # A wrapped line ("with food") has no marker, separator or dose number.
            if bullet or _MED_SEPARATOR.search(item) or _DIGIT.search(item) or not meds:
                meds.append(_MED_SEPARATOR.split(item, maxsplit=1))
            else:
                meds[-1].append(item)  # wrapped line continues the previous instruction
        elif kind == "stopped":
            if bullet or not result.stopped_medications:
                result.stopped_medications.append(item)
            else:
                result.stopped_medications[-1] += f" {item}"
        elif section is not None:
            if bullet:
                section.items.append(item)
            elif ":" in item:
                result.notes.append(item)
            elif section.items:
                section.items[-1] += f" {item}"
            else:
                section.items.append(item)

    result.medications = [
        ExtractedMedication(parts[0][:200], " ".join(parts[1:])[:500])
        for parts in meds[:MAX_MEDICATIONS]
        if parts and parts[0]
    ]
    return result


def draft_medications(extraction: DischargeExtraction) -> list[dict]:
    """Shape extracted medicines as editable draft rows for the insurer to review."""
    return [
        {
            "medicationId": f"PDF-MED-{index:03d}",
            "displayName": medication.name,
            "doseInstruction": medication.instruction,
            "dispensed": True,
            "image": None,
            "reminderEnabled": False,
            "reminderScript": "",
            "unitStrength": None,
            "reminderTimes": [],
        }
        for index, medication in enumerate(extraction.medications, start=1)
    ]


def _heading_kind(line: str, started: bool) -> Kind | None:
    if _BULLET.match(line) or len(line) > 80:
        return None
    key = line.rstrip(":：").strip().lower()
    for kind, phrases in (
        ("stopped", STOPPED_HEADINGS),
        ("medications", MEDICATION_HEADINGS),
        ("other", OTHER_HEADINGS),
    ):
        if any(key == phrase or key.startswith(f"{phrase} ") for phrase in phrases):
            return kind  # type: ignore[return-value]
    letters = [char for char in line if char.isalpha()]
    # After the first known heading, a short ALL-CAPS line opens a new section.
    if started and len(letters) >= 3 and ":" not in line and line == line.upper():
        if all("A" <= char <= "Z" for char in letters):
            return "other"
    return None


def _language(text: str) -> Literal["ar", "en"]:
    arabic = sum("؀" <= char <= "ۿ" for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    return "ar" if arabic > latin else "en"
