"""Voice transcripts: filler sounds, swearing, insults and help-questions never reach the lawyer."""
from casebridge import ingest
from casebridge.safety import clean_speech


def test_angry_memo_keeps_only_the_fact():
    text, removed = clean_speech("This stupid driver crashed my car hm hm hm fuck him what to do")
    assert text == "This driver crashed my car."
    assert removed == 6


def test_fillers_and_masked_swearing_removed():
    text, _ = clean_speech("Um, so uh, the guy ran the red light and hit my door. F***ing idiot!")
    assert text == "So, the guy ran the red light and hit my door."


def test_help_question_dropped_but_injury_kept():
    assert clean_speech("I don't know what to do. My neck hurts.")[0] == "My neck hurts."


def test_ordinary_words_are_not_touched():
    original = "The assistant manager at the Hampton store said the umbrella stand was wet. Hello hello."
    assert clean_speech(original) == (original, 0)


def test_only_noise_becomes_empty():
    assert clean_speech("hmm uh um")[0] == ""


def test_voice_evidence_is_cleaned(monkeypatch):
    monkeypatch.setattr(ingest, "transcribe", lambda data, name, language=None: ("Uh, the damn truck hit me, hmm.", "English"))
    ev = ingest.voice_evidence(b"", "memo.webm")
    assert ev.text == "The truck hit me."
    assert ev.title.endswith("(transcribed)")


def test_voice_placeholder_is_left_alone(monkeypatch):
    placeholder = "[Could not transcribe this audio (ValueError). Please type what it says.]"
    monkeypatch.setattr(ingest, "transcribe", lambda data, name, language=None: (placeholder, None))
    assert ingest.voice_evidence(b"", "memo.webm").text == placeholder


def test_misheard_hmm_and_repeated_short_words_dropped():
    # Whisper often hears "hmm, hmm" as "Him, him".
    text, _ = clean_speech("This stupid driver crashed my car. Him, him. Fuck him. What do I do?")
    assert text == "This driver crashed my car."
    assert clean_speech("No no no. He hit me.")[0] == "He hit me."
    assert clean_speech("I was at the the light.")[0] == "I was at the the light."
