"""PDF intake: real form-style PDFs become one sentence per field; scanned or broken PDFs say so."""
from pathlib import Path

from casebridge import brief, ingest, rules
from casebridge.models import Evidence

PDF = Path(__file__).with_name("fixture_police_report.pdf")   # fictional report, printed to PDF


def test_form_pdf_gives_one_sentence_per_field():
    text = ingest.pdf_text(PDF.read_bytes())
    sents = rules.sentences(Evidence("E1", "document", "report.pdf", text))
    assert "Report number: SJ-2026-104233." in sents
    assert "Vehicle 2: 2021 Ford F-150, plate 8ABC123, driver Kevin Holt." in sents
    assert all("\n" not in s for s in sents)


def test_pdf_builds_a_cited_brief():
    ev = ingest.number([Evidence("", "document", "report.pdf", ingest.pdf_text(PDF.read_bytes()), "report.pdf")])
    b = brief.build(ev, use_llm=False)
    assert b.case_type == "auto_accident" and b.county == "Santa Clara"
    assert any("Kevin Holt" in f.text and f.sources == ["E1"] for f in b.parties)


def test_wrapped_prose_is_rejoined():
    text = "The other car ran the red light and\nhit my passenger door.\nClaim number: 77-1"
    assert ingest._reflow(text) == "The other car ran the red light and hit my passenger door.\nClaim number: 77-1."


def test_scanned_or_broken_pdf_explains_itself():
    assert ingest.pdf_text(b"not a pdf").startswith("[Could not read this PDF")
