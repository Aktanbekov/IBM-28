"""The "trick letter" demo: an insurer letter with AI instructions hidden in an HTML comment."""
import os

os.environ.setdefault("LLM_BACKEND", "rules")

import pytest  # noqa: E402

from casebridge import brief, ingest, safety  # noqa: E402


@pytest.mark.parametrize("case", ["maria", "rosa", "bao"])
def test_trick_letter_is_flagged_in_every_demo_case(case):
    ev = ingest.number(ingest.load_demo_case(case) + [ingest.load_trick_letter()])
    trick = ev[-1].id
    assert safety.injection_flags(ev) == [trick]
    b = brief.build(ev)
    assert any(w.startswith(f"[{trick}] contains text that tries to give instructions to an AI")
               for w in b.warnings)


def test_trick_letters_hidden_advice_never_reaches_the_brief():
    ev = ingest.number(ingest.load_demo_case("maria") + [ingest.load_trick_letter()])
    b = brief.build(ev)
    facts = [f.text for sec in (b.timeline, b.parties, b.injuries, b.damages) for f in sec]
    assert not any("worth nothing" in t or "sign the release today" in t for t in facts)
    assert not any(safety.is_advice(t) for t in facts + [b.summary])


def test_trick_letter_has_no_personal_details():
    letter = ingest.load_trick_letter()
    assert safety.find_names([letter.text]) == {}
    assert safety.find_leaks(letter.text, {}) == []
