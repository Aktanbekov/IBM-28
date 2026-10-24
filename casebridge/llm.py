"""Tiny LLM client: IBM watsonx.ai (Granite) or local Ollama (Granite). Standard library only.

Backend is picked by LLM_BACKEND = auto | watsonx | ollama | rules (default auto):
  auto -> watsonx if WATSONX_APIKEY is set, else Ollama if reachable, else rules-only.
"""
from __future__ import annotations

import json
import os
import urllib.request

WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_MODEL = os.getenv("WATSONX_MODEL", "ibm/granite-3-3-8b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "granite3.3")


def _post(url: str, payload: dict, headers: dict | None = None, form: bool = False, timeout=120) -> dict:
    if form:
        data = "&".join(f"{k}={v}" for k, v in payload.items()).encode()
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        ctype = "application/json"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1)
        return True
    except OSError:
        return False


def backend() -> str:
    choice = os.getenv("LLM_BACKEND", "auto")
    if choice != "auto":
        return choice
    if os.getenv("WATSONX_APIKEY") and os.getenv("WATSONX_PROJECT_ID"):
        return "watsonx"
    return "ollama" if _ollama_up() else "rules"


def chat(system: str, user: str) -> str:
    b = backend()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if b == "watsonx":
        token = _post("https://iam.cloud.ibm.com/identity/token",
                      {"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                       "apikey": os.environ["WATSONX_APIKEY"]}, form=True)["access_token"]
        out = _post(f"{WATSONX_URL}/ml/v1/text/chat?version=2024-10-08",
                    {"model_id": WATSONX_MODEL, "project_id": os.environ["WATSONX_PROJECT_ID"],
                     "messages": messages, "max_tokens": 2000, "temperature": 0},
                    headers={"Authorization": f"Bearer {token}"})
        return out["choices"][0]["message"]["content"]
    if b == "ollama":
        out = _post(f"{OLLAMA_URL}/api/chat", {"model": OLLAMA_MODEL, "messages": messages,
                                               "stream": False, "format": "json",
                                               "options": {"temperature": 0}})
        return out["message"]["content"]
    raise RuntimeError("No LLM backend available")


def chat_json(system: str, user: str) -> dict:
    raw = chat(system, user).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])
