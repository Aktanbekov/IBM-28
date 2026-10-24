"""Engine lane: voice intake, the second demo case, redaction, language-aware matching."""
import os
from types import SimpleNamespace

os.environ["LLM_BACKEND"] = "rules"

import pytest  # noqa: E402

from casebridge import brief, ingest, matching, rules, safety  # noqa: E402
from casebridge.models import CaseBrief, Evidence, Fact  # noqa: E402


# --- voice memos -------------------------------------------------------------------------

class FakeWhisper:
    """Simulates faster-whisper for two tasks:
    - task="translate"   → English translation of Spanish audio
    - task="transcribe"  → original-language transcript (Spanish)
    """
    def __init__(self):
        self.calls = []   # (task, language) for each call, so tests can check what was asked

    def transcribe(self, audio, task, vad_filter, language=None):
        assert task in ("translate", "transcribe")
        self.calls.append((task, language))
        info = SimpleNamespace(language="es", language_probability=0.92)
        if task == "translate":
            segs = [SimpleNamespace(text=" I slipped on a wet floor at the store."),
                    SimpleNamespace(text=" My name is Rosa Martínez. ")]
        else:  # task="transcribe" — original Spanish
            segs = [SimpleNamespace(text=" Me resbalé en el piso mojado de la tienda."),
                    SimpleNamespace(text=" Mi nombre es Rosa Martínez. ")]
        return iter(segs), info


@pytest.fixture
def whisper(monkeypatch):
    monkeypatch.setattr(ingest, "_load_whisper", lambda: FakeWhisper())


def test_voice_memo_is_transcribed_with_language(whisper):
    text, lang = ingest.transcribe(b"fake-audio", "memo.m4a")
    # English translation comes first; original Spanish appended after the label.
    assert "I slipped on a wet floor at the store." in text
    assert "Original (Spanish):" in text
    assert "Me resbalé en el piso mojado" in text
    assert lang == "Spanish"


def test_voice_memo_low_confidence_language_is_unknown(monkeypatch):
    """language_probability < 0.5 → language returned as None (unknown)."""
    class LowConfidenceWhisper:
        def transcribe(self, audio, task, vad_filter):
            assert task == "translate"
            segs = [SimpleNamespace(text=" Some words.")]
            info = SimpleNamespace(language="xx", language_probability=0.3)
            return iter(segs), info
    monkeypatch.setattr(ingest, "_load_whisper", lambda: LowConfidenceWhisper())
    text, lang = ingest.transcribe(b"fake-audio", "memo.m4a")
    assert lang is None
    assert "Some words." in text


def test_voice_evidence_feeds_language_into_brief(whisper):
    ev = ingest.number([ingest.voice_evidence(b"fake-audio", "memo.m4a")])
    assert ev[0].kind == "voice" and "originally in Spanish" in ev[0].title
    b = brief.build(ev)
    assert "Spanish" in b.languages and b.case_type == "premises"


def test_transcription_failure_never_crashes(monkeypatch):
    def broken():
        raise ImportError("no faster_whisper")
    monkeypatch.setattr(ingest, "_load_whisper", broken)
    ev = ingest.voice_evidence(b"fake-audio", "memo.m4a")
    assert "unavailable" in ev.text and "needs a typed transcript" in ev.title


def test_audio_file_types():
    for name in ("a.m4a", "a.MP3", "a.wav", "a.ogg", "a.webm", "a.opus"):
        assert ingest.kind_for(name) == "voice"


# --- second demo case: Rosa, Spanish speaker, slip and fall in Fremont -------------------

def rosa():
    ev = ingest.load_demo_case("rosa")
    return ev, brief.build(ev)


def test_rosa_case_classified():
    _, b = rosa()
    assert (b.case_type, b.client_side, b.county) == ("premises", "plaintiff", "Alameda")
    assert "Spanish" in b.languages


def test_rosa_rules():
    _, b = rosa()
    assert "Incident report from the property" in b.missing_evidence   # store kept the only copy
    assert "Witness contact information" not in b.missing_evidence     # witness gave his number
    dates = {d["date"] for d in b.deadlines}
    assert {"2028-10-09", "2026-11-06"} <= dates
    assert any("release" in w for w in b.warnings)


def test_rosa_matches_spanish_speaking_premises_lawyer_first():
    ev, b = rosa()
    results, _ = matching.match(b.case_type, b.client_side, b.county, rules.detect_languages(ev))
    assert results[0]["id"] == "L13"
    assert all("Spanish" in r["languages"] for r in results)


# --- no personal details reach the lawyer view --------------------------------------------

MARIA_SECRETS = ["Maria", "Lopez", "Kevin", "Holt", "Paula", "Grant", "555-0142", "8ABC123",
                 "pgrant@", "04/12/1991", "SJ-26-118842"]
ROSA_SECRETS = ["Rosa", "María", "Martínez", "Martinez", "Luis", "Ortega", "Derek", "Shaw", "Brian",
                "Cole", "Mehta", "555-0187", "555-0133", "555-0161", "4120 Peralta", "Apt 12", "94536",
                "03/08/1984", "88213407", "HC-55190", "4417-2290-31"]
BAO_SECRETS = ["Nguyen", "Bao", "Whitmore", "Chad", "Lam", "Patricia", "Vo", "Ellison",
               "555-0174", "555-0162", "555-0193", "312 Senter", "Apt 5", "95111",
               "02/27/1953", "05/19/1988", "30917452", "CS-7723041", "SJ-26-204417", "8TRV015"]


@pytest.mark.parametrize("case,secrets", [("maria", MARIA_SECRETS), ("rosa", ROSA_SECRETS),
                                           ("bao", BAO_SECRETS)])
def test_lawyer_view_has_no_personal_details(case, secrets):
    ev = ingest.load_demo_case(case)
    names = safety.find_names([e.text for e in ev])
    red = safety.redact_brief(brief.build(ev), names)
    assert safety.find_leaks(red, names) == []
    for secret in secrets:
        assert secret not in str(red), secret
    # Stricter: even the raw evidence, redacted, leaks nothing.
    raw = " ".join(safety.redact(e.text, names) for e in ev)
    for secret in secrets:
        assert secret not in raw, secret


@pytest.mark.parametrize("text,secret", [
    ("Call me at 408.555.0142", "555.0142"),
    ("or +1 650 555 0199 after 5", "555 0199"),
    ("my cell 4085550142", "4085550142"),
    ("SSN 123-45-6789", "123-45-6789"),
    ("email rosa.m+claims@mail.example.com", "rosa.m"),
    ("I live at 77 Oak Street, Unit 3B", "77 Oak"),
    ("we moved to 1500 W Hedding St.", "1500 W"),
    ("Fremont, CA 94538-1234", "94538"),
    ("Date of birth: March 8, 1984", "1984"),
    ("born on 1984-03-08", "1984"),
    ("fecha de nacimiento: 08/03/1984", "1984"),
    ("license plate 7XYZ456", "7XYZ456"),
    ("Policy # CA-9981234", "9981234"),
    ("VIN 1HGCM82633A004352", "1HGCM82633A004352"),
])
def test_pii_patterns(text, secret):
    assert secret not in safety.redact(text, {})


def test_names_in_spanish_and_without_accents():
    texts = ["Me llamo Rosa María Martínez.", "Testigo: Luis Ortega"]
    names = safety.find_names(texts)
    out = safety.redact("Rosa Martinez told Ms. Martínez's sister. Luis saw it. Maria agreed.", names)
    assert not any(n in out for n in ("Rosa", "Martinez", "Martínez", "Luis", "Maria")), out
    assert "[CLIENT] [CLIENT]" not in out


def test_redaction_keeps_case_facts():
    text = ("Collision on October 2, 2026 at Stevens Creek Blvd, San Jose. Offer of $1,200 [E5]. "
            "Cal. Code Civ. Proc. § 335.1. Follow up in 7 days.")
    assert safety.redact(text, {}) == text


def test_every_free_text_field_is_redacted():
    names = {"Kevin Holt": "[OTHER PARTY]"}
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", "Claim vs Kevin Holt.",
                  timeline=[Fact("Hit by Kevin Holt.", ["E1"], when="Kevin Holt's call")],
                  missing_evidence=["Letter from Kevin Holt"],
                  deadlines=[{"label": "Reply to Kevin Holt", "date": "2026-10-30", "basis": "[E1]"}])
    red = safety.redact_brief(b, names)
    assert "Kevin" not in str(red) and red["county"] == "Santa Clara"
    assert red["deadlines"][0]["date"] == "2026-10-30"


def test_find_leaks_reports_what_is_left():
    assert safety.find_leaks({"text": "Maria at 408-555-0142"}, {"Maria": "[CLIENT]"}) == \
        ["Maria", "408-555-0142"]
    assert safety.find_leaks({"text": "[CLIENT] at [PHONE]"}, {"Maria": "[CLIENT]"}) == []


def test_sentences_do_not_split_after_honorifics():
    ev = Evidence("E1", "document", "letter", "Dear Ms. Lopez, we write to you. Thanks.")
    assert rules.sentences(ev)[0] == "Dear Ms. Lopez, we write to you."


# --- language-aware matching --------------------------------------------------------------

def test_detect_languages():
    assert rules.detect_languages(ingest.load_demo_case("rosa")) == ["Spanish"]
    assert rules.detect_languages(ingest.load_demo_case("maria")) == ["Spanish", "English"]
    assert rules.detect_languages(ingest.load_demo_case("bao")) == ["Vietnamese"]
    assert rules.detect_languages([Evidence("E1", "note", "note", "I was hit.")]) == ["English"]


def test_client_without_english_only_sees_lawyers_they_can_talk_to():
    results, excluded = matching.match("premises", "plaintiff", "Alameda", ["Spanish"])
    assert results and all("Spanish" in r["languages"] for r in results)
    assert excluded["language"] >= 1


def test_bilingual_client_sees_everyone_with_shared_language_ranked_up():
    results, excluded = matching.match("premises", "plaintiff", "Alameda", ["Spanish", "English"])
    assert excluded["language"] == 0
    assert results[0]["id"] == "L13" and "Speaks Spanish" in results[0]["why"]


def test_unclear_language_still_counts_as_transcribed(monkeypatch):
    monkeypatch.setattr(ingest, "transcribe", lambda data, name, language=None: ("Some words.", None))
    assert "language unclear" in ingest.voice_evidence(b"x", "memo.m4a").title


def test_names_match_any_case_but_everyday_words_stay():
    names = {"Rosa Martinez": "[CLIENT]", "Will": "[PERSON]"}
    out = safety.redact("ROSA MARTINEZ said she will call. Will agreed.", names)
    assert out == "[CLIENT] said she will call. [PERSON] agreed."


# --- third demo case: Bao, Vietnamese-speaking grandmother, pedestrian hit in San Jose ------

def bao():
    ev = ingest.load_demo_case("bao")
    return ev, brief.build(ev)


def test_bao_case_classified():
    _, b = bao()
    assert (b.case_type, b.client_side, b.county) == ("auto_accident", "plaintiff", "Santa Clara")
    assert "Vietnamese" in b.languages
    assert "English" not in b.languages


def test_bao_rules():
    _, b = bao()
    # Police report and photos are present; medical records and witness contact are covered.
    assert "Police / collision report" not in b.missing_evidence
    assert "Photos of the scene or vehicles" not in b.missing_evidence
    # Statute deadlines must be anchored to the October 14, 2026 incident date.
    dates = {d["date"] for d in b.deadlines}
    assert "2028-10-14" in dates                    # 2-year personal-injury deadline
    # Release warning: insurer letter contains a release to sign.
    assert any("release" in w for w in b.warnings)
    # Insurer tactic alerts: recorded statement and no-lawyer-needed language.
    alert_titles = {a["title"] for a in b.alerts}
    assert "Recorded statement requested" in alert_titles
    assert "Suggestion that a lawyer isn't needed" in alert_titles


def test_bao_only_matches_vietnamese_lawyer():
    ev, b = bao()
    results, excluded = matching.match(b.case_type, b.client_side, b.county,
                                       rules.detect_languages(ev))
    # L4 Minh Tran is the only lawyer who speaks Vietnamese AND handles auto_accident plaintiff
    # in Santa Clara County.
    assert len(results) == 1
    assert results[0]["id"] == "L4"
    assert "Vietnamese" in results[0]["languages"]
    assert excluded["language"] >= 1          # lawyers without Vietnamese were excluded


def test_bao_lawyer_view_has_no_personal_details():
    ev = ingest.load_demo_case("bao")
    names = safety.find_names([e.text for e in ev])
    red = safety.redact_brief(brief.build(ev), names)
    assert safety.find_leaks(red, names) == []
    for secret in BAO_SECRETS:
        assert secret not in str(red), f"{secret!r} leaked into redacted brief"
    # Stricter: raw evidence texts, each individually redacted, must not contain secrets.
    raw = " ".join(safety.redact(e.text, names) for e in ev)
    for secret in BAO_SECRETS:
        assert secret not in raw, f"{secret!r} leaked from raw redacted evidence"


# --- the client can say which language they'll speak ---------------------------------------

def test_chosen_language_is_passed_to_whisper(monkeypatch):
    fake = FakeWhisper()
    monkeypatch.setattr(ingest, "_load_whisper", lambda: fake)
    text, lang = ingest.transcribe(b"fake-audio", "mic.webm", language="es")
    assert lang == "Spanish"
    assert fake.calls == [("translate", "es"), ("transcribe", "es")]
    assert "Original (Spanish): Me resbalé" in text


def test_chosen_language_skips_the_unsure_detection(monkeypatch):
    class Unsure(FakeWhisper):
        def transcribe(self, audio, task, vad_filter, language=None):
            segs, info = super().transcribe(audio, task, vad_filter, language)
            info.language, info.language_probability = "en", 0.3   # a short clip: Whisper guesses
            return segs, info
    monkeypatch.setattr(ingest, "_load_whisper", lambda: Unsure())
    assert ingest.transcribe(b"x", "mic.webm")[1] is None             # auto: unclear
    text, lang = ingest.transcribe(b"x", "mic.webm", language="vi")   # chosen: trusted
    assert lang == "Vietnamese" and "Original (Vietnamese):" in text
    assert "originally in Vietnamese" in ingest.voice_evidence(b"x", "mic.webm", "vi").title


def test_every_language_choice_is_one_matching_understands():
    for label, code in ingest.SPOKEN_LANGUAGES.items():
        assert code is None or code in ingest.LANGUAGE_NAMES, label
