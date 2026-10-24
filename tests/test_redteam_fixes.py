"""Leaks found by IBM Bob's red-team session (tests/test_bob_redteam.py), each fixed in safety.py.
Kept here too so the fixes stay covered even if the red-team file changes."""
import os

os.environ["LLM_BACKEND"] = "rules"

import pytest  # noqa: E402

from casebridge import brief, ingest, safety  # noqa: E402
from casebridge.models import CaseBrief  # noqa: E402

NAMES = safety.find_names(["My name is Maria Lopez.", "Me llamo Rosa Martínez."])


@pytest.mark.parametrize("text,secret", [
    # OCR look-alike digits in names
    ("Mar1a Lopez called.", "Mar1a"), ("Ms. L0pez signed.", "L0pez"),
    ("M4rtinez, Rosa", "M4rtinez"), ("R0sa was there.", "R0sa"),
    # nicknames
    ("Rosie told the clerk.", "Rosie"),
])
def test_names(text, secret):
    assert secret not in safety.redact(text, NAMES)


@pytest.mark.parametrize("text,secret", [
    ("call four0eight 555-0142", "four0eight"),
    ("rosa @ mail.example.com", "mail.example"), ("rosa.m＠mail.example.com", "mail.example"),
    ("rosa.m(at)mail.example.com", "mail.example"),
    ("I live at 4120 Peralta, Fremont", "4120 Peralta"), ("P.O. Box 1234", "1234"),
    ("4120, apartment 12", "4120"),
    ("DOB 08.03.1984", "1984"), ("born in 1984", "1984"), ("DOB: March 1984", "1984"),
    ("nacida en 08/03/1984", "1984"), ("d.o.b.: 03/08/1984", "1984"),
    ("plate 7xyz456", "7xyz456"), ("7Abc234 drove off", "7Abc234"),
    ("VIN 1hgcm82633a004352", "1hgcm82633a004352"),
    ("policy number: ca-9981234", "9981234"), ("report sj-26-118842", "118842"),
    ("ref hc-55190", "55190"), ("hc-55190 was opened", "55190"),
    ("SSN 123 45 6789", "6789"), ("SSN 123.45.6789", "6789"), ("SSN 123456789", "123456789"),
    ("at 37.3230; -121.9480", "121.9480"), ("at 37°19′22″N 121°57′17″W", "121°57"),
])
def test_patterns(text, secret):
    assert secret not in safety.redact(text, {})


def test_brief_summary_with_ocr_name_and_nickname():
    b = CaseBrief("auto_accident", "plaintiff", None, "Mar1a L0pez, called Rosie by friends, was hit.")
    red = safety.redact_brief(b, NAMES)
    assert not any(s in red["summary"] for s in ("Mar1a", "L0pez", "Rosie"))


@pytest.mark.parametrize("text", [
    # Case facts that must survive all the wider patterns.
    "Vehicle 2: 2021 Ford F-150 hit the 2019 Honda Civic, driver side.",
    "Seen October 9, 2026, 15:40. Follow up in 10 days.",
    "Offer of $1,200 by October 30, 2026 [E5]. Cal. Code Civ. Proc. § 335.1.",
    "Missed 6 days of work. The phone2 app crashed. Stevens Creek Blvd at Winchester Blvd.",
    "Store #318, Mowry Avenue, Fremont. Aisle 4, produce.",
])
def test_case_facts_are_not_over_redacted(text):
    assert safety.redact(text, {}) == text


def test_demo_cases_still_clean():
    for case in ("maria", "rosa"):
        ev = ingest.load_demo_case(case)
        names = safety.find_names([e.text for e in ev])
        red = safety.redact_brief(brief.build(ev), names)
        assert safety.posting_blockers(red, names) == []
        assert "Potential plaintiff matter" in red["summary"]      # summary not wiped by fail-closed


def test_verbs_before_a_role_are_not_names():
    # "Contact adjuster Paula Grant" once turned "Contact" into a name.
    names = safety.find_names(["Contact adjuster Paula Grant at pgrant@summitmutual.example."])
    assert "Contact" not in names
    assert safety.redact("Contact adjuster Paula Grant.", names) == "Contact adjuster [ADJUSTER]."
