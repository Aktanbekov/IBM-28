import os

os.environ["LLM_BACKEND"] = "rules"

from casebridge import brief, ingest, matching, safety  # noqa: E402
from casebridge.models import CaseBrief, Evidence, Fact  # noqa: E402


def demo_brief():
    ev = ingest.load_demo_case()
    return ev, brief.build(ev)


def test_demo_case_classified():
    _, b = demo_brief()
    assert b.case_type == "auto_accident"
    assert b.client_side == "plaintiff"
    assert b.county == "Santa Clara"


def test_every_fact_is_cited():
    ev, b = demo_brief()
    ids = {e.id for e in ev}
    for section in (b.timeline, b.parties, b.injuries, b.damages):
        for f in section:
            assert f.sources and set(f.sources) <= ids


def test_missing_evidence_detects_lost_witness_but_not_police_report():
    _, b = demo_brief()
    assert "Witness contact information" in b.missing_evidence
    assert "Police / collision report" not in b.missing_evidence


def test_deadlines_from_incident_date():
    _, b = demo_brief()
    dates = {d["date"] for d in b.deadlines}
    assert "2028-10-02" in dates          # 2-year personal injury
    assert "2026-10-30" in dates          # insurer's release deadline


def test_uncited_facts_are_dropped():
    b = CaseBrief("auto_accident", "plaintiff", None, "ok",
                  timeline=[Fact("cited", ["E1"]), Fact("made up", []), Fact("bad id", ["E9"])])
    b = safety.apply_guardrails(b, {"E1"})
    assert [f.text for f in b.timeline] == ["cited"]
    assert any("no source" in w for w in b.warnings)


def test_legal_advice_is_blocked():
    assert safety.is_advice("You should accept the offer.")
    assert safety.is_advice("Your case is worth $50,000.")
    assert not safety.is_advice("The insurer offered $1,200.")
    b = CaseBrief("auto_accident", "plaintiff", None, "Rear-end collision. You will win this.",
                  damages=[Fact("You should sign the release.", ["E1"])])
    b = safety.apply_guardrails(b, {"E1"})
    assert b.damages == [] and "win" not in b.summary


def test_redaction_removes_identity():
    ev, b = demo_brief()
    red = safety.redact_brief(b, safety.find_names([e.text for e in ev]))
    blob = str(red)
    for secret in ("Maria", "Lopez", "Kevin Holt", "555-0142", "8ABC123", "pgrant@", "04/12/1991"):
        assert secret not in blob, secret


def test_matching_filters_by_practice_area_and_side():
    results, excluded = matching.match("auto_accident", "plaintiff", "Santa Clara", ["Spanish"])
    assert results and all("plaintiff" in r["sides"] for r in results)
    assert all("auto_accident" in r["practice_areas"] for r in results)
    assert "Speaks Spanish" in results[0]["why"]
    assert excluded["side"] >= 1


def test_defense_side_detected():
    ev = ingest.number([Evidence("", "note", "note", "I rear-ended a car in Oakland and now they are suing me.")])
    b = brief.build(ev)
    assert b.client_side == "defense" and b.county == "Alameda"
