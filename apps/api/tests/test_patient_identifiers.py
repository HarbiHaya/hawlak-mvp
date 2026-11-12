from app.services.patient_identifiers import find_identifier

CASE = {
    "full_name": "مريم خالد العتيبي",
    "phone_e164": "+966501234567",
    "member_id": "SYN-4471203",
    "policy_number": "POL-SYN-88120",
    "case_id": "case_poc_01",
    "filename": "synthetic-discharge.pdf",
}


def found(text: str) -> str | None:
    return find_identifier([text], **CASE)


def test_clean_patient_text_passes():
    assert found("السلام عليكم أم نورة. خذي دواء تجريبي ألف 5 ملغ مرة يومياً.") is None
    assert found("إذا شعرتِ بألم في الصدر فاتصلي على 997 فوراً.") is None
    assert found("Hello. Take 1 tablet at 08:00 for 14 days.") is None


def test_each_case_identifier_is_caught():
    assert found("السلام عليكم مريم  خالد العتيبي.") == "full_name"
    assert found("We will call you on 0501234567.") == "phone_number"
    assert found("رقمك ٠٥٠ ١٢٣ ٤٥٦٧") == "phone_number"
    assert found("Your member number is syn-4471203.") == "member_id"
    assert found("Policy POL-SYN-88120 covers this.") == "policy_number"
    assert found("Reference case_poc_01.") == "case_id"
    assert found("See synthetic-discharge.pdf for details.") == "source_filename"


def test_a_saudi_national_or_iqama_number_is_caught_without_knowing_it():
    assert found("Your ID 1098765432 is on file.") == "national_id"
    assert found("رقم الإقامة ٢٠٩٨٧٦٥٤٣٢") == "national_id"


def test_a_one_word_name_is_not_treated_as_a_full_name():
    assert find_identifier(["Hello Maha."], full_name="Maha") is None
