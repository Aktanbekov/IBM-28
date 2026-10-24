"""Numbers for the app to show what CaseBridge did with a case: facts found and cited, advice
blocked, details hidden, hidden instructions caught, and how complete the evidence is.

Everything here counts the engine's own work or the evidence. Nothing scores the case: no
strength, no odds, no value (AGENTS.md rule 4).
"""
from __future__ import annotations

import re

from . import rules, safety
from .models import CaseBrief, Evidence

FACT_SECTIONS = ("timeline", "parties", "injuries", "damages")


def _from_warning(warnings: list[str], pattern: str) -> int:
    """Read a count back out of a guardrail warning such as "Blocked 2 statement(s) ..."."""
    for w in warnings:
        if m := re.match(pattern, w):
            return int(m.group(1))
    return 0


def brief_stats(evidence: list[Evidence], brief: CaseBrief, red: dict | None = None) -> dict:
    """Scoreboard for one built brief. Pass the anonymized brief (safety.redact_brief) as red
    to include how many personal details are hidden from lawyers."""
    facts = [f for section in FACT_SECTIONS for f in getattr(brief, section)]
    covered, total = rules.readiness(evidence, brief.case_type)
    return {
        "evidence": len(evidence),
        "facts": len(facts),
        "facts_cited": sum(1 for f in facts if f.sources),
        # Statements that read like advice and are still in the brief. The guardrail keeps this at 0.
        "advice_given": sum(1 for t in [brief.summary, *(f.text for f in facts)] if safety.is_advice(t)),
        "advice_blocked": _from_warning(brief.warnings, r"Blocked (\d+) statement"),
        "uncited_removed": _from_warning(brief.warnings, r"Removed (\d+) AI-generated"),
        "hidden_instructions": len(safety.injection_flags(evidence)),
        "details_hidden": sum(n for label, n in safety.privacy_summary(red).items()
                              if label != "statements you chose to hide") if red else 0,
        "deadlines": len(brief.deadlines),
        "alerts": len(brief.alerts),
        "contradictions": len(brief.contradictions),
        "evidence_covered": covered,
        "evidence_checklist": total,
        "readiness_pct": round(100 * covered / total) if total else 100,
    }


def redaction_swaps(text: str, names: dict[str, str]) -> list[tuple[str, str]]:
    """Every (original, placeholder) swap redaction makes in one text, in order, for the app's
    client-view-to-lawyer-view animation. The originals are the client's details: show them only
    to the client, never on the lawyer side."""
    swaps: list[tuple[str, str]] = []
    safety.redact(text, names, swaps)
    return swaps
