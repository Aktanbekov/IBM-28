"""Exact checks (numbers, fault words) set a statement aside; the AI fact check only marks one.
On watsonx, Granite as checker rejected even plainly supported statements and emptied the brief."""
import io
import urllib.error

from casebridge import brief, llm, safety, scoreboard
from casebridge.models import CaseBrief, Evidence, Fact

E1 = ("My car was rear-ended at a red light on Stevens Creek Blvd. "
      "The other driver was going 90 mph and admitted he was drunk.")
EV = [Evidence("E1", "note", "Written note from client", E1)]
GRANITE_REPLY = {
    "summary": "The client was rear-ended at a red light. The at-fault driver was traveling at an excessive "
               "speed of 90 mph and admitted to being intoxicated.",
    "timeline": [{"when": "", "text": "The client was rear-ended at a red light on Stevens Creek Blvd.",
                  "sources": ["E1"]}],
    "parties": [{"text": "The other driver rear-ended the client's vehicle.", "sources": ["E1"]}],
    "injuries": [{"text": "The client suffered injuries in the rear-end collision.", "sources": ["E1"]}],
    "damages": [{"text": "The client's vehicle sustained damage in the collision.", "sources": ["E1"]}],
    "case_type": "auto_accident",
}


def _granite_brief(monkeypatch, verdict):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm, "chat_json", lambda s, u: GRANITE_REPLY)
    monkeypatch.setattr(llm, "checker", lambda: "Granite Guardian (granite3-guardian, local)")
    monkeypatch.setattr(llm, "guardian_check", lambda text, risk, ev, token="": verdict(text))
    return brief.build(EV)


def test_fact_check_doubt_marks_but_never_removes(monkeypatch):
    b = _granite_brief(monkeypatch, lambda t: "rear-ended the client's vehicle" in t)
    assert [f.text for f in b.parties] == ["The other driver rear-ended the client's vehicle."]
    assert b.parties[0].guardian_flags
    stats = scoreboard.brief_stats(EV, b)
    assert (stats["facts"], stats["fact_check_flagged"]) == (2, 1)


def test_fact_check_rejecting_everything_keeps_the_brief(monkeypatch):
    """Live on watsonx, Granite as checker said "not supported" to every statement, including the
    rear-end at a red light that E1 states, and the brief came out empty."""
    b = _granite_brief(monkeypatch, lambda t: True)
    assert [f.text for f in b.timeline] == ["The client was rear-ended at a red light on Stevens Creek Blvd."]
    assert len(b.parties) == 1


def test_failed_fact_check_keeps_every_supported_statement(monkeypatch):
    b = _granite_brief(monkeypatch, lambda t: None)
    assert len(b.timeline) == len(b.parties) == 1


def test_invented_injury_and_damage_are_set_aside(monkeypatch):
    """Live on watsonx: E1 mentions no injury and no damage, yet Granite wrote both, unmarked."""
    reply = dict(GRANITE_REPLY, injuries=[{"text": "The client reports being injured in the collision.",
                                           "sources": ["E1"]}],
                 damages=[{"text": "The client's vehicle was damaged in the rear-end collision.", "sources": ["E1"]}])
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm, "chat_json", lambda s, u: reply)
    monkeypatch.setattr(llm, "checker", lambda: None)
    b = brief.build(EV)
    assert b.injuries == [] and b.damages == []
    aside = next(c for c in b.checks if c["id"] == "set_aside")["items"]
    assert {i["section"] for i in aside} == {"injuries", "damages"}
    assert scoreboard.brief_stats(EV, b)["set_aside"] == 2


def test_reworded_injury_is_kept():
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", "", injuries=[
        Fact("The client reports neck pain.", ["E1"]), Fact("The bumper was dented.", ["E2"])])
    safety.apply_guardrails(b, {"E1", "E2"}, {"E1": "My neck hurts since the crash.",
                                              "E2": "Photo: rear bumper damage."})
    assert len(b.injuries) == 2


def test_set_aside_statements_never_reach_lawyers():
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", "",
                  timeline=[Fact("The other driver was going 45 mph.", ["E1"])])
    safety.apply_guardrails(b, {"E1"}, {"E1": "The other driver was speeding."})
    assert "45 mph" not in str(safety.redact_brief(b, {}))


def test_summary_with_fault_words_is_rebuilt_from_evidence(monkeypatch):
    b = _granite_brief(monkeypatch, lambda t: False)
    assert "at-fault" not in b.summary and "intoxicated" not in b.summary
    assert b.summary_guardian_flags == []
    assert any(c["id"] == "summary" for c in b.checks)


def test_fault_word_needs_the_evidence_to_use_it():
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", "", timeline=[
        Fact("The at-fault driver ran the light.", ["E1"]),
        Fact("The report lists Vehicle 2 at fault.", ["E2"])])
    safety.apply_guardrails(b, {"E1", "E2"}, {"E1": "The other driver ran the light.",
                                              "E2": "Officer's note: Vehicle 2 at fault."})
    assert [f.text for f in b.timeline] == ["The report lists Vehicle 2 at fault."]


def test_invented_number_is_set_aside():
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", "",
                  timeline=[Fact("The other driver was going 45 mph.", ["E1"])])
    safety.apply_guardrails(b, {"E1"}, {"E1": "The other driver was speeding."})
    assert b.timeline == []
    assert next(c for c in b.checks if c["id"] == "set_aside")["items"][0]["reasons"]


def test_offline_demo_sets_nothing_aside():
    from casebridge import ingest
    for case in ("maria", "rosa", "bao"):
        b = brief.build(ingest.load_demo_case(case), use_llm=False)
        assert not any(c["id"] == "set_aside" for c in b.checks), case


def test_prompt_asks_granite_to_attribute_claims():
    assert "The client reports" in brief.SYSTEM_PROMPT and "at-fault" in brief.SYSTEM_PROMPT


def test_watsonx_rate_limit_is_retried_not_left_unchecked(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "watsonx")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "p")
    monkeypatch.setenv("WATSONX_MODEL", "ibm/granite-4-h-small")
    monkeypatch.setattr(llm, "_ollama_guardian", lambda: None)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def fake_post(url, payload, headers=None, form=False, timeout=120):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO(b""))
        return {"choices": [{"message": {"content": "Yes"}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    assert llm.guardian_check("The car was going 45 mph.", "", "The car was speeding.", token="t") is True
    assert len(calls) == 2
