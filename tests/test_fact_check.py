"""Fact check: numbers check (all modes), model choice on watsonx, and the Guardian call itself.
No network: every HTTP call is mocked."""
import os
import unittest.mock as mock

os.environ["LLM_BACKEND"] = "rules"

from casebridge import brief as brief_mod, ingest, llm, safety  # noqa: E402
from casebridge.models import CaseBrief, Evidence, Fact  # noqa: E402


# --- Numbers check -------------------------------------------------------------------------

def test_invented_speed_is_caught():
    assert safety.unsupported_numbers("The other car was going 45 mph.", ["Rear-ended at a red light."]) == ["45"]


def test_numbers_match_across_formats():
    evidence = ["Collision at 17:42 on 10/02/2026. Repair estimate $4,850.00."]
    assert safety.unsupported_numbers("At 5:42 pm on October 2, 2026 the car was hit.", evidence) == []
    assert safety.unsupported_numbers("Repairs cost $4850.", evidence) == []


def test_number_must_be_in_the_cited_evidence_not_elsewhere():
    b = CaseBrief("auto_accident", "plaintiff", "Santa Clara", "", engine="watsonx")
    b.damages = [Fact("Lost wages were $1,100.", ["E1"])]
    texts = {"E1": "Repair estimate $4,850.", "E2": "I lost $1,100 in wages."}
    assert safety.check_numbers(b, texts) == 1
    assert b.damages[0].guardian_flags == ["⚠ 1100 not in [E1]"]


def test_model_summary_checked_rules_summary_not():
    texts = {"E1": "Rear-ended on October 2."}
    model = CaseBrief("auto_accident", "plaintiff", "", "Hit at 60 mph.", engine="watsonx")
    rules = CaseBrief("auto_accident", "plaintiff", "", "6 pieces of evidence.", engine="rules")
    assert safety.check_numbers(model, texts) == 1
    assert safety.check_numbers(rules, texts) == 0


def test_demo_cases_have_no_false_alarms():
    for case in ("maria", "rosa", "bao"):
        b = brief_mod.build(ingest.load_demo_case(case), use_llm=False)
        facts = [f for s in ("timeline", "parties", "injuries", "damages") for f in getattr(b, s)]
        assert not any(f.guardian_flags for f in facts), case
        assert not b.summary_guardian_flags, case


def test_guardrails_warn_about_wrong_numbers():
    b = CaseBrief("auto_accident", "plaintiff", "", "", engine="watsonx")
    b.timeline = [Fact("The truck was going 70 mph.", ["E1"])]
    safety.apply_guardrails(b, {"E1"}, {"E1": "A truck hit my car."})
    assert any("number that isn't in the evidence" in w for w in b.warnings)


# --- Model choice ----------------------------------------------------------------------------

SPECS = {"resources": [
    {"model_id": "ibm/granite-4-h-small", "functions": [{"id": "text_chat"}],
     "lifecycle": [{"id": "available", "start_date": "2025-10-02"}]},
    {"model_id": "ibm/granite-guardian-3-8b", "functions": [{"id": "text_chat"}],
     "lifecycle": [{"id": "available", "start_date": "2024-10-21"}, {"id": "withdrawn", "start_date": "2026-09-30"}]},
]}


def test_withdrawn_models_are_skipped_and_granite_4_chosen(monkeypatch):
    monkeypatch.setattr(llm, "_models", None)
    monkeypatch.delenv("WATSONX_MODEL", raising=False)
    with mock.patch.object(llm, "_get", return_value=SPECS), \
         mock.patch.object(llm, "date") as fake_date:
        fake_date.today.return_value.isoformat.return_value = "2026-10-24"
        assert "ibm/granite-guardian-3-8b" not in llm.watsonx_models()
        assert llm.watsonx_model() == "ibm/granite-4-h-small"


def test_watsonx_model_env_override(monkeypatch):
    monkeypatch.setenv("WATSONX_MODEL", "ibm/some-new-granite")
    assert llm.watsonx_model() == "ibm/some-new-granite"


# --- Guardian call -------------------------------------------------------------------------

def test_yes_no_parsing():
    assert llm._yes_no("Yes") is True
    assert llm._yes_no(" no<|end_of_text|>") is False
    assert llm._yes_no("") is None


def test_groundedness_prompt_has_context_and_official_definition():
    prompt = llm._guardian_prompt("Going 45 mph.", llm.GROUNDEDNESS_DEFINITION, "Hit at a red light.")
    assert "Context: Hit at a red light." in prompt and "Assistant Message: Going 45 mph." in prompt
    assert "not grounded or faithful" in prompt
    assert prompt.endswith("<|start_of_role|>assistant<|end_of_role|>")


def test_local_guardian_used_when_pulled(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "watsonx")
    with mock.patch.object(llm, "_ollama_models", return_value=["granite3-guardian:2b"]), \
         mock.patch.object(llm, "_post", return_value={"response": "Yes"}) as post:
        assert llm.checker() == "Granite Guardian (granite3-guardian:2b, local)"
        assert llm.guardian_check("Going 45 mph.", "", "Hit at a red light.") is True
    assert post.call_args.args[0].endswith("/api/generate")
    assert post.call_args.args[1]["raw"] is True


def test_watsonx_granite_checks_when_no_local_guardian(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "watsonx")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "p")
    monkeypatch.setenv("WATSONX_MODEL", "ibm/granite-4-h-small")
    reply = {"choices": [{"message": {"content": "No."}}]}
    with mock.patch.object(llm, "_ollama_models", return_value=[]), \
         mock.patch.object(llm, "_post", return_value=reply) as post:
        assert llm.checker() == "Granite (ibm/granite-4-h-small) on watsonx"
        assert llm.guardian_check("Hit at a red light.", "", "Hit at a red light.", token="t") is False
    assert "/ml/v1/text/chat" in post.call_args.args[0]


def test_checker_off_in_rules_mode_and_errors_never_raise(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "rules")
    assert llm.checker() is None
    monkeypatch.setenv("LLM_BACKEND", "watsonx")
    with mock.patch.object(llm, "_ollama_models", return_value=["granite3-guardian:2b"]), \
         mock.patch.object(llm, "_post", side_effect=OSError("offline")):
        assert llm.guardian_check("x", "", "y") is None


def test_some_unchecked_facts_get_a_quiet_label():
    f1, f2 = Fact("Hit at a red light.", ["E1"]), Fact("Bumper dented.", ["E1"])
    b = CaseBrief("auto_accident", "plaintiff", "", "Rear-end crash.", engine="watsonx")
    b.timeline = [f1, f2]
    ev = [Evidence("E1", "note", "Note", "I was stopped at a red light when he hit me. The bumper is dented in.")]
    answers = {"Hit at a red light.": False, "Bumper dented.": None}
    with mock.patch("casebridge.llm.guardian_check", side_effect=lambda t, r, e, k: answers.get(t, False)), \
         mock.patch("casebridge.brief._fetch_token", return_value=""):
        brief_mod._apply_guardian(b, ev, "Granite Guardian")
    assert f1.guardian_flags == [] and f2.guardian_flags == ["Not checked"]


def test_auto_needs_the_chat_model_not_just_ollama(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "auto")
    monkeypatch.delenv("WATSONX_APIKEY", raising=False)
    with mock.patch.object(llm, "_ollama_models", return_value=["granite3-guardian:2b"]):
        assert llm.backend() == "rules"
        assert llm.checker() == "Granite Guardian (granite3-guardian:2b, local)"   # still usable offline
    with mock.patch.object(llm, "_ollama_models", return_value=["granite3.3:latest"]):
        assert llm.backend() == "ollama"


def test_exact_quotes_skip_the_model_check():
    quote, reworded = Fact("Driver reported no injuries.", ["E1"]), Fact("Nobody in the car was hurt.", ["E1"])
    b = CaseBrief("auto_accident", "plaintiff", "", "", engine="rules")
    b.parties = [quote, reworded]
    ev = [Evidence("E1", "document", "Report", "Pedestrian taken to hospital. Driver reported no injuries.")]
    with mock.patch("casebridge.llm.guardian_check", return_value=False) as check, \
         mock.patch("casebridge.brief._fetch_token", return_value=""):
        brief_mod._apply_guardian(b, ev, "Granite Guardian (granite3-guardian:2b, local)")
    assert [c.args[0] for c in check.call_args_list] == ["Nobody in the car was hurt."]
    guardian = b.checks[-1]
    assert guardian["status"] == "pass" and "1 statement is an exact quote" in guardian["detail"]


def test_month_names_support_numeric_dates():
    assert safety.unsupported_numbers("The crash was on 10/2/2026.", ["Collision on October 2, 2026."]) == []
    assert safety.unsupported_numbers("The crash was on 11/2/2026.", ["Collision on October 2, 2026."]) == ["11"]
