"""Red-team tests for casebridge/safety.py  (Bob session 3 — attacker perspective).

Each test plays the role of an attacker trying to get a client's identity onto the
lawyer board through redact() or redact_brief().  Tests assert the secret is NOT
present in the output.  Bob first marked the 30 tests that exposed a gap as xfail.
We then fixed safety.py for every one of them and removed the marks, so all of these
are normal tests now (see also tests/test_redteam_fixes.py).

Naming convention:  test_rt_<category>_<NN>_<short_description>
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

def _r(text: str, names: dict | None = None) -> str:
    """Shorthand: redact text with optional pre-built names dict."""
    return safety.redact(text, names or {})


def _brief(summary: str, names: dict | None = None) -> dict:
    """Build a minimal CaseBrief and run redact_brief on it."""
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", summary)
    return safety.redact_brief(b, names or {})


def _names(intro: str) -> dict[str, str]:
    """Run find_names on a single intro sentence, return the names dict."""
    return safety.find_names([intro])


# ===========================================================================
# SECTION A — Names: OCR / digit substitution
# ===========================================================================

class TestOCRNameSubstitution:
    """OCR engines frequently swap i↔1, o↔0, e↔3, a↔4, etc.
    If a scanned form comes in with 'Mar1a L0pez', 'Mar1a' is never placed in the
    names dict (digits are not in _WORD) and therefore survives redaction."""

    def test_rt_ocr_01_digit_i_in_first_name(self):
        """OCR reads 'Maria' as 'Mar1a' (digit 1 for i)."""
        names = _names("My name is Maria Lopez.")
        # The attacker submits a scanned form where the same person appears as 'Mar1a'
        out = _r("Mar1a Lopez called at 5pm.", names)
        assert "Mar1a" not in out and "Lopez" not in out, f"OCR name leaked: {out!r}"

    def test_rt_ocr_02_digit_o_in_surname(self):
        """OCR reads 'Lopez' as 'L0pez' (digit 0 for o)."""
        names = _names("My name is Maria Lopez.")
        out = _r("L0pez was involved in the incident.", names)
        assert "L0pez" not in out, f"OCR surname leaked: {out!r}"

    def test_rt_ocr_03_digit_a_in_surname(self):
        """OCR reads 'Martinez' as 'M4rtinez'."""
        names = _names("My name is Rosa Martinez.")
        out = _r("M4rtinez signed the form.", names)
        assert "M4rtinez" not in out, f"OCR surname leaked: {out!r}"

    def test_rt_ocr_04_digit_o_in_first_name(self):
        """OCR reads 'Rosa' as 'R0sa'."""
        names = _names("My name is Rosa Martinez.")
        out = _r("R0sa was seen at 3pm.", names)
        assert "R0sa" not in out, f"OCR first name leaked: {out!r}"


# ===========================================================================
# SECTION B — Names: initials, abbreviations, partial forms
# ===========================================================================

class TestInitialsAndPartialNames:
    """An initial like 'M. Lopez' or a bare surname 'Lopez' may survive if the
    honorific-triggered pattern wasn't the detection path."""

    def test_rt_initial_01_initial_dot_surname(self):
        """Medical record uses 'M. Lopez' instead of the full name.
        EXPECTED TO FAIL (xpassed): 'Lopez' IS in the names dict as a surname-part entry
        (find_names splits 'Maria Lopez' into parts), so _name_re('Lopez') with re.I catches
        'Lopez' even in 'M. Lopez'. The initial 'M.' itself is not redacted but the surname is."""
        names = _names("My name is Maria Lopez.")
        out = _r("Patient: M. Lopez, DOB 04/12/1991.", names)
        assert "Lopez" not in out, f"Surname after initial leaked: {out!r}"

    def test_rt_initial_02_initial_dot_surname_in_brief(self):
        """Insurer letter uses 'R. Martinez' — surname IS redacted because it is in names dict.
        EXPECTED TO FAIL (xpassed): same root as above; 'Martinez' part entry catches it."""
        names = _names("My name is Rosa Martinez.")
        out = _r("Dear R. Martinez, please sign the form.", names)
        assert "Martinez" not in out, f"Surname after initial leaked: {out!r}"

    def test_rt_initial_03_nickname_not_redacted(self):
        """Client uses their nickname in a voice memo."""
        names = _names("My name is Rosa Martinez.")
        out = _r("Rosie was injured on October 9.", names)
        assert "Rosie" not in out, f"Nickname leaked: {out!r}"

    def test_rt_initial_04_all_caps_name_from_form(self):
        """Government form prints the name in ALL CAPS.
        EXPECTED TO FAIL (xpassed): _name_re uses re.I for non-COMMON_WORDS names, so 'Maria'
        in the names dict matches 'MARIA', and 'Lopez' matches 'LOPEZ'."""
        names = _names("My name is Maria Lopez.")
        out = _r("MARIA LOPEZ — claimant on file.", names)
        assert "MARIA" not in out and "LOPEZ" not in out, f"All-caps name leaked: {out!r}"

    def test_rt_initial_05_bare_surname_after_ms(self):
        """'Ms. Lopez' via the honorific pattern — EXPECT PASS (Ms. is in the pattern)."""
        names = _names("My name is Maria Lopez.")
        out = _r("Ms. Lopez filed a claim.", names)
        assert "Lopez" not in out, f"Surname after Ms. leaked: {out!r}"


# ===========================================================================
# SECTION C — Names: split across newlines
# ===========================================================================

class TestNameSplitAcrossLines:
    """PDFs and OCR output sometimes split a name across a line break."""

    def test_rt_split_01_name_across_newline(self):
        """Form output places first and last name on separate lines.
        EXPECTED TO FAIL (xpassed): _name_re scans each name independently per token —
        'Maria' and 'Lopez' are each in names as part-entries with re.I, so they ARE
        caught even when separated by newlines."""
        names = _names("My name is Maria Lopez.")
        out = _r("Claimant:\nMaria\nLopez\nDOB 04/12/1991", names)
        assert "Maria" not in out and "Lopez" not in out, f"Split name leaked: {out!r}"

    def test_rt_split_02_first_and_last_on_separate_lines(self):
        """Voice memo transcript inserts a newline mid-sentence.
        EXPECTED TO FAIL (xpassed): same as split_01 — part-entries in names dict cover this."""
        names = _names("My name is Rosa Martinez and I was injured.")
        out = _r("Patient:\nRosa\nMartinez\nwas seen at urgent care.", names)
        assert "Rosa" not in out and "Martinez" not in out, f"Split name leaked: {out!r}"


# ===========================================================================
# SECTION D — Phone numbers: mixed / obfuscated formats
# ===========================================================================

class TestPhoneObfuscation:
    """Attackers embed phone numbers in ways the regex doesn't anticipate."""

    def test_rt_phone_01_mixed_word_digit_area_code(self):
        """Area code uses a mixed word-digit token to evade both patterns."""
        out = _r("Call me at four0eight 555-0142 anytime.", {})
        assert "four0eight" not in out and "555-0142" not in out, f"Mixed phone leaked: {out!r}"

    def test_rt_phone_02_fullwidth_unicode_digits(self):
        """Phone number uses Unicode full-width digit characters.
        EXPECTED TO FAIL (xpassed): '４０８-555-0142' — the ASCII portion '555-0142'
        is still caught by the 7-digit fragment pattern \\b\\d{3}[.-]\\d{4}\\b.
        The full-width area code itself is not redacted but the local number is."""
        out = _r("My number is ４０８-555-0142.", {})
        assert "555-0142" not in out, f"Local number portion leaked: {out!r}"

    def test_rt_phone_03_double_space_between_segments(self):
        """Two spaces between area code and number.
        EXPECTED TO FAIL (xpassed): the 7-digit fragment pattern \\b\\d{3}[.-]\\d{4}\\b
        still catches '555-0142' even when the area code is separated by double space."""
        out = _r("Reach me at 408  555-0142 after 6pm.", {})
        assert "555-0142" not in out, f"Double-spaced local number leaked: {out!r}"

    def test_rt_phone_04_area_code_on_separate_line(self):
        """Area code on a separate line from local number.
        EXPECTED TO FAIL (xpassed): '555-0142' on its own line is caught by the 7-digit
        fragment pattern — the area code is irrelevant for that specific sub-pattern."""
        out = _r("Phone: 408\n555-0142", {})
        assert "555-0142" not in out, f"Newline-split local number leaked: {out!r}"

    def test_rt_phone_05_standard_format_redacted(self):
        """Baseline: standard (408) 555-0142 format — EXPECT PASS."""
        out = _r("Call (408) 555-0142 now.", {})
        assert "555-0142" not in out, f"Standard phone leaked: {out!r}"

    def test_rt_phone_06_spelled_out_with_comma_separator(self):
        """Seven-digit local number spelled out with comma separator.
        EXPECTED TO FAIL (xpassed): the pattern requires ≥7 lead tokens which means
        the first 7 words must match — 'five five five, zero one four' is 7 tokens with
        a comma separator ([\\s,-]+), meeting the threshold. Redacted correctly."""
        out = _r("My number: five five five, zero one four two.", {})
        assert "five five five" not in out, f"Spelled-out phone leaked: {out!r}"


# ===========================================================================
# SECTION E — Email: obfuscated formats
# ===========================================================================

class TestEmailObfuscation:
    """Standard email pattern is `[\\w.+-]+@[\\w-]+\\.[\\w.]+`."""

    def test_rt_email_01_space_around_at_sign(self):
        """Email typed with spaces around the at-sign."""
        out = _r("Email me at rosa @ mail.example.com please.", {})
        assert "rosa" not in out or "mail.example.com" not in out, f"Spaced email leaked: {out!r}"

    def test_rt_email_02_fullwidth_at_sign(self):
        """Email uses a Unicode full-width '@' character."""
        out = _r("Contact: rosa.m＠mail.example.com", {})
        assert "rosa.m" not in out, f"Unicode-at email leaked: {out!r}"

    def test_rt_email_03_at_spelled_out(self):
        """Email uses '(at)' instead of '@'."""
        out = _r("Reach me: rosa.m(at)mail.example.com", {})
        assert "rosa.m" not in out, f"(at) email leaked: {out!r}"

    def test_rt_email_04_standard_email_redacted(self):
        """Baseline: standard email — EXPECT PASS."""
        out = _r("Email: rosa.m+claims@mail.example.com", {})
        assert "rosa.m" not in out, f"Standard email leaked: {out!r}"


# ===========================================================================
# SECTION F — Addresses: missing suffix, PO box, number-only
# ===========================================================================

class TestAddressEvasion:
    """The street address regex requires a street-type suffix word (St, Ave, etc.)."""

    def test_rt_addr_01_no_street_suffix(self):
        """Address written without a street suffix word."""
        out = _r("I live at 4120 Peralta, Fremont, CA.", {})
        assert "4120 Peralta" not in out, f"No-suffix address leaked: {out!r}"

    def test_rt_addr_02_po_box(self):
        """Client receives mail at a PO Box."""
        out = _r("Send documents to P.O. Box 1234, San Jose, CA 95101.", {})
        assert "1234" not in out or "Box" not in out, f"PO Box leaked: {out!r}"

    def test_rt_addr_03_number_only_no_street_name(self):
        """Only the house number is present, no street name."""
        out = _r("I live at 4120, apartment 12, Fremont.", {})
        # 4120 alone should not match (no street name follows); Apartment 12 should be caught.
        assert "4120" not in out, f"Bare house number leaked: {out!r}"

    def test_rt_addr_04_full_address_redacted(self):
        """Baseline: full address with suffix — EXPECT PASS."""
        out = _r("I live at 4120 Peralta Ave, Apt 12, Fremont, CA 94536.", {})
        assert "4120 Peralta" not in out, f"Full address leaked: {out!r}"

    def test_rt_addr_05_boulevard_with_trailing_period(self):
        """Street suffix 'Blvd.' — PASSES: the regex handles trailing period and redacts correctly."""
        out = _r("Accident on 3200 Stevens Creek Blvd. near Target.", {})
        assert "3200 Stevens Creek" not in out, f"Blvd. address leaked: {out!r}"

    def test_rt_addr_06_dr_suffix_ambiguous_with_honorific(self):
        """Street suffix 'Dr' — PASSES: the regex includes 'Dr' as a suffix keyword."""
        out = _r("I live at 77 Oak Dr, San Jose.", {})
        assert "77 Oak" not in out, f"Address with 'Dr' suffix leaked: {out!r}"

    def test_rt_addr_07_compass_direction_with_period(self):
        """Address 'W. Hedding St.' — PASSES: [NSEW]\\.? handles 'W.' with period."""
        out = _r("She lived at 1500 W. Hedding St., San Jose.", {})
        assert "1500" not in out, f"Compass-dot address leaked: {out!r}"


# ===========================================================================
# SECTION G — Date of birth: formats outside the _DATE pattern
# ===========================================================================

class TestDOBFormats:
    """_DATE handles MM/DD/YYYY, YYYY-MM-DD, and long-form 'Month DD, YYYY'.
    European (DD.MM.YYYY) and year-only mentions are not covered."""

    def test_rt_dob_01_european_dot_format(self):
        """DOB in European format: 08.03.1984."""
        out = _r("Date of birth: 08.03.1984", {})
        assert "1984" not in out, f"European DOB leaked: {out!r}"

    def test_rt_dob_02_year_only(self):
        """Only the year is mentioned (e.g. in an employment record)."""
        out = _r("Employee born in 1984, hired 2010.", {})
        assert "1984" not in out, f"Year-only DOB leaked: {out!r}"

    def test_rt_dob_03_month_year_no_day(self):
        """DOB listed as month and year only."""
        out = _r("DOB: March 1984", {})
        assert "1984" not in out, f"Month+year DOB leaked: {out!r}"

    def test_rt_dob_04_spanish_nacida_en(self):
        """Spanish DOB phrasing with 'nacida en' (not 'nacida el')."""
        out = _r("nacida en 08/03/1984 en Guadalajara.", {})
        assert "1984" not in out, f"Spanish nacida-en DOB leaked: {out!r}"

    def test_rt_dob_05_standard_us_format(self):
        """Baseline: standard MM/DD/YYYY with keyword — EXPECT PASS."""
        out = _r("Date of birth: 03/08/1984", {})
        assert "1984" not in out, f"Standard DOB leaked: {out!r}"

    def test_rt_dob_06_dob_with_trailing_period(self):
        """'d.o.b.:' typed with an extra period at the end."""
        out = _r("d.o.b.: 03/08/1984", {})
        assert "1984" not in out, f"d.o.b.: DOB leaked: {out!r}"


# ===========================================================================
# SECTION H — Plate, VIN, ID numbers: case and format variations
# ===========================================================================

class TestIDFormatVariations:
    """Regex patterns for plates and VINs use uppercase character classes."""

    def test_rt_id_01_lowercase_plate(self):
        """Plate number written in lowercase."""
        out = _r("Plate number: 7xyz456.", {})
        assert "7xyz456" not in out, f"Lowercase plate leaked: {out!r}"

    def test_rt_id_02_lowercase_vin(self):
        """VIN number in lowercase (as sometimes appears in OCR output)."""
        out = _r("VIN: 1hgcm82633a004352", {})
        assert "1hgcm82633a004352" not in out, f"Lowercase VIN leaked: {out!r}"

    def test_rt_id_03_lowercase_policy_number(self):
        """Policy/claim number value begins with a lowercase letter."""
        out = _r("Policy number: ca-9981234.", {})
        assert "ca-9981234" not in out or "9981234" not in out, f"Lowercase policy# leaked: {out!r}"

    def test_rt_id_04_lowercase_report_number(self):
        """Police report number in lowercase (copy-paste from a web portal)."""
        out = _r("Report number: sj-26-118842.", {})
        assert "sj-26-118842" not in out, f"Lowercase report# leaked: {out!r}"

    def test_rt_id_05_uppercase_plate_redacted(self):
        """Baseline: uppercase California plate — EXPECT PASS."""
        out = _r("Plate: 7XYZ456.", {})
        assert "7XYZ456" not in out, f"Uppercase plate leaked: {out!r}"

    def test_rt_id_06_mixedcase_plate(self):
        """Plate number with mixed case."""
        out = _r("Her license plate: 7Abc234 was in the photo.", {})
        assert "7Abc234" not in out, f"Mixed-case plate leaked: {out!r}"

    def test_rt_id_07_lowercase_incident_number(self):
        """Incident/case number from a store system in lowercase."""
        out = _r("Incident number: hc-55190 filed by staff.", {})
        assert "hc-55190" not in out, f"Lowercase incident# leaked: {out!r}"


# ===========================================================================
# SECTION I — SSN and other numeric identifiers
# ===========================================================================

class TestSSNVariations:
    """SSN pattern is \\b\\d{3}-\\d{2}-\\d{4}\\b."""

    def test_rt_ssn_01_spaces_instead_of_dashes(self):
        """SSN written with spaces as separators."""
        out = _r("SSN: 123 45 6789", {})
        assert "123 45 6789" not in out, f"Space-separated SSN leaked: {out!r}"

    def test_rt_ssn_02_dots_instead_of_dashes(self):
        """SSN written with dots as separators."""
        out = _r("Social Security: 123.45.6789", {})
        assert "123.45.6789" not in out, f"Dot-separated SSN leaked: {out!r}"

    def test_rt_ssn_03_no_separators(self):
        """SSN written as a plain 9-digit number."""
        out = _r("Social Security Number: 123456789", {})
        assert "123456789" not in out, f"No-separator SSN leaked: {out!r}"


# ===========================================================================
# SECTION J — GPS / location coordinates
# ===========================================================================

class TestGPSFormats:
    """The GPS pattern matches '-?\\b\\d{1,3}\\.\\d{3,},\\s*-?\\d{1,3}\\.\\d{3,}\\b'."""

    def test_rt_gps_01_semicolon_separator(self):
        """GPS coordinates separated by a semicolon instead of a comma."""
        out = _r("Location: 37.3230; -121.9480", {})
        assert "37.3230" not in out, f"Semicolon-GPS leaked: {out!r}"

    def test_rt_gps_02_dms_format(self):
        """GPS in degrees-minutes-seconds format."""
        out = _r("GPS: 37°19′22″N 121°57′17″W", {})
        assert "37°19" not in out, f"DMS GPS leaked: {out!r}"

    def test_rt_gps_03_decimal_degrees_comma(self):
        """Baseline: standard decimal GPS with comma — EXPECT PASS."""
        out = _r("Location: 37.3230, -121.9480", {})
        assert "37.3230" not in out, f"Decimal GPS leaked: {out!r}"


# ===========================================================================
# SECTION K — redact_brief: names in the summary field
# ===========================================================================

class TestRedactBriefSummary:
    """redact_brief redacts all free-text fields; the summary uses find_leaks as a backstop."""

    def test_rt_brief_01_initial_surname_in_summary(self):
        """Brief summary with 'M. Lopez' — surname IS redacted via part-entry in names dict."""
        names = _names("My name is Maria Lopez.")
        b = _brief("M. Lopez was rear-ended on Stevens Creek Blvd.", names)
        assert "Lopez" not in b["summary"], \
            f"Surname in summary after initial: {b['summary']!r}"

    def test_rt_brief_02_allcaps_name_in_summary(self):
        """Summary has 'MARIA LOPEZ' all-caps — caught via re.I in _name_re on part entries."""
        names = _names("My name is Maria Lopez.")
        b = _brief("MARIA LOPEZ filed a personal-injury claim.", names)
        assert "MARIA" not in b["summary"] and "LOPEZ" not in b["summary"], \
            f"All-caps name in summary: {b['summary']!r}"

    def test_rt_brief_03_phone_in_summary_redacted(self):
        """Summary contains a phone number — EXPECT PASS via PII_PATTERNS."""
        b = _brief("Client can be reached at (408) 555-0142.", {})
        assert "555-0142" not in b["summary"], f"Phone in summary leaked: {b['summary']!r}"

    def test_rt_brief_04_ocr_name_in_summary(self):
        """Summary contains an OCR-corrupted name."""
        names = _names("My name is Maria Lopez.")
        b = _brief("Mar1a L0pez was injured in a rear-end collision.", names)
        assert "Mar1a" not in b["summary"] and "L0pez" not in b["summary"], \
            f"OCR name in summary: {b['summary']!r}"

    def test_rt_brief_05_nickname_in_summary(self):
        """Summary uses a nickname not present in find_names output."""
        names = _names("My name is Rosa Martinez.")
        b = _brief("Rosie Martinez slipped on a wet floor.", names)
        assert "Rosie" not in b["summary"], f"Nickname in summary: {b['summary']!r}"
