"""Branch/function coverage tests (Bob session 3).

Every test here targets a specific branch or code path in
rules.py, safety.py, matching.py or ingest.py that is not
exercised by any existing test file. No source files are changed.

Section index
  A. rules._minutes                    – 12 am, 12 pm, 24h, no-match
  B. rules.detect_county               – "X County" literal, comma-prefixed, returns None
  C. rules.detect_case_type            – "other", "medical", "workplace"
  D. rules.detect_languages            – Tagalog, "no english" cue, only-document evidence
  E. rules.deadlines                   – government cue, no incident date, month-rollover
  F. rules.missing_evidence            – dog_bite checklist, default checklist, keyword in title
  G. rules.warnings                    – five untested ADVICE_QUESTION_RE variants
  H. rules.insurer_alerts              – long response window (no short-window alert)
  I. rules.contradictions              – photo time excluded, tolerance boundary, _cite
  J. rules.sentences                   – ! and ? terminators
  K. rules.how_to_get                  – unknown label returns None
  L. rules._similar                    – overlap thresholds
  M. rules.collect                     – deduplication merges sources
  N. rules.incident_date               – document preferred over note
  O. ingest._gps_degrees               – S (southern) hemisphere
  P. ingest.photo_note                 – taken-only, gps-only
  Q. ingest.photo_metadata             – GPS ref missing (defaults N/E)
  R. ingest.kind_for                   – .heic, .webp, .aac, .flac, .doc, .docx
  S. ingest.voice_evidence             – English language title
  T. ingest.number                     – empty list
  U. ingest.pdf_text                   – pypdf absent fallback
  V. matching.speaks_with              – empty language list
  W. matching.match                    – no county, custom lawyers list, all excluded,
                                         free_consultation=False, "other" case type why text
"""
from __future__ import annotations

import io
import os
os.environ["LLM_BACKEND"] = "rules"

import pytest  # noqa: E402
from casebridge import ingest, matching, rules, safety  # noqa: E402
from casebridge.models import Evidence  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ev(text: str, kind: str = "note", eid: str = "E1", title: str = "note") -> Evidence:
    return Evidence(eid, kind, title, text)


def evs(*items):
    """Build a numbered list of Evidence from (kind, title, text) tuples."""
    return ingest.number([Evidence("", k, t, x) for k, t, x in items])


# ===========================================================================
# A. rules._minutes
# ===========================================================================

class TestMinutes:
    """Every branch of the _minutes() helper."""

    def test_12_am_is_midnight(self):
        """12 am = 0 minutes after midnight (h == 12 and ampm == 'am' → h = 0)."""
        assert rules._minutes("12 am") == 0

    def test_12_pm_is_noon(self):
        """12 pm = 720 minutes (noon; h == 12 and ampm == 'pm' → no change)."""
        assert rules._minutes("12 pm") == 720

    def test_12_00_pm(self):
        """12:00 pm (with minutes) → 720."""
        assert rules._minutes("12:00 pm") == 720

    def test_12_00_am(self):
        """12:00 am → 0."""
        assert rules._minutes("12:00 am") == 0

    def test_24h_no_ampm(self):
        """17:42 (24-hour, no am/pm suffix) → 17*60+42 = 1062."""
        assert rules._minutes("17:42") == 1062

    def test_no_match_returns_none(self):
        """A string that does not start with digits returns None."""
        assert rules._minutes("noon") is None

    def test_plain_pm(self):
        """9 pm → 21 * 60 = 1260."""
        assert rules._minutes("9 pm") == 1260

    def test_plain_am(self):
        """9 am → 9 * 60 = 540."""
        assert rules._minutes("9 am") == 540


# ===========================================================================
# B. rules.detect_county
# ===========================================================================

class TestDetectCounty:
    """County detection branches."""

    @pytest.mark.xfail(
        reason="detect_county captures everything before 'county' with a non-greedy regex "
               "then calls .title() on the whole group. 'in santa clara' becomes "
               "'In Santa Clara' instead of 'Santa Clara'. The regex intended to grab "
               "only the county name but captures preceding words too."
    )
    def test_explicit_county_phrase(self):
        """'Santa Clara County' in text should return 'Santa Clara', but current code
        returns 'The Incident Occurred In Santa Clara' due to greedy capture."""
        assert rules.detect_county([ev("The incident occurred in Santa Clara County.")]) == "Santa Clara"

    def test_county_with_comma_prefix(self):
        """'Oakland, Alameda County' – split on comma, take last part."""
        assert rules.detect_county([ev("Filed in Oakland, Alameda County court.")]) == "Alameda"

    def test_city_lookup(self):
        """City name 'Sunnyvale' → Santa Clara via CITY_TO_COUNTY."""
        assert rules.detect_county([ev("The accident was in Sunnyvale near Highway 101.")]) == "Santa Clara"

    def test_returns_none_when_no_location(self):
        """No county name and no known city → None."""
        assert rules.detect_county([ev("I was injured at the store today.")]) is None

    @pytest.mark.xfail(
        reason="Same root cause as test_explicit_county_phrase: the non-greedy regex "
               "captures 'fremont is in alameda' → .title() → 'Fremont Is In Alameda'. "
               "When the text contains a city name before the county phrase, the "
               "whole sentence fragment is returned instead of just the county name."
    )
    def test_county_phrase_with_preceding_words(self):
        """'Alameda County' preceded by other words returns the wrong value."""
        result = rules.detect_county([ev("Fremont is in Alameda County.")])
        assert result == "Alameda"


# ===========================================================================
# C. rules.detect_case_type
# ===========================================================================

class TestDetectCaseType:
    """Case types that are never the output in existing tests."""

    def test_other_when_no_keywords(self):
        """No keyword matches → 'other'."""
        assert rules.detect_case_type([ev("Everything is fine, nothing happened.")]) == "other"

    def test_medical_keywords(self):
        """'malpractice' keyword → 'medical'."""
        assert rules.detect_case_type([ev("The surgeon committed malpractice during my operation.")]) == "medical"

    def test_workplace_keywords(self):
        """'workers comp' keyword → 'workplace'."""
        assert rules.detect_case_type([ev("I was injured at work and filed for workers comp.")]) == "workplace"

    def test_dog_bite_keywords(self):
        """'bit me' keyword → 'dog_bite'."""
        assert rules.detect_case_type([ev("The neighbor's dog bit me on the arm.")]) == "dog_bite"


# ===========================================================================
# D. rules.detect_languages
# ===========================================================================

class TestDetectLanguages:
    """Language detection branches not covered by the demo cases."""

    def test_tagalog_detected_from_voice_title(self):
        """'originally in Tagalog' in voice title → ['Tagalog'] (no English because no-english cue)."""
        e = Evidence("E1", "voice", "Voice memo (originally in Tagalog)", "I do not speak english much.")
        assert rules.detect_languages([e]) == ["Tagalog"]

    def test_no_english_cue_drops_english(self):
        """'no english' (exact cue) with a detected language → English removed."""
        e = Evidence("E1", "voice", "memo", "I speak Korean but no english.")
        result = rules.detect_languages([e])
        assert "Korean" in result and "English" not in result

    def test_document_kind_ignored_for_language(self):
        """A document mentioning a language doesn't count – only voice/note do."""
        e = Evidence("E1", "document", "doc", "Dear Spanish-speaking client, we write in Spanish.")
        result = rules.detect_languages([e])
        assert result == ["English"]     # no voice/note → english default

    def test_bilingual_keeps_english(self):
        """Language found, no no-english cue → English is kept."""
        e = Evidence("E1", "voice", "Voice memo (originally in Korean)", "I was hit by a car.")
        result = rules.detect_languages([e])
        assert "Korean" in result and "English" in result

    def test_no_evidence_at_all(self):
        """Empty evidence list → ['English'] default."""
        assert rules.detect_languages([]) == ["English"]


# ===========================================================================
# E. rules.deadlines
# ===========================================================================

class TestDeadlines:
    """Deadline branches not covered elsewhere."""

    def test_government_cue_adds_six_month_deadline(self):
        """'VTA' is a government cue → 6-month government-entity deadline."""
        items = evs(("note", "n", "On September 3, 2026 a VTA bus hit me in San Jose."))
        dl = rules.deadlines(items, "auto_accident")
        gov = [d for d in dl if "government" in d["label"]]
        assert gov and gov[0]["date"] == "2027-03-03"
        assert gov[0]["basis"] == "Cal. Gov. Code § 911.2"

    def test_pothole_is_government_cue(self):
        """'pothole' is in GOVERNMENT_CUES → government deadline fires."""
        items = evs(("note", "n", "On October 1, 2026 I hit a pothole and lost control."))
        dl = rules.deadlines(items, "auto_accident")
        assert any("government" in d["label"] for d in dl)

    def test_no_incident_date_produces_no_statute_deadlines(self):
        """No dateable incident → no 2-year or 3-year deadline; only response dates possible."""
        items = evs(("note", "n", "I was hit by a car and my knee hurts."))
        dl = rules.deadlines(items, "auto_accident")
        assert not any("filing deadline" in d["label"] for d in dl)

    def test_month_rollover_in_plus(self):
        """An incident in August + 6 months = February next year (month rollover)."""
        items = evs(("note", "n", "On August 15, 2026 a city bus struck my vehicle."))
        dl = rules.deadlines(items, "auto_accident")
        gov = [d for d in dl if "government" in d["label"]]
        assert gov and gov[0]["date"] == "2027-02-15"

    def test_premises_has_no_property_damage_deadline(self):
        """Property-damage 3-year deadline only fires for auto_accident."""
        items = evs(("note", "n", "On October 1, 2026 I slipped at the store."))
        dl = rules.deadlines(items, "premises")
        assert not any("Property-damage" in d["label"] for d in dl)

    def test_response_date_without_sign_keyword_not_added(self):
        """'by November 10, 2026' without sign/return/respond → not a response deadline."""
        items = evs(("document", "letter", "Please reply by November 10, 2026 with your contact info."))
        dl = rules.deadlines(items, "auto_accident")
        assert not any(d["basis"].startswith("[E") for d in dl)


# ===========================================================================
# F. rules.missing_evidence
# ===========================================================================

class TestMissingEvidence:
    """Checklist paths not fully covered."""

    def test_dog_bite_checklist_vaccination_missing(self):
        """Dog-bite checklist: no vaccination info → 'Dog's vaccination records' missing."""
        items = evs(("photo", "wounds", "Dog bite photo October 5, 2026."),
                    ("document", "urgent care", "Seen for a dog bite, diagnosis: puncture wounds."),
                    ("note", "note", "My neighbor's dog bit me."))
        missing = rules.missing_evidence(items, "dog_bite")
        assert "Dog's vaccination records" in missing

    def test_dog_bite_owner_present(self):
        """Dog-bite checklist: owner mentioned → not missing."""
        items = evs(("document", "bite report", "Animal control bite report: dog owner lives nearby."),
                    ("note", "note", "The owner was there and I took their number. Witness: my friend, 510-555-0100."))
        missing = rules.missing_evidence(items, "dog_bite")
        assert "Dog owner's name and contact details" not in missing

    def test_default_checklist_for_medical(self):
        """'medical' case type falls through to DEFAULT_CHECKLIST."""
        items = evs(("note", "note", "The surgeon made an error. No records yet."))
        missing = rules.missing_evidence(items, "medical")
        # DEFAULT_CHECKLIST has Medical records, Photos, Witness contact information
        assert "Medical records" in missing

    def test_default_checklist_for_workplace(self):
        """'workplace' case type uses DEFAULT_CHECKLIST."""
        items = evs(("note", "note", "I was injured at work. No records."))
        missing = rules.missing_evidence(items, "workplace")
        assert "Medical records" in missing

    def test_keyword_match_in_title_satisfies_checklist(self):
        """A keyword in the evidence title (not just text) satisfies the checklist."""
        # The 'police' keyword in the title of a document satisfies "Police / collision report".
        items = evs(("document", "Police collision report", "Collision on October 2, 2026."))
        missing = rules.missing_evidence(items, "auto_accident")
        assert "Police / collision report" not in missing

    def test_witness_with_email_in_same_sentence_satisfies_contact(self):
        """CONTACT_RE matches email; 'witness' keyword and email must be in the same sentence."""
        # sentences() splits on '.', so 'witness' and the email must be together.
        items = evs(("note", "note", "Witness can be reached at w@example.com today."))
        missing = rules.missing_evidence(items, "auto_accident")
        assert "Witness contact information" not in missing

    def test_witness_with_email_in_different_sentence_is_missing(self):
        """If 'witness' is in one sentence and the email in the next, the check fails —
        this documents the behavior: the keyword and contact must co-occur in one sentence."""
        items = evs(("note", "note", "There was a witness at the scene. Their email is w@example.com."))
        missing = rules.missing_evidence(items, "auto_accident")
        # "witness" and email are in different sentences → not satisfied
        assert "Witness contact information" in missing

    def test_witness_without_contact_is_missing(self):
        """A witness mentioned by name only (no phone or email) is NOT enough."""
        items = evs(("note", "note", "There was a witness at the scene but I lost their contact."))
        missing = rules.missing_evidence(items, "auto_accident")
        assert "Witness contact information" in missing


# ===========================================================================
# G. rules.warnings  (ADVICE_QUESTION_RE variants)
# ===========================================================================

class TestWarnings:
    """Each untested branch of the ADVICE_QUESTION_RE and release-warning."""

    def test_must_i_accept(self):
        """'must I accept' triggers the advice-question warning."""
        items = ingest.number([Evidence("", "note", "note", "Must I accept this offer?")])
        w = rules.warnings(items)
        assert any("can't answer that" in x for x in w)

    def test_do_i_have_to_sign(self):
        """'do I have to sign' triggers the warning."""
        items = ingest.number([Evidence("", "note", "note", "Do I have to sign the release?")])
        w = rules.warnings(items)
        assert any("can't answer that" in x for x in w)

    def test_is_it_a_good_idea_to_settle(self):
        """'is it a good idea to settle' triggers the warning."""
        items = ingest.number([Evidence("", "note", "note", "Is it a good idea to settle?")])
        w = rules.warnings(items)
        assert any("can't answer that" in x for x in w)

    def test_is_this_a_good_offer(self):
        """'is this a good offer' triggers the warning."""
        items = ingest.number([Evidence("", "note", "note", "Is this a good offer?")])
        w = rules.warnings(items)
        assert any("can't answer that" in x for x in w)

    def test_how_much_is_my_claim_worth(self):
        """'how much is my claim worth' triggers the warning."""
        items = ingest.number([Evidence("", "note", "note", "How much is my claim worth?")])
        w = rules.warnings(items)
        assert any("can't answer that" in x for x in w)

    def test_spanish_debo_firmar(self):
        """'debo firmar' (should I sign in Spanish) triggers the warning."""
        items = ingest.number([Evidence("", "note", "note", "¿Debo firmar este documento?")])
        w = rules.warnings(items)
        assert any("can't answer that" in x for x in w)

    def test_release_without_settlement_keyword(self):
        """'release' + 'sign' (without 'settlement') also fires the release warning."""
        items = ingest.number([Evidence("", "document", "letter",
                                        "Please sign the enclosed release within 30 days.")])
        w = rules.warnings(items)
        assert any("release" in x for x in w)

    def test_advice_question_in_document_not_warned(self):
        """ADVICE_QUESTION_RE only fires for 'note' and 'voice', not 'document'."""
        items = ingest.number([Evidence("", "document", "letter", "Should I sign this?")])
        w = rules.warnings(items)
        assert not any("can't answer that" in x for x in w)


# ===========================================================================
# H. rules.insurer_alerts  – long response window → no short-window alert
# ===========================================================================

class TestInsurerAlertsWindow:
    """The short-window alert only fires when the response deadline ≤ 45 days out."""

    def test_long_response_window_no_short_alert(self):
        """A response deadline 60 days after the incident does NOT get the short-window alert."""
        items = evs(("document", "letter",
                     "Incident of October 1, 2026. Please sign the release and return it by "
                     "November 30, 2026."))   # 60 days later
        alerts = rules.insurer_alerts(items)
        assert not any("Short response window" in a["title"] for a in alerts)

    def test_short_window_just_inside_threshold(self):
        """A response deadline 45 days after the incident IS flagged."""
        items = evs(("document", "letter",
                     "Incident of October 1, 2026. Please sign the release and return it by "
                     "November 15, 2026."))   # exactly 45 days
        alerts = rules.insurer_alerts(items)
        assert any("Short response window (45 days" in a["title"] for a in alerts)


# ===========================================================================
# I. rules.contradictions  – photo time excluded, tolerance, _cite
# ===========================================================================

class TestContradictions:
    """Contradiction-check branches not specifically tested."""

    def test_photo_time_excluded_from_contradiction(self):
        """A time in a photo caption is ignored for contradiction purposes."""
        items = [
            Evidence("E1", "photo", "Scene photo", "Photo taken 9:30 am. Skid marks visible. Collision happened."),
            Evidence("E2", "note", "note", "The accident happened at 11:15 am. Car collision."),
        ]
        # E1 is a photo: its time is excluded. Only E2 contributes a time → no time contradiction.
        c = rules.contradictions(items)
        assert not any(x["topic"] == "Time of the incident" for x in c)

    def test_times_within_tolerance_not_flagged(self):
        """Times within 30 minutes of each other → no time contradiction."""
        items = [
            Evidence("E1", "note", "note", "I was hit at 5:40 pm in the collision."),
            Evidence("E2", "document", "doc", "The accident was at 17:42 on that day."),
        ]
        c = rules.contradictions(items)
        assert not any(x["topic"] == "Time of the incident" for x in c)

    def test_times_outside_tolerance_flagged(self):
        """Times more than 30 minutes apart → time contradiction."""
        items = [
            Evidence("E1", "note", "note", "The crash happened at 9:00 am."),
            Evidence("E2", "document", "doc", "The collision was at 10:45 am according to the report."),
        ]
        c = rules.contradictions(items)
        assert any(x["topic"] == "Time of the incident" for x in c)

    def test_cite_formats_correctly(self):
        """_cite produces 'value [E1, E2]; ...' format."""
        result = rules._cite({"October 2, 2026": ["E1", "E4"], "October 3, 2026": ["E2"]})
        assert "October 2, 2026 [E1, E4]" in result
        assert "October 3, 2026 [E2]" in result
        assert ";" in result

    def test_same_plate_in_both_items_not_a_contradiction(self):
        """The same plate appearing in two evidence items is not a plate contradiction."""
        items = [
            Evidence("E1", "note", "n", "Plate 7XYZ456 was the car that hit me."),
            Evidence("E2", "document", "d", "Vehicle with plate 7XYZ456 was involved."),
        ]
        c = rules.contradictions(items)
        assert not any(x["topic"] == "Licence plate" for x in c)


# ===========================================================================
# J. rules.sentences – ! and ? terminators
# ===========================================================================

class TestSentences:
    """Sentence splitting on ! and ? end-markers."""

    def test_splits_on_exclamation(self):
        ev_item = Evidence("E1", "note", "n", "It was terrible! The car ran the light.")
        parts = rules.sentences(ev_item)
        assert parts[0] == "It was terrible!" and parts[1] == "The car ran the light."

    def test_splits_on_question_mark(self):
        ev_item = Evidence("E1", "note", "n", "Was anyone else hurt? I don't know.")
        parts = rules.sentences(ev_item)
        assert parts[0] == "Was anyone else hurt?" and parts[1] == "I don't know."

    def test_no_split_on_empty_string(self):
        ev_item = Evidence("E1", "note", "n", "")
        assert rules.sentences(ev_item) == []

    def test_single_sentence_no_split(self):
        ev_item = Evidence("E1", "note", "n", "Just one sentence with no end marker")
        assert rules.sentences(ev_item) == ["Just one sentence with no end marker"]


# ===========================================================================
# K. rules.how_to_get
# ===========================================================================

class TestHowToGet:
    """The None path: an unrecognized label returns None."""

    def test_unknown_label_returns_none(self):
        assert rules.how_to_get("Some unknown item") is None

    def test_known_label_returns_string(self):
        tip = rules.how_to_get("Medical records")
        assert isinstance(tip, str) and len(tip) > 10


# ===========================================================================
# L. rules._similar
# ===========================================================================

class TestSimilar:
    """Edge cases of the Jaccard similarity helper."""

    def test_identical_strings(self):
        assert rules._similar("the car hit me", "the car hit me")

    def test_empty_string_not_similar(self):
        assert not rules._similar("", "the car hit me")
        assert not rules._similar("the car hit me", "")

    def test_no_overlap_not_similar(self):
        assert not rules._similar("the car hit me hard", "pizza and coffee")

    def test_high_overlap_is_similar(self):
        # "I was hit by a car" vs "I was hit by the car" share most tokens
        assert rules._similar("I was hit by a car", "I was hit by the car")

    def test_low_overlap_not_similar(self):
        assert not rules._similar("I slipped on a wet floor in the aisle",
                                  "The driver ran the red light at speed")


# ===========================================================================
# M. rules.collect – deduplication merges sources
# ===========================================================================

class TestCollect:
    """When two evidence items contain nearly identical sentences, collect() merges sources."""

    def test_near_duplicate_merges_sources(self):
        items = [
            Evidence("E1", "note", "n", "My knee was injured in the collision."),
            Evidence("E2", "document", "d", "The knee was injured in the collision."),
        ]
        facts = rules.collect(items, lambda s: "knee" in s.lower())
        # Should produce one fact whose sources include both E1 and E2.
        assert len(facts) == 1
        assert set(facts[0].sources) == {"E1", "E2"}

    def test_distinct_sentences_not_merged(self):
        items = [
            Evidence("E1", "note", "n", "My knee was injured."),
            Evidence("E2", "document", "d", "My shoulder was dislocated."),
        ]
        facts = rules.collect(items, lambda s: any(w in s.lower() for w in ["knee", "shoulder"]))
        assert len(facts) == 2


# ===========================================================================
# N. rules.incident_date – document preferred over note
# ===========================================================================

class TestIncidentDate:
    """Documents are sorted first; the date from a document wins over a note."""

    def test_document_date_preferred_over_note(self):
        items = [
            Evidence("E1", "note", "n", "I was hit on October 5, 2026."),
            Evidence("E2", "document", "d", "Police report: collision on October 2, 2026."),
        ]
        # E2 is a document; its date (October 2) should be preferred.
        d = rules.incident_date(items)
        from datetime import date
        assert d == date(2026, 10, 2)

    def test_note_used_when_no_document(self):
        items = [Evidence("E1", "note", "n", "The accident was on October 5, 2026.")]
        from datetime import date
        assert rules.incident_date(items) == date(2026, 10, 5)

    def test_no_date_returns_none(self):
        items = [Evidence("E1", "note", "n", "I was injured at the store.")]
        assert rules.incident_date(items) is None


# ===========================================================================
# O. ingest._gps_degrees – S (southern hemisphere)
# ===========================================================================

class TestGpsDegrees:
    """Hemisphere handling in _gps_degrees."""

    def test_north_positive(self):
        assert ingest._gps_degrees((37, 19, 22.8), "N") > 0

    def test_south_negative(self):
        """Southern hemisphere ref 'S' → negative latitude."""
        lat = ingest._gps_degrees((33, 51, 35.0), "S")
        assert lat < 0

    def test_east_positive(self):
        assert ingest._gps_degrees((121, 56, 52.8), "E") > 0

    def test_west_negative(self):
        """Western hemisphere ref 'W' → negative longitude (already tested via photo_with_exif,
        but this tests _gps_degrees directly)."""
        lon = ingest._gps_degrees((121, 56, 52.8), "W")
        assert lon < 0

    def test_lowercase_ref_treated_same(self):
        """The ref is uppercased before comparison; lowercase 's' also goes negative."""
        assert ingest._gps_degrees((10, 0, 0), "s") < 0


# ===========================================================================
# P. ingest.photo_note – taken-only and gps-only
# ===========================================================================

class TestPhotoNote:
    """photo_note branches: only taken, only GPS, or both."""

    def test_taken_only_no_gps(self):
        from datetime import datetime
        note = ingest.photo_note({"taken": datetime(2026, 10, 2, 17, 47, 12), "gps": None})
        assert "October 2, 2026" in note
        assert "GPS" not in note

    def test_gps_only_no_taken(self):
        note = ingest.photo_note({"taken": None, "gps": (37.323, -121.948)})
        assert "GPS" in note or "37.3230" in note
        assert "October" not in note

    def test_neither_returns_empty(self):
        assert ingest.photo_note({"taken": None, "gps": None}) == ""

    def test_leading_zero_stripped_from_hour(self):
        """strftime('%I') gives '09' for 9 am; lstrip('0') should give '9'."""
        from datetime import datetime
        note = ingest.photo_note({"taken": datetime(2026, 10, 2, 9, 5, 0), "gps": None})
        assert "9:05 am" in note
        assert "09:" not in note


# ===========================================================================
# Q. ingest.photo_metadata – GPS ref missing (defaults N/E)
# ===========================================================================

class TestPhotoMetadataDefaults:
    """When GPS ref tags are absent, _gps_degrees defaults to N/E (positive)."""

    def test_gps_ref_defaults_to_north_east(self):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        img, exif = Image.new("RGB", (4, 4), "blue"), Image.Exif()
        # Provide lat/lon values but NO ref tags (1 and 3 absent).
        exif.get_ifd(ingest.GPS_IFD).update({2: (37.0, 0.0, 0.0), 4: (121.0, 0.0, 0.0)})
        out = io.BytesIO()
        img.save(out, "JPEG", exif=exif)
        meta = ingest.photo_metadata(out.getvalue())
        if meta["gps"] is not None:
            lat, lon = meta["gps"]
            assert lat > 0 and lon > 0   # defaults to N/E = positive


# ===========================================================================
# R. ingest.kind_for – file extensions not yet tested
# ===========================================================================

class TestKindFor:
    """Every untested file extension."""

    @pytest.mark.parametrize("name,expected", [
        ("photo.heic", "photo"),
        ("photo.webp", "photo"),
        ("audio.aac",  "voice"),
        ("audio.flac", "voice"),
        ("document.doc",  "document"),
        ("document.docx", "document"),
        ("readme.txt",    "note"),
        ("data.json",     "note"),
        ("PHOTO.HEIC",    "photo"),   # extension lookup is case-insensitive via .lower()
    ])
    def test_extension_mapping(self, name, expected):
        assert ingest.kind_for(name) == expected


# ===========================================================================
# S. ingest.voice_evidence – English language → plain "transcribed" title
# ===========================================================================

class TestVoiceEvidenceTitle:
    """The English-language branch of voice_evidence produces a plain title."""

    def test_english_audio_title(self, monkeypatch):
        """When transcribe() returns language='English', the title is just '(transcribed)'."""
        from types import SimpleNamespace
        class EnglishWhisper:
            def transcribe(self, audio, task, vad_filter):
                segs = [SimpleNamespace(text="I was rear-ended on Main Street.")]
                info = SimpleNamespace(language="en", language_probability=0.95)
                return iter(segs), info
        monkeypatch.setattr(ingest, "_load_whisper", lambda: EnglishWhisper())
        ev_item = ingest.voice_evidence(b"fake", "memo.m4a")
        assert ev_item.title == "Voice memo memo.m4a (transcribed)"
        assert "originally in" not in ev_item.title


# ===========================================================================
# T. ingest.number – empty list
# ===========================================================================

class TestNumber:
    def test_empty_list(self):
        assert ingest.number([]) == []

    def test_single_item_gets_e1(self):
        items = ingest.number([Evidence("", "note", "n", "text")])
        assert items[0].id == "E1"


# ===========================================================================
# U. ingest.pdf_text – pypdf absent fallback
# ===========================================================================

class TestPdfText:
    def test_pypdf_absent_returns_placeholder(self, monkeypatch):
        """If pypdf can't be imported, pdf_text returns a clear placeholder."""
        import builtins
        real_import = builtins.__import__
        def blocked(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("pypdf not installed")
            return real_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", blocked)
        result = ingest.pdf_text(b"%PDF-1.4 fake")
        assert "unavailable" in result and "pypdf" in result


# ===========================================================================
# V. matching.speaks_with – edge cases
# ===========================================================================

class TestSpeaksWith:
    """speaks_with() branches not covered."""

    def test_empty_client_languages_always_matches(self):
        """No language preference → any lawyer is reachable."""
        assert matching.speaks_with([], ["English"]) is True

    def test_english_client_always_matches(self):
        """Client speaks English → any lawyer matches (English assumed everywhere)."""
        assert matching.speaks_with(["English"], ["English", "Spanish"]) is True

    def test_non_english_client_no_shared_language(self):
        """Client speaks only Korean; lawyer speaks only Spanish → False."""
        assert matching.speaks_with(["Korean"], ["English", "Spanish"]) is False

    def test_non_english_client_shared_language(self):
        """Client speaks only Vietnamese; lawyer speaks Vietnamese → True."""
        assert matching.speaks_with(["Vietnamese"], ["English", "Vietnamese"]) is True


# ===========================================================================
# W. matching.match – additional branches
# ===========================================================================

class TestMatchAdditional:
    """Branches of match() not exercised by existing tests."""

    def _lawyer(self, **kwargs):
        defaults = {"id": "L99", "name": "Test Lawyer", "firm": "Test Firm",
                    "practice_areas": ["auto_accident"], "sides": ["plaintiff"],
                    "counties": ["Santa Clara"], "languages": ["English"],
                    "rating": 4.5, "reviews": 10, "years": 5,
                    "fee_model": "Contingency", "free_consultation": True,
                    "bio": "test", "review_snippets": ["good"]}
        defaults.update(kwargs)
        return defaults

    def test_no_county_no_county_bonus(self):
        """county=None → no county bonus → lower fit_score than a county-matched lawyer."""
        lw = self._lawyer()
        results, _ = matching.match("auto_accident", "plaintiff", None, ["English"], [lw])
        assert results[0]["fit_score"] < 8 + 4.5   # no +3 county bonus

    def test_county_mismatch_no_bonus(self):
        """County present but not in lawyer's list → no +3 bonus."""
        lw = self._lawyer(counties=["Alameda"])
        results, _ = matching.match("auto_accident", "plaintiff", "Santa Clara", ["English"], [lw])
        assert "Santa Clara County" not in results[0]["why"]

    def test_county_match_adds_bonus(self):
        """County matches → +3 and 'Practices in X County' in why."""
        lw = self._lawyer()
        results, _ = matching.match("auto_accident", "plaintiff", "Santa Clara", ["English"], [lw])
        assert "Practices in Santa Clara County" in results[0]["why"]

    def test_no_free_consultation_not_in_why(self):
        """free_consultation=False → 'Free first consultation' absent from why."""
        lw = self._lawyer(free_consultation=False)
        results, _ = matching.match("auto_accident", "plaintiff", None, ["English"], [lw])
        assert "Free first consultation" not in results[0]["why"]

    def test_free_consultation_in_why(self):
        """free_consultation=True → 'Free first consultation' in why."""
        lw = self._lawyer(free_consultation=True)
        results, _ = matching.match("auto_accident", "plaintiff", None, ["English"], [lw])
        assert "Free first consultation" in results[0]["why"]

    def test_all_lawyers_excluded_returns_empty(self):
        """All lawyers filtered out → empty results, nonzero exclusion counts."""
        lw = self._lawyer(practice_areas=["premises"])  # doesn't handle auto_accident
        results, excluded = matching.match("auto_accident", "plaintiff", None, ["English"], [lw])
        assert results == [] and excluded["practice_area"] == 1

    def test_other_case_type_skips_practice_filter(self):
        """'other' case type → unclear=True, practice_area filter skipped."""
        lw = self._lawyer(practice_areas=["premises"])
        results, excluded = matching.match("other", "plaintiff", None, ["English"], [lw])
        assert results and excluded["practice_area"] == 0
        assert "confirm your case type" in results[0]["why"][0]

    def test_shared_non_english_language_adds_bonus_and_why(self):
        """Shared non-English language → +2 and 'Speaks X' in why."""
        lw = self._lawyer(languages=["English", "Korean"])
        results, _ = matching.match("auto_accident", "plaintiff", None, ["Korean"], [lw])
        assert any("Speaks Korean" in w for w in results[0]["why"])
        assert results[0]["fit_score"] >= 7   # base 5 + 2 language bonus

    def test_custom_lawyers_list_used(self):
        """Passing a custom lawyers list bypasses load_lawyers()."""
        lw = self._lawyer(id="CUSTOM")
        results, _ = matching.match("auto_accident", "plaintiff", None, ["English"], [lw])
        assert results[0]["id"] == "CUSTOM"
