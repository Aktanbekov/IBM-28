"""The scoreboard counts the engine's work and the evidence, never the case's value."""
import os

os.environ.setdefault("LLM_BACKEND", "rules")

import pytest  # noqa: E402

from casebridge import brief, ingest, rules, safety, scoreboard  # noqa: E402


def _built(case):
    ev = ingest.load_demo_case(case)
    b = brief.build(ev)
    red = safety.redact_brief(b, safety.find_names([e.text for e in ev]))
    return ev, b, red


@pytest.mark.parametrize("case", ["maria", "rosa", "bao"])
def test_every_fact_is_cited_and_no_advice_is_given(case):
    ev, b, red = _built(case)
    s = scoreboard.brief_stats(ev, b, red)
    assert s["facts"] > 0 and s["facts_cited"] == s["facts"]
    assert s["advice_given"] == 0
    assert s["details_hidden"] > 0
    assert 0 <= s["readiness_pct"] <= 100


def test_nothing_on_the_scoreboard_scores_the_case():
    ev, b, red = _built("maria")
    keys = " ".join(scoreboard.brief_stats(ev, b, red))
    for word in ("value", "worth", "strength", "odds", "win", "payout", "score"):
        assert word not in keys


def test_readiness_matches_the_missing_list():
    ev = ingest.load_demo_case("bao")
    covered, total = rules.readiness(ev, "auto_accident")
    assert total - covered == len(rules.missing_evidence(ev, "auto_accident"))
    assert total == 6   # the 7 auto items minus the repair estimate (Bao was on foot)


def test_trick_letter_counts_as_a_caught_hidden_instruction():
    ev = ingest.number(ingest.load_demo_case("rosa") + [ingest.load_trick_letter()])
    assert scoreboard.brief_stats(ev, brief.build(ev))["hidden_instructions"] == 1


def test_guardrail_counts_are_read_from_its_warnings():
    b = brief.build(ingest.load_demo_case("maria"))
    b.warnings += ["Removed 2 AI-generated statement(s) with no source evidence.",
                   "Blocked 3 statement(s) that read like legal advice or outcome predictions."]
    s = scoreboard.brief_stats(ingest.load_demo_case("maria"), b)
    assert (s["uncited_removed"], s["advice_blocked"]) == (2, 3)


def test_redaction_swaps_list_every_replacement_in_order():
    names = {"Rosa Martinez": "[CLIENT]"}
    swaps = scoreboard.redaction_swaps("Rosa Martinez, (510) 555-0187, rosa@mail.example.com", names)
    assert ("(510) 555-0187", "[PHONE]") in swaps
    assert ("rosa@mail.example.com", "[EMAIL]") in swaps
    assert ("Rosa Martinez", "[CLIENT]") in swaps
    # Same result as plain redaction: asking for swaps never changes the output.
    text = "Call Rosa Martinez at (510) 555-0187."
    assert safety.redact(text, names, []) == safety.redact(text, names)
