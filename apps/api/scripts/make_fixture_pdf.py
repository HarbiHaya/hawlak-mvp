"""Render the fake discharge-plan PDF from the approved-plan fixture, deterministically.

The PDF stands in for the hospital's source document: the API reads structured plans, never
PDFs. Its sha256 becomes approvedPlan.source.sourceHash in the plan and in the expected event.
After editing the plan fixture, run from apps/api:

    uv run python -m scripts.make_fixture_pdf
"""

import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
PLAN_FILE = FIXTURES / "approved-plan.abu-mohammed.json"
EVENT_FILE = FIXTURES / "expected-review-event.abu-mohammed.json"
PDF_FILE = FIXTURES / "approved-plan.abu-mohammed.pdf"

TITLE, HEADING, BODY, SMALL = ("F2", 13), ("F2", 11), ("F1", 11), ("F1", 9)


def _lines(plan: dict) -> list[tuple[tuple[str, int], str]]:
    case, approved = plan["case"], plan["approvedPlan"]
    facts = approved["clinicalFacts"]
    lines = [
        (TITLE, "SYNTHETIC DISCHARGE PLAN - DEMO ONLY - NOT A REAL PATIENT"),
        (SMALL, plan["reviewStatus"]),
        (BODY, ""),
        (BODY, f"Record: {approved['source']['recordId']}    Patient ref: {case['patientRef']}"),
        (BODY, f"Approved by {approved['approvedBy']} at {approved['approvedAt']}"),
        (BODY, f"Plan {approved['planId']}, version {approved['version']}"),
        (BODY, ""),
        (HEADING, "NEW MEDICINES"),
    ]
    for number, med in enumerate(facts["newMedicines"], start=1):
        detail = f"{med['strength']}, {med['dose']}, {med['frequency']} ({med['timing']})"
        lines.append((BODY, f"{number}. {med['name']}: {detail}"))
    sections = [
        ("STOPPED MEDICINES", facts["stoppedMedicines"]),
        ("ACTIVITY", facts["activityInstructions"]),
        ("DIET", facts["dietInstructions"]),
        (f"WARNING SIGNS - CALL {facts['emergencyNumber']} AT ONCE", facts["redFlags"]),
    ]
    for heading, items in sections:
        lines += [(BODY, ""), (HEADING, heading)]
        lines += [(BODY, f"- {item}") for item in items]
    lines += [
        (BODY, ""),
        (BODY, f"Emergency number: {facts['emergencyNumber']}"),
        (BODY, f"Expected medicine-box photos: {case['expectedBoxCount']}"),
    ]
    return lines


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(plan: dict) -> bytes:
    """One A4 page in standard Helvetica with no dates, so the same plan gives the same bytes."""
    ops = ["BT", "56 800 Td", "16 TL"]
    for (font, size), text in _lines(plan):
        ops.append(f"/{font} {size} Tf ({_escape(text)}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")  # raises on characters Helvetica cannot show

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Title (Synthetic discharge plan - demo only) >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_at = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\n" % (len(objects) + 1)
    pdf += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(pdf)


def main() -> None:
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    pdf = render_pdf(plan)
    PDF_FILE.write_bytes(pdf)

    digest = "sha256:" + hashlib.sha256(pdf).hexdigest()
    plan["approvedPlan"]["source"]["sourceHash"] = digest
    event = json.loads(EVENT_FILE.read_text(encoding="utf-8"))
    event["approvedPlan"]["sourceHash"] = digest
    for path, data in ((PLAN_FILE, plan), (EVENT_FILE, event)):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PDF_FILE.name} ({len(pdf)} bytes); sourceHash is now {digest}")


if __name__ == "__main__":
    main()
