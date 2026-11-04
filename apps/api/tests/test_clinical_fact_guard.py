from copy import deepcopy

import pytest

from app.schemas.voice import ClinicalFacts
from app.services.clinical_fact_guard import (
    ClinicalFactMismatchError,
    compare_clinical_facts,
    ensure_clinical_facts_match,
)


def facts_from(plan: dict) -> dict:
    return plan["approvedPlan"]["clinicalFacts"]


def test_exact_facts_and_narrow_normalization_pass(plan):
    source = facts_from(plan)
    output = deepcopy(source)
    output["emergencyNumber"] = "٩٩٧"
    output["redFlags"][0] = "  New chest pain, or pressure  "

    assert compare_clinical_facts(source, output).passed is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["newMedicines"][0].update({"dose": "2 tablets"}),
        lambda value: value["newMedicines"].pop(),
        lambda value: value["stoppedMedicines"].append("Fictional medicine X"),
        lambda value: value.update({"emergencyNumber": "998"}),
        lambda value: value["redFlags"].pop(),
        lambda value: value["dietInstructions"].append("New advice"),
    ],
)
def test_every_fact_mutation_fails_closed(plan, mutate):
    source = facts_from(plan)
    output = deepcopy(source)
    mutate(output)

    with pytest.raises(ClinicalFactMismatchError):
        ensure_clinical_facts_match(source, output)


def test_schema_rejects_extra_fact_fields(plan):
    output = deepcopy(facts_from(plan))
    output["newAdvice"] = "not allowed"

    with pytest.raises(ValueError):
        ClinicalFacts.model_validate(output)
