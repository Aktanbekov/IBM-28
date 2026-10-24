"""Statements a check finds unsupported leave the brief: the live Granite test showed invented
"suffered injuries" and "vehicle damage" marked "Not supported" but still listed and counted."""
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


def test_rejected_statements_leave_the_brief_and_the_count(monkeypatch):
    b = _granite_brief(monkeypatch, lambda t: "injuries" in t or "damage" in t)
    assert b.injuries == [] and b.damages == []
    aside = next(c for c in b.checks if c["id"] == "set_aside")["items"]
    assert [i["section"] for i in aside] == ["injuries", "damages"]
    stats = scoreboard.brief_stats(EV, b)
    assert (stats["facts"], stats["facts_cited"], stats["set_aside"]) == (2, 2, 2)


def test_set_aside_statements_never_reach_lawyers(monkeypatch):
    b = _granite_brief(monkeypatch, lambda t: "injuries" in t)
    red = safety.redact_brief(b, {})
    assert "suffered injuries" not in str(red)


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
