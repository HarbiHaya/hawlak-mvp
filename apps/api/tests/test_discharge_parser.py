from io import BytesIO

from pypdf import PdfWriter

from app.services.discharge_parser import (
    draft_medications,
    parse_discharge_pdf,
    parse_discharge_text,
)


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_reads_medications_and_sections_from_the_synthetic_discharge_pdf(fixtures_dir):
    result = parse_discharge_pdf((fixtures_dir / "approved-plan.abu-mohammed.pdf").read_bytes())

    assert result.status == "parsed"
    assert result.language == "en"
    assert [(m.name, m.instruction) for m in result.medications] == [
        ("Fictional medicine A", "5 mg, 1 tablet, once daily (morning)"),
        ("Fictional medicine B", "10 mg, 1 tablet, once daily (evening)"),
        ("Fictional medicine C", "20 mg, 1 tablet, twice daily (morning and evening)"),
    ]
    assert result.stopped_medications == ["Fictional medicine D"]
    assert [(s.heading, s.items) for s in result.sections] == [
        ("ACTIVITY", ["Take short, slow walks around the house and rest when tired."]),
        ("DIET", ["Prefer low-salt meals."]),
        ("WARNING SIGNS - CALL 997 AT ONCE", ["New chest pain or pressure", "Shortness of breath"]),
    ]
    assert result.notes == ["Emergency number: 997", "Expected medicine-box photos: 3"]
    assert "NEW MEDICINES" in result.text


def test_reports_a_pdf_without_text_instead_of_guessing():
    result = parse_discharge_pdf(blank_pdf())

    assert result.status == "no_text"
    assert result.medications == []


def test_reports_an_unreadable_pdf():
    assert parse_discharge_pdf(b"%PDF-1.4 not really a pdf").status == "unreadable"


def test_reads_arabic_headings_numbering_and_wrapped_lines():
    text = "\n".join(
        [
            "خطة الخروج",
            "الأدوية الجديدة",
            "١. دواء تجريبي ألف: قرص واحد صباحاً",
            "• دواء تجريبي باء - قرص مساءً",
            "مع الأكل",
            "الأدوية الموقوفة",
            "- دواء تجريبي دال",
            "علامات الخطر",
            "- ألم جديد في الصدر",
        ]
    )

    result = parse_discharge_text(text)

    assert result.language == "ar"
    assert [(m.name, m.instruction) for m in result.medications] == [
        ("دواء تجريبي ألف", "قرص واحد صباحاً"),
        ("دواء تجريبي باء", "قرص مساءً مع الأكل"),
    ]
    assert result.stopped_medications == ["دواء تجريبي دال"]
    assert [(s.heading, s.items) for s in result.sections] == [
        ("علامات الخطر", ["ألم جديد في الصدر"])
    ]


def test_medications_become_editable_draft_rows(fixtures_dir):
    result = parse_discharge_pdf((fixtures_dir / "approved-plan.abu-mohammed.pdf").read_bytes())

    medications = draft_medications(result)

    assert [m["displayName"] for m in medications] == [
        "Fictional medicine A",
        "Fictional medicine B",
        "Fictional medicine C",
    ]
    assert medications[0] == {
        "medicationId": "PDF-MED-001",
        "displayName": "Fictional medicine A",
        "doseInstruction": "5 mg, 1 tablet, once daily (morning)",
        "dispensed": True,
        "image": None,
        "reminderEnabled": False,
        "reminderScript": "",
    }
