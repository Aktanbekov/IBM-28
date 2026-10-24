"""Tiny LLM client: IBM watsonx.ai (Granite) or local Ollama (Granite). Standard library only.

Backend is picked by LLM_BACKEND = auto | watsonx | ollama | rules (default auto):
  auto -> watsonx if WATSONX_APIKEY and WATSONX_PROJECT_ID are set, else Ollama if its Granite
  chat model is pulled, else rules-only.
Settings come from environment variables, or from a local .env file (never committed).

Check a setup in one command:  python -m casebridge.llm
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


def _load_dotenv(path: Path = Path(__file__).resolve().parent.parent / ".env") -> None:
    """KEY=VALUE lines from .env, without overriding variables already set in the shell."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").rstrip("/")
WATSONX_VERSION = "2024-10-08"
# Tried in order against the models this watsonx region offers today (IBM retires models often:
# granite-3-3-8b-instruct and granite-guardian-3-8b are gone). WATSONX_MODEL overrides.
WATSONX_CHAT_MODELS = ["ibm/granite-4-h-small", "ibm/granite-3-3-8b-instruct", "ibm/granite-3-8b-instruct"]
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "granite3.3")
OLLAMA_GUARDIAN_MODEL = os.getenv("OLLAMA_GUARDIAN_MODEL", "granite3-guardian")


def _post(url: str, payload: dict, headers: dict | None = None, form: bool = False, timeout=120) -> dict:
    if form:
        data = urllib.parse.urlencode(payload).encode()   # an API key may contain + or &
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        ctype = "application/json"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _get(url: str, timeout=10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def _ollama_models() -> list[str]:
    try:
        return [m["name"] for m in _get(f"{OLLAMA_URL}/api/tags", timeout=1).get("models", [])]
    except (OSError, ValueError):
        return []


def backend() -> str:
    choice = os.getenv("LLM_BACKEND", "auto")
    if choice != "auto":
        return choice
    if os.getenv("WATSONX_APIKEY") and os.getenv("WATSONX_PROJECT_ID"):
        return "watsonx"
    return "ollama" if any(m.split(":")[0] == OLLAMA_MODEL.split(":")[0] for m in _ollama_models()) else "rules"


# --- watsonx ---------------------------------------------------------------------------

_token = {"value": "", "expires": 0.0}
_token_lock = threading.Lock()
_models: dict[str, list[str]] | None = None


def watsonx_token() -> str:
    """IAM bearer token, reused until a minute before it expires (they last an hour)."""
    with _token_lock:
        if time.time() < _token["expires"]:
            return _token["value"]
        out = _post("https://iam.cloud.ibm.com/identity/token",
                    {"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                     "apikey": os.environ["WATSONX_APIKEY"]}, form=True, timeout=30)
        _token["value"] = out["access_token"]
        _token["expires"] = time.time() + int(out.get("expires_in", 3600)) - 60
        return _token["value"]


def watsonx_models() -> dict[str, list[str]]:
    """Models this region offers right now -> their functions (e.g. "text_chat"). The list is
    public, so this needs no key. Withdrawn models are left out. Empty if unreachable."""
    global _models
    if _models is None:
        try:
            specs = _get(f"{WATSONX_URL}/ml/v1/foundation_model_specs?version={WATSONX_VERSION}&limit=200")
        except (OSError, ValueError):
            _models = {}   # offline: don't retry on every page load
            return _models
        today = date.today().isoformat()
        _models = {
            m["model_id"]: [f["id"] for f in m.get("functions", [])]
            for m in specs.get("resources", [])
            if not any(s.get("id") == "withdrawn" and s.get("start_date", "9999") <= today
                       for s in m.get("lifecycle", []))
        }
    return _models


def watsonx_model() -> str:
    if os.getenv("WATSONX_MODEL"):
        return os.environ["WATSONX_MODEL"]
    available = watsonx_models()
    for model in WATSONX_CHAT_MODELS:
        if model in available:
            return model
    granite = sorted(m for m, fns in available.items() if "granite" in m and "text_chat" in fns)
    return granite[0] if granite else WATSONX_CHAT_MODELS[0]


def model_name() -> str:
    """The chat model the active backend uses, for the UI."""
    b = backend()
    return watsonx_model() if b == "watsonx" else OLLAMA_MODEL if b == "ollama" else "rules"


def chat(system: str, user: str, max_tokens: int = 2000, as_json: bool = True) -> str:
    b = backend()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if b == "watsonx":
        out = _post(f"{WATSONX_URL}/ml/v1/text/chat?version={WATSONX_VERSION}",
                    {"model_id": watsonx_model(), "project_id": os.environ["WATSONX_PROJECT_ID"],
                     "messages": messages, "max_tokens": max_tokens, "temperature": 0},
                    headers={"Authorization": f"Bearer {watsonx_token()}"})
        return out["choices"][0]["message"]["content"]
    if b == "ollama":
        payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": False,
                   "options": {"temperature": 0, "num_predict": max_tokens}}
        if as_json:
            payload["format"] = "json"
        return _post(f"{OLLAMA_URL}/api/chat", payload)["message"]["content"]
    raise RuntimeError("No LLM backend available")


def chat_json(system: str, user: str) -> dict:
    raw = chat(system, user).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])


# --- Fact checker: Granite Guardian -------------------------------------------------------
# After Granite writes the brief, every statement is checked by a second model:
#   * Granite Guardian, IBM's open risk-detection model, when it runs locally in Ollama
#     (ollama pull granite3-guardian:2b). It checks groundedness and our legal-advice risk.
#     Guardian is no longer hosted on watsonx (granite-guardian-3-8b was withdrawn 2026-09-30).
#   * Otherwise, on watsonx, Granite itself answers the same Yes/No question.
# The UI always names which one ran. Rules mode skips this; safety.unsupported_numbers still runs.

GROUNDEDNESS_DEFINITION = (
    "'Assistant' message is not grounded or faithful to the information provided in the 'Context'. "
    "This risk arises when the assistant's message includes claims, facts, or details that are not "
    "supported by or directly related to the provided context. An ungrounded answer may involve "
    "fabricating information, misinterpreting the context, or making unsupported extrapolations "
    "beyond what the context actually states.")


def _guardian_prompt(text: str, risk_definition: str, context: str) -> str:
    """Granite Guardian 3 prompt format (from the model card's chat template)."""
    if context.strip():
        intro = ("You are a safety agent trying to help determine if the assistant message poses a "
                 "potential harm based on the provided risk definition and the given context.")
        conversation = f"Context: {context}\nAssistant Message: {text}"
    else:
        intro = ("You are a safety agent trying to help determine whether the last assistant message "
                 "in the conversation is harmful according to the safety risk definition below.")
        conversation = f"Assistant Message: {text}"
    return (f"<|start_of_role|>user<|end_of_role|>{intro}\n\n<start_of_conversation>\n{conversation}\n"
            f"<end_of_conversation>\n\nOur safety risk definition is defined below:\n"
            f"<start_of_risk_definition>\n- {risk_definition}\n<end_of_risk_definition>\n\n"
            "Is the last assistant message harmful based on the risk definition? "
            "Your answer must be either 'Yes' or 'No'.<|end_of_text|>\n"
            "<|start_of_role|>assistant<|end_of_role|>")


def _yes_no(answer: str) -> bool | None:
    match = re.search(r"\b(yes|no)\b", answer, re.I)
    return None if match is None else match.group(1).lower() == "yes"


def _ollama_guardian() -> str | None:
    """Name of a pulled Granite Guardian model in Ollama, if any."""
    return next((m for m in _ollama_models() if m.startswith(OLLAMA_GUARDIAN_MODEL)), None)


def checker() -> str | None:
    """Which model checks facts, or None. Local Guardian works offline, so it runs even when no
    chat model is connected; only an explicit LLM_BACKEND=rules turns every model off."""
    if os.getenv("LLM_BACKEND") == "rules":
        return None
    guardian = _ollama_guardian()
    if guardian:
        return f"Granite Guardian ({guardian}, local)"
    if backend() == "watsonx":
        return f"Granite ({watsonx_model()}) on watsonx"
    return None


def guardian_check(user_text: str, risk_definition: str, evidence_text: str,
                   token: str = "") -> bool | None:
    """Does user_text show the risk? With evidence_text, the risk is checked against it
    (groundedness). True = risky, False = safe, None = no checker or it failed."""
    risk = GROUNDEDNESS_DEFINITION if evidence_text.strip() else risk_definition
    try:
        guardian = _ollama_guardian()
        if guardian:
            out = _post(f"{OLLAMA_URL}/api/generate",
                        {"model": guardian, "raw": True, "stream": False,
                         "prompt": _guardian_prompt(user_text, risk, evidence_text),
                         "options": {"temperature": 0, "num_predict": 5}}, timeout=60)
            return _yes_no(out.get("response", ""))
        if backend() == "watsonx":
            question = (f"Evidence:\n{evidence_text}\n\nStatement: {user_text}\n\n"
                        "Does the statement contain any claim, number, date or detail that the evidence "
                        "does not support?" if evidence_text.strip() else
                        f"Risk: {risk_definition}\n\nText: {user_text}\n\nDoes the text show this risk?")
            payload = {"model_id": watsonx_model(), "project_id": os.environ["WATSONX_PROJECT_ID"],
                       "messages": [{"role": "system", "content": "You are a strict checker. "
                                     "Answer with exactly one word: Yes or No."},
                                    {"role": "user", "content": question}],
                       "max_tokens": 5, "temperature": 0}
            headers = {"Authorization": f"Bearer {token or watsonx_token()}"}
            url = f"{WATSONX_URL}/ml/v1/text/chat?version={WATSONX_VERSION}"
            # The Lite plan allows only a few requests per second; a 429 used to leave a statement
            # "Not checked". Wait as asked (Retry-After) and try again, up to 3 times.
            for attempt in range(4):
                try:
                    out = _post(url, payload, headers=headers, timeout=30)
                    return _yes_no(out["choices"][0]["message"]["content"])
                except urllib.error.HTTPError as exc:
                    if exc.code not in (429, 503) or attempt == 3:
                        raise
                    retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                    time.sleep(min(float(retry_after), 8) if retry_after.isdigit() else 1.5 * 2 ** attempt)
    except Exception:
        return None
    return None


def _self_check() -> None:
    """python -m casebridge.llm : show what is connected and try one real call of each kind."""
    b = backend()
    print(f"Backend:      {b}")
    if b == "watsonx":
        offered = watsonx_models()
        print(f"Region:       {WATSONX_URL} ({len(offered)} models offered)")
        print(f"Chat model:   {watsonx_model()}")
        try:
            watsonx_token()
            print("IAM token:    OK")
        except Exception as exc:
            print(f"IAM token:    FAILED ({exc}). Check WATSONX_APIKEY.")
            return
    elif b == "ollama":
        print(f"Chat model:   {OLLAMA_MODEL} (pulled: {', '.join(_ollama_models()) or 'none'})")
    else:
        print("Chat model:   none (the brief is built offline with rules)")
    if b != "rules":
        try:
            print(f"Chat test:    {chat('Reply with one word.', 'Say OK.', max_tokens=5, as_json=False).strip()!r}")
        except Exception as exc:
            print(f"Chat test:    FAILED ({exc})")
            if isinstance(exc, urllib.error.HTTPError):   # IBM's body names the real cause
                print(f"              {exc.read().decode(errors='replace')[:600]}")
    print(f"Fact checker: {checker() or 'none (citations and numbers rules only)'}")
    if not checker():
        return
    evidence = "The other car rear-ended Maria at a red light at about 5:40 pm. Her bumper was dented."
    for statement, expected in [("Maria's car was hit from behind at a red light.", False),
                                ("The other car was going 45 mph.", True)]:
        verdict = guardian_check(statement, "", evidence)
        result = {True: "flagged", False: "supported", None: "no answer"}[verdict]
        status = "OK" if verdict is expected else "CHECK"
        print(f"  {status:5} {statement!r} -> {result}")


if __name__ == "__main__":
    _self_check()
