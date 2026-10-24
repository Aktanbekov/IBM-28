"""The user stories from our pitch, run end to end through the engine (offline rules mode).
If one of these fails, a promise we make to judges is broken."""
import os

os.environ["LLM_BACKEND"] = "rules"

from casebridge import brief, ingest, matching, safety  # noqa: E402
from casebridge.models import Evidence  # noqa: E402


def run(*items):
    """Build a brief from (kind, title, text) tuples and match it, like the app does."""
    ev = ingest.number([Evidence("", kind, title, text) for kind, title, text in items])
    b = brief.build(ev)
    results, _ = matching.match(b.case_type, b.client_side, b.county, b.languages)
    return ev, b, results


def no_advice(b):
    text = " ".join(f.text for f in b.timeline + b.parties + b.injuries + b.damages) + b.summary
    return not safety.is_advice(text)


def test_1_car_accident_maria():
    ev = ingest.load_demo_case("maria")
    b = brief.build(ev)
    results, _ = matching.match(b.case_type, b.client_side, b.county, b.languages)
    assert (b.case_type, b.client_side) == ("auto_accident", "plaintiff")
    assert "2026-10-30" in {d["date"] for d in b.deadlines} and b.warnings
    assert results and all("plaintiff" in r["sides"] for r in results) and no_advice(b)


def test_2_hit_by_a_city_bus_gets_the_six_month_government_claim_deadline():
    _, b, _ = run(("note", "note", "On September 3, 2026 a VTA city bus hit my car in San Jose. "
                                   "My shoulder was injured."))
    gov = [d for d in b.deadlines if "government" in d["label"]]
    assert gov and gov[0]["date"] == "2027-03-03" and gov[0]["basis"] == "Cal. Gov. Code § 911.2"


def test_3_slip_and_fall_asks_for_incident_report_witnesses_and_footage():
    _, b, results = run(("photo", "Wet floor", "Photo of a wet floor in the store aisle, October 1, 2026."),
                        ("photo", "Receipt", "Store receipt dated October 1, 2026, 3:12 pm."),
                        ("note", "note", "I slipped on a wet floor at the store in Oakland and fell."))
    assert b.case_type == "premises"
    for item in ("Incident report from the property", "Witness contact information",
                 "Request to keep the security camera footage"):
        assert item in b.missing_evidence
    assert results and all("premises" in r["practice_areas"] for r in results)


def test_4_dog_bite_is_sorted_and_matched_and_owner_address_is_hidden():
    ev, b, results = run(("photo", "Injury", "Photo of dog bite wounds on my forearm, October 5, 2026."),
                         ("document", "Urgent care", "Seen October 5, 2026 for a dog bite. Diagnosis: "
                                                     "puncture wounds."),
                         ("note", "note", "My neighbor's dog bit me in Sunnyvale. The owner lives at "
                                          "214 Maple Ave."))
    assert b.case_type == "dog_bite"
    assert "Animal control or bite report" in b.missing_evidence
    assert results and all("dog_bite" in r["practice_areas"] for r in results)
    assert "214 Maple" not in safety.redact(ev[2].text, {})


def test_5_vietnamese_speaker_gets_an_english_brief_and_vietnamese_speaking_lawyers():
    _, b, results = run(("voice", "Voice memo (transcribed, originally in Vietnamese)",
                         "I was crossing the street in San Jose on October 4, 2026 when a car hit me. "
                         "I don't speak English."))
    assert b.languages == ["Vietnamese"]
    assert results and all("Vietnamese" in r["languages"] for r in results)


def test_6_should_i_sign_gets_no_advice_but_deadline_alerts_and_lawyers():
    _, b, results = run(("document", "Insurer letter",
                         "We offer $2,000 as full and final settlement of all claims from the incident "
                         "of October 1, 2026. Please sign the enclosed release and return it by "
                         "October 20, 2026."),
                        ("note", "My question", "Should I sign this?"))
    assert any("can't answer that" in w for w in b.warnings)          # honest refusal
    assert any("release" in w for w in b.warnings)                    # what the letter means
    assert "2026-10-20" in {d["date"] for d in b.deadlines}
    assert results                                                    # never left with nobody
    assert no_advice(b) and not any(safety.is_advice(w) for w in b.warnings)


def test_7_driver_being_sued_sees_only_defense_lawyers():
    _, b, results = run(("note", "note", "I rear-ended a car in Fremont on September 28, 2026 and "
                                         "now they are suing me."))
    assert b.client_side == "defense"
    assert results and all("defense" in r["sides"] for r in results)


def test_10_spanish_speaking_lawyer_is_first_for_spanish_speakers():
    for case, first in (("maria", "L1"), ("rosa", "L13")):
        b = brief.build(ingest.load_demo_case(case))
        results, _ = matching.match(b.case_type, b.client_side, b.county, b.languages)
        assert results[0]["id"] == first and "Spanish" in results[0]["languages"]
