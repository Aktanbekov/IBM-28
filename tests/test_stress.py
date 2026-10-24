"""Hostile or huge input must not freeze the app (catastrophic regex backtracking).

Bob's stress session found the email pattern took ~4-15 s on "word-" * 10000 with no "@".
"""
import time

import pytest

from casebridge import rules, safety
from casebridge.models import Evidence

HOSTILE = {
    "dash_run": "word-" * 10_000,
    "dot_run": "a.b" * 10_000,
    "run_then_at": "word-" * 10_000 + "@x.com",
    "digits": "1 " * 25_000,
    "alnum": "a1" * 25_000,
    "caps": "Maria Lopez " * 4_000,
    "ignore": "ignore " * 7_000,
    "emoji": "😀é " * 15_000,
    "address_words": "12345 " + "Oak " * 10_000,
}
NAMES = {"Maria Lopez": "[CLIENT]", "Maria": "[CLIENT]", "Lopez": "[CLIENT]"}
CALLS = {
    "redact": lambda t: safety.redact(t, NAMES),
    "find_names": lambda t: safety.find_names([t]),
    "has_injection": safety.has_injection,
    "build_brief": lambda t: rules.build_brief([Evidence(id="E1", kind="note", title="n", text=t)]),
}


@pytest.mark.parametrize("call", CALLS)
@pytest.mark.parametrize("name", HOSTILE)
def test_hostile_input_finishes_fast(name, call):
    start = time.perf_counter()
    CALLS[call](HOSTILE[name])
    assert time.perf_counter() - start < 2, f"{call} took too long on {name}"


def test_email_still_redacted_after_the_speed_fix():
    for text in ("rosa@mail.example.com", "rosa @ mail.example.com", "rosa(at)mail.example.com",
                 "write to contact-rosa@mail.example.com today"):
        assert "[EMAIL]" in safety.redact(text, {}), text
