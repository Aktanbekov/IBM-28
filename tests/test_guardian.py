"""Tests for the Granite Guardian integration.

All tests mock llm.guardian_check so no real API calls are made.
LLM_BACKEND is forced to "rules" to prevent any watsonx/Ollama calls from
build(); _apply_guardian is exercised directly.
"""
import os
import unittest.mock as mock

os.environ["LLM_BACKEND"] = "rules"
os.environ.setdefault("WATSONX_PROJECT_ID", "test-project")
os.environ.setdefault("WATSONX_APIKEY", "test-key")

from casebridge import brief as brief_mod  # noqa: E402
from casebridge.models import CaseBrief, Evidence, Fact  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_brief(*facts: Fact, summary: str = "A rear-end collision occurred.") -> CaseBrief:
    b = CaseBrief(
        case_type="auto_accident",
        client_side="plaintiff",
        county="Santa Clara",
        summary=summary,
        engine="watsonx",
    )
    b.timeline = list(facts)
    return b


def _make_evidence(*texts: str) -> list[Evidence]:
    return [Evidence(id=f"E{i+1}", kind="note", title=f"Note {i+1}", text=t)
            for i, t in enumerate(texts)]


# ---------------------------------------------------------------------------
# Test 1 — groundedness failure flags the fact
# ---------------------------------------------------------------------------

class TestGroundednessFailure:
    """When Guardian returns True for a fact's groundedness check, the fact is flagged."""

    def test_fact_gets_not_grounded_flag(self):
        fact_text = "The car was travelling at 90 mph."
        fact = Fact(text=fact_text, sources=["E1"])
        b = _make_brief(fact, summary="Minor collision with no injuries.")
        ev = _make_evidence("A low-speed rear-end collision occurred.")

        # Route by user_text: only the fact groundedness call should be flagged.
        def _routed(user_text, risk, ev_text, token):
            return user_text == fact_text  # True only for this fact

        with mock.patch("casebridge.llm.guardian_check", side_effect=_routed), \
             mock.patch("casebridge.brief._fetch_token", return_value="tok"):
            brief_mod._apply_guardian(b, ev)

        assert any("Not grounded" in f for f in fact.guardian_flags), fact.guardian_flags
        assert "E1" in fact.guardian_flags[0]

    def test_warning_count_added_to_brief(self):
        fact_text = "Injuries were severe."
        fact = Fact(text=fact_text, sources=["E1"])
        b = _make_brief(fact)
        ev = _make_evidence("The driver had a minor bruise.")

        def _routed(user_text, risk, ev_text, token):
            return user_text == fact_text

        with mock.patch("casebridge.llm.guardian_check", side_effect=_routed), \
             mock.patch("casebridge.brief._fetch_token", return_value="tok"):
            brief_mod._apply_guardian(b, ev)

        assert any("flagged 1 statement" in w for w in b.warnings), b.warnings


# ---------------------------------------------------------------------------
# Test 2 — legal advice is never sent to Guardian (the rules guardrail owns it)
# ---------------------------------------------------------------------------

class TestAdviceStaysWithRules:
    """Guardian 2B flagged quoted insurer letters as advice, so only groundedness is asked."""

    def test_only_groundedness_is_checked(self):
        b = _make_brief(Fact(text="The insurer offered $1,200.", sources=["E1"]))
        ev = _make_evidence("We are prepared to offer $1,200 as full settlement.")
        with mock.patch("casebridge.llm.guardian_check", return_value=False) as check, \
             mock.patch("casebridge.brief._fetch_token", return_value="tok"):
            brief_mod._apply_guardian(b, ev)
        assert {c.args[1] for c in check.call_args_list} == {brief_mod.GROUNDEDNESS_RISK}
        assert all(c.args[2] for c in check.call_args_list)   # always against evidence


# ---------------------------------------------------------------------------
# Test 3 — all checks pass: no flags, no Guardian warning
# ---------------------------------------------------------------------------

class TestAllChecksSafe:
    """When Guardian returns False for every call, no flags are written."""

    def test_no_flags_no_warning(self):
        fact = Fact(text="The collision happened at 5:40 pm.", sources=["E1"])
        b = _make_brief(fact, summary="A rear-end collision at 5:40 pm.")
        ev = _make_evidence("Rear-end collision at 5:40 pm on October 2.")

        # All calls → False (safe)
        with mock.patch("casebridge.llm.guardian_check", return_value=False), \
             mock.patch("casebridge.brief._fetch_token", return_value="tok"):
            brief_mod._apply_guardian(b, ev)

        assert fact.guardian_flags == []
        assert b.summary_guardian_flags == []
        assert not any("flagged" in w for w in b.warnings)


# ---------------------------------------------------------------------------
# Test 4 — Guardian unavailable (returns None): fact marked "Not checked"
# ---------------------------------------------------------------------------

class TestGuardianUnavailable:
    """When guardian_check returns None for every call (network error etc.), the brief says so
    once, calmly, and no fact is flagged or deleted."""

    def test_fact_marked_not_checked(self):
        fact = Fact(text="Vehicle was a red sedan.", sources=["E1"])
        b = _make_brief(fact)
        ev = _make_evidence("A red sedan rear-ended the plaintiff.")

        with mock.patch("casebridge.llm.guardian_check", return_value=None), \
             mock.patch("casebridge.brief._fetch_token", return_value="tok"):
            brief_mod._apply_guardian(b, ev)

        assert fact.guardian_flags == []
        assert any("could not run" in w for w in b.warnings), b.warnings
        # Fact must NOT have been deleted
        assert b.timeline[0] is fact


# ---------------------------------------------------------------------------
# Test 5 — summary groundedness failure populates summary_guardian_flags
# ---------------------------------------------------------------------------

class TestSummaryGroundedness:
    """When the summary fails the groundedness check, summary_guardian_flags is set."""

    def test_summary_gets_flag(self):
        fact = Fact(text="The collision happened on October 2.", sources=["E1"])
        summary_text = "The client suffered life-changing injuries."
        b = _make_brief(fact, summary=summary_text)
        ev = _make_evidence("Collision on October 2. Minor whiplash.")

        # Route by user_text so the call order doesn't matter (ThreadPoolExecutor
        # delivers futures via as_completed in an arbitrary order).
        def _routed(user_text, risk, ev_text, token):
            if user_text == summary_text:
                return True   # summary groundedness → flagged
            return False      # fact groundedness and advice → safe

        with mock.patch("casebridge.llm.guardian_check", side_effect=_routed), \
             mock.patch("casebridge.brief._fetch_token", return_value="tok"):
            brief_mod._apply_guardian(b, ev)

        assert any("Summary not grounded" in fl for fl in b.summary_guardian_flags), \
            b.summary_guardian_flags
        assert fact.guardian_flags == []
