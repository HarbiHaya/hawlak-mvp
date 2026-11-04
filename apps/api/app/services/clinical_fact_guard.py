import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from app.schemas.voice import ClinicalFacts

_WHITESPACE = re.compile(r"\s+")
_DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


@dataclass(frozen=True, slots=True)
class FactDifference:
    path: str
    kind: Literal["added", "removed", "changed"]
    source: Any | None
    output: Any | None


@dataclass(frozen=True, slots=True)
class FactGuardReport:
    passed: bool
    differences: tuple[FactDifference, ...]


class ClinicalFactMismatchError(ValueError):
    """The composed output did not copy the complete approved fact set."""

    def __init__(self, report: FactGuardReport) -> None:
        super().__init__("composed script facts do not match the approved plan")
        self.report = report


def compare_clinical_facts(
    source: ClinicalFacts | dict[str, Any],
    output: ClinicalFacts | dict[str, Any],
) -> FactGuardReport:
    """Compare source facts exactly after a deliberately narrow normalization.

    This is structural equality, not semantic matching. List order, duplicates,
    additions and removals remain significant.
    """

    source_model = (
        source if isinstance(source, ClinicalFacts) else ClinicalFacts.model_validate(source)
    )
    output_model = (
        output if isinstance(output, ClinicalFacts) else ClinicalFacts.model_validate(output)
    )
    source_flat = _flatten(source_model.model_dump(by_alias=True, mode="json"))
    output_flat = _flatten(output_model.model_dump(by_alias=True, mode="json"))
    differences: list[FactDifference] = []

    for path in sorted(source_flat.keys() | output_flat.keys()):
        source_present = path in source_flat
        output_present = path in output_flat
        if not source_present:
            differences.append(FactDifference(path, "added", None, output_flat[path][1]))
        elif not output_present:
            differences.append(FactDifference(path, "removed", source_flat[path][1], None))
        elif source_flat[path][0] != output_flat[path][0]:
            differences.append(
                FactDifference(path, "changed", source_flat[path][1], output_flat[path][1])
            )

    return FactGuardReport(passed=not differences, differences=tuple(differences))


def ensure_clinical_facts_match(
    source: ClinicalFacts | dict[str, Any],
    output: ClinicalFacts | dict[str, Any],
) -> FactGuardReport:
    report = compare_clinical_facts(source, output)
    if not report.passed:
        raise ClinicalFactMismatchError(report)
    return report


def _flatten(value: Any, path: str = "$") -> dict[str, tuple[Any, Any]]:
    if isinstance(value, dict):
        flattened: dict[str, tuple[Any, Any]] = {}
        for key, child in value.items():
            flattened.update(_flatten(child, f"{path}.{key}"))
        return flattened
    if isinstance(value, list):
        flattened = {f"{path}.__length__": (len(value), len(value))}
        for index, child in enumerate(value):
            flattened.update(_flatten(child, f"{path}[{index}]"))
        return flattened
    return {path: (_normalize_scalar(value), value)}


def _normalize_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = unicodedata.normalize("NFKC", value).translate(_DIGIT_TRANSLATION).casefold()
    normalized = "".join(
        char for char in normalized if not unicodedata.category(char).startswith("P")
    )
    return _WHITESPACE.sub(" ", normalized).strip()
