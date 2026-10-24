"""Case-brief agent: evidence -> cited, guard-railed brief.

Pipeline:
  1. Rules pass (always): case type, side, county, deadlines, missing evidence.
  2. LLM pass (if available): Granite rewrites the narrative sections with [E#] citations.
  3. Guardrails: drop uncited facts, block legal-advice language.
Deadlines and the missing-evidence checklist stay deterministic on purpose.
"""
from __future__ import annotations

from . import llm, rules
from .models import CaseBrief, Evidence, Fact, PRACTICE_AREAS
from .safety import apply_guardrails

SYSTEM_PROMPT = """You are an intake assistant that prepares a case brief for a lawyer.
You ORGANIZE facts. You never give legal advice, never predict outcomes, never estimate what a case is worth.
Every fact MUST cite one or more evidence ids like "E2" taken from the evidence list. If something is not in
the evidence, leave it out. Write facts as short, neutral, third-person sentences.
Return ONLY JSON with this shape:
{"case_type": one of %s,
 "client_side": "plaintiff" or "defense",
 "summary": "3-4 neutral sentences",
 "timeline": [{"when": "...", "text": "...", "sources": ["E1"]}],
 "parties":  [{"text": "...", "sources": ["E4"]}],
 "injuries": [{"text": "...", "sources": ["E6"]}],
 "damages":  [{"text": "...", "sources": ["E1"]}],
 "languages": ["languages the client speaks, if stated"]}""" % list(PRACTICE_AREAS)


def evidence_block(evidence: list[Evidence]) -> str:
    return "\n\n".join(f"[{e.id}] ({e.kind}) {e.title}\n{e.text}" for e in evidence)


def _facts(items) -> list[Fact]:
    return [Fact(text=str(i.get("text", "")), sources=list(i.get("sources", [])), when=i.get("when"))
            for i in items or [] if isinstance(i, dict)]


def build(evidence: list[Evidence], use_llm: bool = True) -> CaseBrief:
    brief = rules.build_brief(evidence)
    if any(e.kind == "voice" and "spanish" in e.title.lower() for e in evidence):
        brief.languages = ["Spanish", "English"]

    backend = llm.backend() if use_llm else "rules"
    if backend != "rules":
        try:
            data = llm.chat_json(SYSTEM_PROMPT, evidence_block(evidence))
            brief.summary = data.get("summary") or brief.summary
            for section in ("timeline", "parties", "injuries", "damages"):
                facts = _facts(data.get(section))
                if facts:
                    setattr(brief, section, facts)
            if data.get("case_type") in PRACTICE_AREAS:
                brief.case_type = data["case_type"]
                brief.missing_evidence = rules.missing_evidence(evidence, brief.case_type)
                brief.deadlines = rules.deadlines(evidence, brief.case_type)
            if data.get("client_side") in ("plaintiff", "defense"):
                brief.client_side = data["client_side"]
            if data.get("languages"):
                brief.languages = sorted(set(brief.languages) | set(data["languages"]))
            brief.engine = backend
        except Exception as exc:  # never let the demo die on a model hiccup
            brief.warnings.append(f"LLM unavailable ({type(exc).__name__}); used rule-based extraction.")

    return apply_guardrails(brief, {e.id for e in evidence})
