"""Bob session 3 – adversarial edge-case tests for casebridge/safety.py.

Each test is annotated with EXPECT_PASS or EXPECT_FAIL to document whether the
current implementation handles the case correctly.  Tests that are expected to
fail use pytest.mark.xfail so `pytest -q` stays green; the failure message tells
us exactly what needs to be fixed in the source.
"""
from __future__ import annotations

import os
os.environ["LLM_BACKEND"] = "rules"

import pytest  # noqa: E402
from casebridge import safety  # noqa: E402
from casebridge.models import CaseBrief, Fact  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _brief_with_summary(summary: str) -> CaseBrief:
    return CaseBrief("auto_accident", "plaintiff", "Santa Clara", summary)


# ===========================================================================
# 1.  find_names / redact – names with hyphens and apostrophes
# ===========================================================================

class TestHyphenatedAndApostropheNames:
    """Names like Smith-Jones and O'Brien appear in police and medical records."""

    @pytest.mark.xfail(
        reason="_WORD regex requires all-lowercase after first char; 'Smith-Jones' has "
               "an uppercase J mid-token so it matches only 'Smith', not 'Smith-Jones'."
    )
    def test_hyphenated_name_detected_by_find_names(self):
        """'Smith-Jones' should be captured as a single name token."""
        texts = ["My name is Smith-Jones."]
        names = safety.find_names(texts)
        assert any("Smith-Jones" in k for k in names), \
            f"find_names did not detect 'Smith-Jones'; got: {names}"

    @pytest.mark.xfail(
        reason="_WORD stops at 'O' because the apostrophe is in the char class but "
               "'B' (uppercase) terminates the match; O'Brien is split into 'O' (too short) "
               "and 'Brien'."
    )
    def test_apostrophe_name_detected_by_find_names(self):
        """'O'Brien' should be captured as a single name token."""
        texts = ["My name is O'Brien."]
        names = safety.find_names(texts)
        assert any("O'Brien" in k for k in names), \
            f"find_names did not detect \"O'Brien\"; got: {names}"

    @pytest.mark.xfail(
        reason="Even after find_names misses the full hyphenated name, redact() gets "
               "no entry for 'Smith-Jones', so the raw string survives redaction."
    )
    def test_hyphenated_name_redacted(self):
        """After detection the full hyphenated name must be replaced in free text."""
        texts = ["Vehicle 1: driver Smith-Jones hit the median."]
        names = safety.find_names(texts)
        out = safety.redact("Smith-Jones filed the claim.", names)
        assert "Smith-Jones" not in out, f"Name survived redaction: {out!r}"

    @pytest.mark.xfail(
        reason="Same root cause as test_apostrophe_name_detected_by_find_names."
    )
    def test_apostrophe_name_redacted(self):
        """O'Brien detected via role pattern must be removed from later free text."""
        texts = ["My name is O'Brien."]
        names = safety.find_names(texts)
        out = safety.redact("O'Brien said the light was green.", names)
        assert "O'Brien" not in out, f"Name survived redaction: {out!r}"


# ===========================================================================
# 2.  find_names / redact – names in all-lowercase
# ===========================================================================

class TestLowercaseNames:
    """Transcripts from speech-to-text sometimes produce all-lowercase output."""

    @pytest.mark.xfail(
        reason="_WORD requires an uppercase first letter ([A-ZÀ-ÖØ-Þ]), so an "
               "all-lowercase name like 'rosa martinez' is never matched by any role pattern."
    )
    def test_lowercase_client_name_detected(self):
        """'my name is rosa martinez' should still produce a names entry for the client."""
        texts = ["my name is rosa martinez."]
        names = safety.find_names(texts)
        assert names, f"find_names returned empty for all-lowercase input; got: {names}"

    @pytest.mark.xfail(
        reason="Because the lowercase name is never put in the names dict, it is never "
               "substituted by redact(), so it leaks through to the lawyer view."
    )
    def test_lowercase_name_redacted(self):
        """Even when transcribed in lowercase, the name must not reach the lawyer view."""
        texts = ["my name is rosa martinez."]
        names = safety.find_names(texts)
        out = safety.redact("rosa martinez was injured.", names)
        assert "rosa" not in out.lower() and "martinez" not in out.lower(), \
            f"Lowercase name survived redaction: {out!r}"


# ===========================================================================
# 3.  redact – phone numbers split across words / unusual formatting
# ===========================================================================

class TestSplitPhoneNumbers:
    """Attackers (or OCR artefacts) may insert spaces or dashes inside phone numbers."""

    # EXPECT_PASS – standard patterns already covered by PII_PATTERNS
    def test_phone_with_dots_redacted(self):
        assert "555.0142" not in safety.redact("call 555.0142 now", {})

    def test_phone_with_parens_redacted(self):
        assert "408" not in safety.redact("(408) 555-0142", {})

    @pytest.mark.xfail(
        reason="The regex requires digits to be contiguous or separated by a single "
               r"[\s.-] character; extra spaces like '555 - 0142' break the match."
    )
    def test_phone_split_with_spaces_and_dash(self):
        """'555 - 0142' (spaces around dash) should be caught as a phone fragment."""
        out = safety.redact("Call me at 555 - 0142 tonight.", {})
        assert "555" not in out or "0142" not in out, \
            f"Split phone number survived: {out!r}"

    @pytest.mark.xfail(
        reason="'Five five five zero one four two' is purely alphabetic so no numeric "
               "pattern fires; this is an inherent limitation of pattern-based redaction."
    )
    def test_phone_spelled_out_not_redacted(self):
        """Spelled-out phone numbers are NOT expected to be caught – document the gap."""
        out = safety.redact("My number is five five five zero one four two.", {})
        # We expect this to FAIL (number survives), documenting the known gap.
        assert "[PHONE]" in out, "Spelled-out phone not caught (known limitation)"

    def test_phone_address_hash(self):
        """Address with '#' for unit: '77 Oak Street, #3B' must be redacted."""
        # The current Apt/Unit pattern covers '#', but the street address pattern
        # does not include a leading '#' variant — this test checks the Apt pattern.
        out = safety.redact("I live at 77 Oak Street, #3B.", {})
        assert "77 Oak" not in out, f"Street number survived: {out!r}"


# ===========================================================================
# 4.  redact – addresses with '#' in the unit portion
# ===========================================================================

class TestAddressHash:
    """Addresses written as '123 Main St #4' (no Apt/Unit keyword)."""

    # EXPECT_PASS via the house-number + street-name pattern
    def test_street_address_with_hash_unit_redacted(self):
        """'4120 Peralta Ave, #12' – street part should be redacted."""
        out = safety.redact("I live at 4120 Peralta Ave, #12, Fremont.", {})
        assert "4120 Peralta" not in out, f"Address survived: {out!r}"

    @pytest.mark.xfail(
        reason="The street-address regex requires the unit part to start with an "
               "Apt/Apartment/Unit/Suite/Ste keyword; bare '#12' after the street "
               "name is not in the optional suffix group."
    )
    def test_bare_hash_unit_after_street_redacted(self):
        """'4120 Peralta Ave #12' (no comma, no keyword) should fully be redacted."""
        out = safety.redact("She lives at 4120 Peralta Ave #12 Fremont.", {})
        # Both the street number and the '#12' unit should disappear.
        assert "4120" not in out and "#12" not in out, f"Survived: {out!r}"


# ===========================================================================
# 5.  is_advice – Spanish-language advice phrasing
# ===========================================================================

class TestSpanishAdvicePhrasing:
    """Advice patterns currently cover English only."""

    @pytest.mark.xfail(
        reason="ADVICE_PATTERNS has no Spanish equivalents; 'usted debería firmar' "
               "(you should sign) is not matched."
    )
    def test_usted_deberia_firmar_blocked(self):
        assert safety.is_advice("Usted debería firmar el acuerdo."), \
            "Spanish 'should sign' phrasing not detected as advice"

    @pytest.mark.xfail(
        reason="ADVICE_PATTERNS has no Spanish equivalents; 'su caso vale' "
               "(your case is worth) is not matched."
    )
    def test_su_caso_vale_blocked(self):
        assert safety.is_advice("Su caso vale más de $50,000."), \
            "Spanish 'case is worth' phrasing not detected as advice"

    @pytest.mark.xfail(
        reason="'debería aceptar' (should accept) follows the same gap."
    )
    def test_deberia_aceptar_blocked(self):
        assert safety.is_advice("Creo que debería aceptar la oferta."), \
            "'debería aceptar' (should accept) not detected as advice"

    @pytest.mark.xfail(
        reason="'ganará el caso' (will win the case) is not in ADVICE_PATTERNS."
    )
    def test_ganara_el_caso_blocked(self):
        assert safety.is_advice("Con esta evidencia usted ganará el caso."), \
            "Spanish 'will win' phrasing not detected as advice"


# ===========================================================================
# 6.  is_advice – advice disguised as questions
# ===========================================================================

class TestAdviceDisguisedAsQuestions:
    """Rhetorical questions that amount to advice ('Shouldn't you settle?')."""

    @pytest.mark.xfail(
        reason="ADVICE_PATTERNS use \\b(you should)\\b which requires the exact order; "
               "inversion 'shouldn't you settle?' reorders the tokens and the regex misses it."
    )
    def test_inverted_you_should_settle(self):
        assert safety.is_advice("Shouldn't you settle for the offer on the table?"), \
            "Inverted 'you should settle' question not detected as advice"

    @pytest.mark.xfail(
        reason="'Don't you think you will win?' rephrases the outcome prediction as a "
               "question; ADVICE_PATTERNS need 'you will win' literally."
    )
    def test_question_form_will_win(self):
        assert safety.is_advice("Don't you think you will win this case?"), \
            "Question-form outcome prediction not blocked"

    # EXPECT_PASS – 'you will win' literal phrase is in ADVICE_PATTERNS
    def test_direct_you_will_win_blocked(self):
        assert safety.is_advice("You will win this case.")

    # EXPECT_PASS – 'you should sign' literal phrase is in ADVICE_PATTERNS
    def test_direct_you_should_sign_blocked(self):
        assert safety.is_advice("You should sign the release.")


# ===========================================================================
# 7.  is_advice – false positives that must NOT be blocked
# ===========================================================================

class TestAdviceFalsePositives:
    """These are facts reported by the client, not advice generated by the app."""

    # EXPECT_PASS – 'I should sign' does not match '\byou should\b'
    def test_insurer_said_i_should_sign_is_not_advice(self):
        """'the insurer said I should sign' is a fact about what was said, not our advice."""
        assert not safety.is_advice("The insurer said I should sign the release."), \
            "False positive: quoting the insurer's words blocked as app-generated advice"

    # EXPECT_PASS – 'you should contact a lawyer' is not in the action list
    def test_refer_to_lawyer_is_not_blocked(self):
        """A referral sentence should not be mistaken for case-outcome advice."""
        assert not safety.is_advice("You should contact a lawyer before you respond."), \
            "Referral to a lawyer incorrectly flagged as outcome advice"

    # EXPECT_PASS – 'strong evidence' ≠ 'strong case'
    def test_strong_evidence_is_not_blocked(self):
        assert not safety.is_advice("The police report is strong evidence of liability.")

    # EXPECT_PASS – a monetary settlement figure that is a fact, not a prediction
    def test_insurer_offered_amount_is_not_blocked(self):
        """Stating what the insurer offered is factual, not a case-value prediction."""
        assert not safety.is_advice("The insurer offered $3,500 to settle the claim.")

    @pytest.mark.xfail(
        reason="The pattern r'\\b(your |the )?case is worth\\b' is case-insensitive and "
               "matches 'your case is worth'; a news quote like 'reporter said the case is "
               "worth following' would also match, but the primary concern here is the phrase "
               "'the case is worth $X' which correctly fires — this test documents a subtle "
               "false-positive edge: 'this case is worth fighting for' is not a valuation."
    )
    def test_case_worth_fighting_for_is_not_blocked(self):
        """'worth fighting for' is not a monetary valuation; it should not be blocked."""
        assert not safety.is_advice("My attorney says this case is worth fighting for."), \
            "False positive: 'worth fighting for' incorrectly flagged as case valuation"

    # EXPECT_PASS – 'settle for $' needs the literal phrase; '$1,200 settlement' is a fact
    def test_settlement_amount_in_timeline_is_not_blocked(self):
        assert not safety.is_advice("Insurer offered a $1,200 settlement on Oct 5 [E5].")


# ===========================================================================
# 8.  redact_brief / find_leaks – names with hyphens and apostrophes in briefs
# ===========================================================================

class TestBriefRedactionEdgeCases:
    """Ensure redact_brief and find_leaks handle special-character names."""

    @pytest.mark.xfail(
        reason="find_names does not extract 'O'Brien' as a single token (see section 1), "
               "so it never enters the names dict passed to redact_brief, and find_leaks "
               "reports it as a leak only if it was in the names dict to begin with."
    )
    def test_apostrophe_name_does_not_leak_in_brief(self):
        names = {"O'Brien": "[OTHER PARTY]"}
        b = _brief_with_summary("The driver O'Brien ran the red light.")
        red = safety.redact_brief(b, names)
        assert "O'Brien" not in str(red), f"Name leaked into brief: {red}"

    def test_hyphenated_name_manually_provided_is_redacted(self):
        """When the caller manually adds 'Smith-Jones' to the names dict, it IS redacted."""
        names = {"Smith-Jones": "[OTHER PARTY]"}
        b = _brief_with_summary("Smith-Jones was the at-fault driver.")
        red = safety.redact_brief(b, names)
        assert "Smith-Jones" not in str(red), \
            f"Manually supplied hyphenated name leaked: {red}"

    def test_find_leaks_catches_apostrophe_name(self):
        """find_leaks must flag a name that survived redaction."""
        names = {"O'Brien": "[OTHER PARTY]"}
        # Simulate a brief where redaction failed.
        data = {"summary": "O'Brien ran the light."}
        leaks = safety.find_leaks(data, names)
        assert "O'Brien" in leaks, \
            f"find_leaks did not report unredacted 'O'Brien'; leaks: {leaks}"
