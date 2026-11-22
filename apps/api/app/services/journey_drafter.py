"""Draft the voice note, reminders and call scripts from the discharge document.

Every draft is only a proposal: the insurer reviews and approves the exact words.
The template drafter copies document facts into fixed bilingual sentences. The live
drafter lets the model rephrase in the patient's dialect, then guard_draft rejects any
number the document does not contain or any medicine that went missing, and the
template draft is used instead. Tablet counts and reminder times come only from the fixed
fields in dose_facts; the model phrases them and never calculates.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.dialects import get_dialect_profile
from app.services.discharge_parser import DischargeExtraction
from app.services.dose_facts import dose_facts

logger = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "journey-draft-v5.txt"
WARNING_HEADINGS = ("warning", "red flag", "علامات الخطر", "علامات التحذير")
ARABIC_HEADINGS = {"activity": "النشاط", "diet": "الغذاء", "follow": "المتابعة"}
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NAME_END = re.compile(r"[\d(,:،]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_IDENTIFYING_LABEL = re.compile(
    r"name|\bid\b|mrn|record|phone|mobile|member|policy|national|iqama|"
    r"اسم|هوية|إقامة|اقامة|ملف|جوال|هاتف|عضوية|وثيقة",
    re.IGNORECASE,
)
_EMERGENCY = re.compile(r"emergency|طوارئ|إسعاف|اسعاف", re.IGNORECASE)

TEXT = {
    "en": {
        "greeting": "Hello{label}. This message from Hawlak, on behalf of your care team, "
        "summarises your discharge instructions.",
        "medicines_elsewhere": "Your medicines come in separate messages, with a photo request "
        "and reminders.",
        "stopped": "Stop taking: {items}.",
        "warning": "If you notice any of the following, call {number} at once: {items}.",
        "warning_no_number": "If you notice any of the following, seek urgent medical care "
        "at once: {items}.",
        "closing": "Please keep this message for reference.",
        "reminder": "Hawlak reminder: it is time to take {name}. {instruction}",
        "units": "Number of tablets or capsules per dose: {count}.",
        "opening": "Hello{label}. This is Hawlak, calling on behalf of your care team to follow "
        "up on your recovery after discharge. I will ask a few short questions. "
        "Please answer yes or no.",
        "question": "Since leaving the hospital, have you had {item}?",
        "completion": "Thank you. Your answers have been recorded and shared with your care "
        "team. Goodbye.",
        "transfer": "Thank you. I will now transfer you to your care team. "
        "Please stay on the line.",
        "list": "; ",
    },
    "ar": {
        "greeting": "السلام عليكم{label}. هذه رسالة من حولك نيابةً عن فريق رعايتك، "
        "وتتضمن تعليمات الخروج من المستشفى.",
        "medicines_elsewhere": "ستصلك أدويتك في رسائل منفصلة، مع طلب صور العلب والتذكيرات.",
        "stopped": "يُرجى التوقف عن تناول: {items}.",
        "warning": "إذا لاحظت أياً مما يلي فاتصل على {number} فوراً: {items}.",
        "warning_no_number": "إذا لاحظت أياً مما يلي فاطلب الرعاية الطبية العاجلة فوراً: {items}.",
        "closing": "يُرجى الاحتفاظ بهذه الرسالة للرجوع إليها.",
        "reminder": "تذكير من حولك: حان موعد تناول {name}. {instruction}",
        "units": "عدد الحبات في كل جرعة: {count}.",
        "opening": "السلام عليكم{label}. معك حولك نيابةً عن فريق رعايتك لمتابعة حالتك بعد "
        "الخروج من المستشفى. سأطرح عليك أسئلة قصيرة، يُرجى الإجابة بنعم أو لا.",
        "question": "منذ خروجك من المستشفى، هل لاحظت: {item}؟",
        "completion": "شكراً لك. سُجّلت إجاباتك وأُبلغ بها فريق رعايتك. مع السلامة.",
        "transfer": "شكراً لك. سأحوّلك الآن إلى فريق رعايتك، يُرجى البقاء على الخط.",
        "list": "؛ ",
    },
}


class DraftRejected(ValueError):
    pass


@dataclass(slots=True)
class JourneyDraft:
    voice_script: str
    reminder_scripts: dict[str, str]
    call_opening: str
    call_questions: list[dict[str, str]]
    call_completion: str
    call_transfer: str
    generator: str
    source_language: str = "en"
    notes: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {to_camel(key): value for key, value in asdict(self).items()}


class DraftModel(Protocol):
    def generate(self, prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class TemplateJourneyDrafter:
    def draft(
        self,
        extraction: DischargeExtraction,
        medications: list[dict],
        label: str | None,
        language: str,
        dialect_code: str | None = None,
    ) -> JourneyDraft:
        greeting = f" {label}" if label else ""  # no approved form of address: no name
        text = TEXT["ar" if language == "ar" else "en"]
        warnings = [s for s in extraction.sections if _is_warning(s.heading)]
        others = [s for s in extraction.sections if not _is_warning(s.heading)]
        number = _emergency_number(extraction)

        # The voice note carries instructions only; medicines go to reminders and photos.
        lines = [text["greeting"].format(label=greeting)]
        if extraction.stopped_medications:
            items = text["list"].join(extraction.stopped_medications)
            lines.append(text["stopped"].format(items=items))
        for section in others:
            heading = _heading(section.heading, language)
            lines.append(f"{heading}: " + " ".join(_sentence(item) for item in section.items))
        warning_items = [item.rstrip(".") for s in warnings for item in s.items]
        if warning_items:
            key = "warning" if number else "warning_no_number"
            joined = text["list"].join(_lower_first(i, language) for i in warning_items)
            lines.append(text[key].format(number=number, items=joined))
        if medications:
            lines.append(text["medicines_elsewhere"])
        lines.append(text["closing"])

        return JourneyDraft(
            voice_script="\n".join(lines),
            reminder_scripts={
                m["medicationId"]: (
                    text["reminder"].format(
                        name=m["displayName"], instruction=_sentence(m["doseInstruction"])
                    )
                    + _units(m, text)
                ).strip()
                for m in medications
            },
            call_opening=text["opening"].format(label=greeting),
            call_questions=[
                {
                    "id": f"warning-{index}",
                    "prompt": text["question"].format(item=_lower_first(item, language)),
                }
                for index, item in enumerate(warning_items[:12], start=1)
            ],
            call_completion=text["completion"],
            call_transfer=text["transfer"],
            generator="template",
            source_language=extraction.language,
        )


class LiveJourneyDrafter:
    def __init__(self, model: DraftModel, model_name: str) -> None:
        self._model = model
        self._model_name = model_name
        self._fallback = TemplateJourneyDrafter()

    def draft(self, extraction, medications, label, language, dialect_code=None) -> JourneyDraft:
        payload = {
            "patientLabel": label,
            "language": language,
            "dialectProfile": (
                get_dialect_profile(dialect_code).as_prompt_input()
                if language == "ar" and dialect_code
                else None
            ),
            "medications": [
                {
                    **{k: m[k] for k in ("medicationId", "displayName", "doseInstruction")},
                    # Fixed fields: the model may say these, and may not work out its own.
                    "unitsPerDose": dose_facts(m)["unitsPerDose"]["value"],
                    "reminderTimes": dose_facts(m)["reminderTimes"]["value"],
                }
                for m in medications
            ],
            "stoppedMedications": extraction.stopped_medications,
            "sections": [{"heading": s.heading, "items": s.items} for s in extraction.sections],
            "notes": [note for note in extraction.notes if not _identifying(note)],
        }
        try:
            raw = self._model.generate(PROMPT_PATH.read_text(encoding="utf-8"), payload)
            draft = JourneyDraft(
                voice_script=raw["voiceScript"],
                reminder_scripts={r["medicationId"]: r["script"] for r in raw["reminderScripts"]},
                call_opening=raw["callOpening"],
                call_questions=[
                    {"id": f"warning-{i}", "prompt": prompt}
                    for i, prompt in enumerate(raw["callQuestions"][:12], start=1)
                ],
                call_completion=raw["callCompletion"],
                call_transfer=raw["callTransfer"],
                generator=f"openai:{self._model_name}",
                source_language=extraction.language,
            )
            guard_draft(draft, extraction, medications)
            return draft
        except Exception as exc:  # any provider or guard failure falls back to the template
            logger.warning("Live journey draft rejected; using template: %s", type(exc).__name__)
            fallback = self._fallback.draft(extraction, medications, label, language, dialect_code)
            fallback.notes.append("live_draft_rejected")
            return fallback


def _identifying(note: str) -> bool:
    """A "label: value" note that names or numbers the patient stays out of the model input."""
    label = note.split(":", 1)[0]
    return bool(_IDENTIFYING_LABEL.search(label)) and not _EMERGENCY.search(label)


def guard_draft(draft: JourneyDraft, extraction: DischargeExtraction, medications: list) -> None:
    """Reject a draft that adds a number, drops an instruction number, names a dispensed
    medicine in the voice note, or leaves a medicine's name out of its reminder."""
    source = " ".join(
        [
            extraction.text,
            *(f"{m['displayName']} {m['doseInstruction']}" for m in medications),
            *(_fixed_numbers(m) for m in medications),
        ]
    )
    allowed = _numbers(source)
    texts = [draft.voice_script, draft.call_opening, draft.call_completion, draft.call_transfer]
    texts += [q["prompt"] for q in draft.call_questions] + list(draft.reminder_scripts.values())
    invented = set().union(*(_numbers(t) for t in texts)) - allowed
    if invented:
        raise DraftRejected(f"number not in the document: {sorted(invented)}")
    script = draft.voice_script.casefold()
    instruction_numbers = _numbers(" ".join(i for s in extraction.sections for i in s.items))
    if not instruction_numbers <= _numbers(draft.voice_script):
        raise DraftRejected("instruction number missing from the voice note")
    for medication in medications:
        if _medicine_name(medication["displayName"]).casefold() in script:
            raise DraftRejected("medicine in the voice note")
        reminder = draft.reminder_scripts.get(medication["medicationId"], "")
        if reminder and medication["displayName"] not in reminder:
            raise DraftRejected("medicine missing from its reminder")


class OpenAIDraftModel:
    SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "voiceScript",
            "reminderScripts",
            "callOpening",
            "callQuestions",
            "callCompletion",
            "callTransfer",
        ],  # fmt: skip
        "properties": {
            "voiceScript": {"type": "string"},
            "reminderScripts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["medicationId", "script"],
                    "properties": {
                        "medicationId": {"type": "string"},
                        "script": {"type": "string"},
                    },
                },
            },
            "callOpening": {"type": "string"},
            "callQuestions": {"type": "array", "items": {"type": "string"}},
            "callCompletion": {"type": "string"},
            "callTransfer": {"type": "string"},
        },
    }

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=45)
        self._model = model

    def generate(self, prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.responses.create(
            model=self._model,
            instructions=prompt,
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "journey_draft",
                    "schema": self.SCHEMA,
                    "strict": True,
                }
            },
            store=False,
        )
        return json.loads(response.output_text)


def build_journey_drafter(settings) -> TemplateJourneyDrafter | LiveJourneyDrafter:
    if settings.demo_provider_mode == "live" and settings.openai_api_key:
        model = OpenAIDraftModel(
            settings.openai_api_key.get_secret_value(), settings.openai_text_model
        )
        return LiveJourneyDrafter(model, settings.openai_text_model)
    return TemplateJourneyDrafter()


def _medicine_name(display_name: str) -> str:
    """The name part of a display name ("Renal multivitamin, one tablet" -> "Renal multivitamin").

    ponytail: best effort; a transliteration ("فوروسيميد") slips through to the reviewer,
    who approves every word.
    """
    return _NAME_END.split(display_name, maxsplit=1)[0].strip() or display_name


def _units(medication: dict, text: dict) -> str:
    """The calculated count as a fixed sentence; nothing when it is unknown."""
    count = dose_facts(medication)["unitsPerDose"]["value"]
    return f" {text['units'].format(count=count)}" if count else ""


def _fixed_numbers(medication: dict) -> str:
    facts = dose_facts(medication)
    return f"{facts['unitsPerDose']['value'] or ''} {' '.join(facts['reminderTimes']['value'])}"


def to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text.translate(_DIGITS)))


def _is_warning(heading: str) -> bool:
    return any(key in heading.lower() for key in WARNING_HEADINGS)


def _emergency_number(extraction: DischargeExtraction) -> str:
    for text in [*(s.heading for s in extraction.sections if _is_warning(s.heading))]:
        if found := re.search(r"\b\d{3,4}\b", text.translate(_DIGITS)):
            return found.group()
    for note in extraction.notes:
        if any(key in note.lower() for key in ("emergency", "طوارئ", "الطوارئ")):
            if found := re.search(r"\b\d{3,4}\b", note.translate(_DIGITS)):
                return found.group()
    return ""


def _heading(heading: str, language: str) -> str:
    if language == "ar":
        for key, arabic in ARABIC_HEADINGS.items():
            if heading.lower().startswith(key):
                return arabic
        return heading
    return heading.capitalize() if heading.isupper() else heading


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?؟" else f"{text}."


def _lower_first(text: str, language: str) -> str:
    text = text.strip().rstrip(".")
    if language == "en" and len(text) > 1 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text
