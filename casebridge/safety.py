"""Responsible-AI layer: citation enforcement, no-legal-advice guardrail, PII redaction."""
from __future__ import annotations

import re

from .models import CaseBrief, Fact

# The assistant organizes facts. It must never predict outcomes, value a case, or tell
# the person what legal action to take.
ADVICE_PATTERNS = [
    r"\byou (will|would|should|are going to) (win|lose)\b",
    r"\byou should (accept|sign|reject|settle|sue|file)\b",
    r"\b(your |the )?case is worth\b",
    r"\bguarantee",
    r"\b(strong|weak|winning|losing) case\b",
    r"\bsettle for \$",
    r"\bexpect(ed)? (a )?(settlement|payout|award) of\b",
]
ADVICE_RE = re.compile("|".join(ADVICE_PATTERNS), re.I)


def is_advice(text: str) -> bool:
    return bool(ADVICE_RE.search(text))


def enforce_citations(facts: list[Fact], valid_ids: set[str]) -> tuple[list[Fact], int]:
    """Drop any fact with no valid source. Uncited claims never reach a lawyer."""
    kept, dropped = [], 0
    for f in facts:
        f.sources = [s for s in f.sources if s in valid_ids]
        if f.sources:
            kept.append(f)
        else:
            dropped += 1
    return kept, dropped


def apply_guardrails(brief: CaseBrief, valid_ids: set[str]) -> CaseBrief:
    dropped_total, blocked = 0, 0
    for section in ("timeline", "parties", "injuries", "damages"):
        facts, dropped = enforce_citations(getattr(brief, section), valid_ids)
        dropped_total += dropped
        clean = []
        for f in facts:
            if is_advice(f.text):
                blocked += 1
            else:
                clean.append(f)
        setattr(brief, section, clean)
    if is_advice(brief.summary):
        blocked += 1
        brief.summary = re.sub(r"[^.]*(" + ADVICE_RE.pattern + r")[^.]*\.?", "", brief.summary,
                               flags=re.I).strip()
    if dropped_total:
        brief.warnings.append(f"Removed {dropped_total} AI-generated statement(s) with no source evidence.")
    if blocked:
        brief.warnings.append(f"Blocked {blocked} statement(s) that read like legal advice or outcome predictions.")
    return brief


# --- Redaction for the lawyer-side case board -------------------------------------------

PHONE_RE = re.compile(r"\(?\b\d{3}\)?[\s.-]?\d{3}-\d{4}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
DOB_RE = re.compile(r"\bDOB\s*[:\-]?\s*\d{1,2}/\d{1,2}/\d{2,4}", re.I)
PLATE_RE = re.compile(r"\b\d[A-Z]{3}\d{3}\b")              # California plate format
REPORT_NO_RE = re.compile(r"\b[A-Z]{2}-\d{2}-\d{4,}\b")
ADDRESS_RE = re.compile(r"\b\d{2,5}\s+[A-Z][a-z]+(\s[A-Z][a-z]+)*\s(St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Way|Ct)\b")

NAME = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
CLIENT_NAME_PATTERNS = [rf"[Mm]y name is {NAME}", rf"Patient:\s*{NAME}", rf"Dear (?:Ms\.|Mr\.|Mrs\.)\s*{NAME}",
                        rf"Vehicle 1:[^.]*?driver {NAME}"]
ROLE_PATTERNS = [
    ("[CLIENT]", CLIENT_NAME_PATTERNS),
    ("[OTHER PARTY]", [rf"driver,? (?:his|her) name is {NAME}", rf"Vehicle 2:[^.]*?driver {NAME}",
                       rf"our insured {NAME}"]),
    ("[ADJUSTER]", [rf"adjuster {NAME}"]),
    ("[PERSON]", [rf"witness(?: named)? {NAME}"]),
]


def find_names(texts: list[str]) -> dict[str, str]:
    """Map each detected person name (and its parts) to a role placeholder."""
    joined = "\n".join(texts)
    names: dict[str, str] = {}
    for role, patterns in ROLE_PATTERNS:
        for p in patterns:
            for m in re.finditer(p, joined):
                full = m.group(1).strip()
                names.setdefault(full, role)
    # Also catch surname-only mentions ("Ms. Lopez").
    for full, role in list(names.items()):
        parts = full.split()
        if len(parts) > 1:
            names.setdefault(parts[-1], role)
    return names


def redact(text: str, names: dict[str, str]) -> str:
    for rx, token in ((EMAIL_RE, "[EMAIL]"), (PHONE_RE, "[PHONE]"), (DOB_RE, "DOB [REDACTED]"),
                      (PLATE_RE, "[PLATE]"), (REPORT_NO_RE, "[REPORT #]"), (ADDRESS_RE, "[ADDRESS]")):
        text = rx.sub(token, text)
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", names[name], text)
    return text


def redact_brief(brief: CaseBrief, names: dict[str, str]) -> dict:
    d = brief.to_dict()
    d["summary"] = redact(d["summary"], names)
    for section in ("timeline", "parties", "injuries", "damages"):
        for f in d[section]:
            f["text"] = redact(f["text"], names)
    d["warnings"] = [redact(w, names) for w in d["warnings"]]
    return d
