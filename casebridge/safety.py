"""Responsible-AI layer: citation enforcement, no-legal-advice guardrail, PII redaction."""
from __future__ import annotations

import re
import unicodedata

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
# Pattern-based, and tuned to fail closed: when unsure, hide it. Lawyers only see the real
# brief after the client accepts them.

_UP, _LO = "A-ZÀ-ÖØ-Þ", "a-zß-öø-ÿ"
_WORD = rf"[{_UP}][{_LO}'’-]+"
NAME = rf"({_WORD}(?:\s{_WORD}){{0,2}})"          # "Maria Lopez", "Rosa María Martínez"
_DATE = (r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
         r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
         r"\s+\d{1,2},?\s+\d{4})")

PII_PATTERNS = [  # (regex, replacement); order matters: specific before generic
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[EMAIL]"),
    (re.compile(rf"\b(DOB|D\.O\.B\.|[Dd]ate of birth|[Bb]orn(?: on)?|[Ff]echa de nacimiento|"
                rf"[Nn]acid[oa] el)\s*[:\-]?\s*{_DATE}"), r"\1 [REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}[.-]\d{4}\b"), "[PHONE]"),                       # 555-0142
    (re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"), "[VIN]"),
    (re.compile(r"\b\d[A-Z]{3}\d{3}\b"), "[PLATE]"),                      # California plate
    (re.compile(r"\b([Pp]late|[Pp]laca|[Ll]icense plate)(\s*(?:no\.?|number|#))?\s*[:#]?\s*[A-Z0-9-]{2,8}\b"),
     r"\1 [PLATE]"),
    (re.compile(r"\b[A-Z]{2}-\d{2}-\d{4,}\b"), "[REPORT #]"),
    (re.compile(r"\b((?i:policy|claim|member|account|MRN|medical record|driver'?s license|DL|report|"
                r"incident|reference|ref)(?:\s*(?i:no\.?|number|#))?)\s*[:#]?\s*(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,}\b"),
     r"\1 [ID]"),
    (re.compile(r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s"
                r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|Blvd|Boulevard|Pl|Place|"
                r"Ter|Terrace|Pkwy|Parkway|Hwy|Highway|Cir|Circle)\b\.?"
                r"(?:,?\s*(?:Apt|Apartment|Unit|Suite|Ste|#)\.?\s*\w+)?"), "[ADDRESS]"),
    (re.compile(r"\b(?:Apt|Apartment|Unit)\.?\s*#?\s*\d+\w?\b"), "[ADDRESS]"),
    (re.compile(r"\b(CA|California)\s+\d{5}(?:-\d{4})?\b"), r"\1 [ZIP]"),
]

CLIENT_NAME_PATTERNS = [
    rf"[Mm]y name is {NAME}", rf"\bI am {NAME}", rf"\bI'm {NAME}", rf"[Mm]e llamo {NAME}",
    rf"[Mm]i nombre es {NAME}", rf"(?:Patient|Claimant|Client|Customer|Name|Nombre):\s*{NAME}",
    rf"(?:Dear|Hi|Hello|Hola|Estimad[oa]) (?:Ms\.|Mr\.|Mrs\.|Sra\.|Sr\.)?\s*{NAME}", rf"Vehicle 1:[^.]*?driver {NAME}",
]
ROLE_PATTERNS = [
    ("[CLIENT]", CLIENT_NAME_PATTERNS),
    ("[OTHER PARTY]", [rf"driver,? (?:his|her) name is {NAME}", rf"Vehicle 2:[^.]*?driver {NAME}",
                       rf"our insured {NAME}", rf"(?:owner|defendant):?\s+{NAME}"]),
    ("[ADJUSTER]", [rf"[Aa]djuster:?\s+{NAME}", rf"{NAME},? (?:a |the |your )?(?:claims )?adjuster"]),
    ("[PERSON]", [rf"(?i:witness|manager|employee|officer|nurse|supervisor|clerk|cashier|gerente|"
                  rf"testigo)(?: named|:|,)? {NAME}",
                  rf"\b(?:Dr|Mr|Ms|Mrs|Sr|Sra|Srta)\.?\s+{NAME}", rf"(?:named|called|llamad[oa]) {NAME}", rf"[Tt]his is {NAME}",
                  rf"(?:Sincerely|Regards|Atentamente),?\s+{NAME}"]),
]
# Capitalized words the name patterns can swallow but which are never names.
NOT_NAMES = {"I", "The", "And", "But", "So", "My", "He", "She", "They", "We", "His", "Her", "Our",
             "Okay", "Yes", "No", "Not", "Very", "Really", "Just", "Sorry", "Scared", "Fine", "Here",
             "Driver", "Vehicle", "Police", "Officer", "Store", "Manager", "Insurance", "Doctor", "Dr"}


def _plain(s: str) -> str:
    """Strip accents, so "Martínez" also catches "Martinez"."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def find_names(texts: list[str]) -> dict[str, str]:
    """Map each detected person name, its parts and its unaccented spelling to a role placeholder."""
    joined = "\n".join(texts)
    names: dict[str, str] = {}
    for role, patterns in ROLE_PATTERNS:
        for p in patterns:
            for m in re.finditer(p, joined):
                words = [w for w in m.group(1).split() if w not in NOT_NAMES]
                # Stop at the first non-name word: "Kevin Holt Said" is rare, "Holt said" is lowercase.
                if words:
                    names.setdefault(" ".join(words), role)
    # Also catch first-name-only and surname-only mentions ("Maria said", "Ms. Lopez").
    for full, role in list(names.items()):
        for part in full.split():
            if len(part) > 2:
                names.setdefault(part, role)
    for name, role in list(names.items()):
        names.setdefault(_plain(name), role)
    return names


def redact(text: str, names: dict[str, str]) -> str:
    for rx, token in PII_PATTERNS:
        text = rx.sub(token, text)
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(rf"(?<![\w\[]){re.escape(name)}(?![\w\]])", names[name], text)
    return re.sub(r"(\[[A-Z #]+\])(?:\s+\1)+", r"\1", text)   # "[CLIENT] [CLIENT]" -> "[CLIENT]"


def find_leaks(data, names: dict[str, str]) -> list[str]:
    """Final check on anything a lawyer will see: list every known name or PII pattern still present."""
    blob = str(data)
    leaks = [n for n in names if re.search(rf"(?<![\w\[]){re.escape(n)}(?![\w\]])", blob)]
    for rx, _ in PII_PATTERNS:
        leaks += [m.group(0) for m in rx.finditer(blob) if "[" not in m.group(0)]
    return [x for i, x in enumerate(leaks) if x not in leaks[:i] and not any(x in y for y in leaks if y != x)]


# Fields that hold fixed values (enum keys, ISO dates, statute citations), not free text.
_FIXED = {"case_type", "client_side", "county", "engine", "languages", "date", "sources"}


def _redact_all(value, names, key=None):
    if key in _FIXED:
        return value
    if isinstance(value, str):
        return redact(value, names)
    if isinstance(value, list):
        return [_redact_all(v, names) for v in value]
    if isinstance(value, dict):
        return {k: _redact_all(v, names, k) for k, v in value.items()}
    return value


def redact_brief(brief: CaseBrief, names: dict[str, str]) -> dict:
    """The anonymized brief for the lawyer board. Every free-text field is redacted, and a final
    leak check blanks out any statement that still contains a known identifier (fail closed)."""
    d = _redact_all(brief.to_dict(), names)
    for section in ("timeline", "parties", "injuries", "damages"):
        for f in d[section]:
            if find_leaks(f, names):
                f["text"], f["when"] = "[Statement hidden to protect the client's identity]", None
    if find_leaks(d["summary"], names):
        d["summary"] = "[Summary hidden to protect the client's identity]"
    return d
