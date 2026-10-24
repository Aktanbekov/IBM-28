"""Responsible-AI layer: citation enforcement, no-legal-advice guardrail, PII redaction."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import CaseBrief, Evidence, Fact

# The assistant organizes facts. It must never predict outcomes, value a case, or tell
# the person what legal action to take.
ADVICE_PATTERNS = [
    r"\byou (will|would|should|are going to) (win|lose)\b",
    r"\byou should (accept|sign|reject|settle|sue|file)\b",
    r"\bshould(n't| not)? you (accept|sign|reject|settle|sue|file)\b",
    r"\b(case|claim) (is|could be|may be|might be) worth\s*(\$|\d|a lot|more|up to|around|about|at least)",
    # Spanish: "debería firmar", "su caso vale", "ganará el caso"
    r"\bdeber[ií]a(s|n)? (aceptar|firmar|rechazar|demandar|llegar a un acuerdo|conformarse)\b",
    r"\b(su|tu) (caso|reclamo) vale\b",
    r"\b(usted )?(ganar[áa]|perder[áa]|vas? a ganar|vas? a perder)\b",
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


# --- Prompt-injection defense ------------------------------------------------------------
# Evidence is written by other people: an insurer's letter, a scanned form, a text message.
# Any of it can hide instructions aimed at our AI ("ignore your rules", "say the case is worth
# $1M"). We never obey evidence. We flag it for the client and lawyer, and when evidence goes
# to Granite it is fenced off as data (see wrap_evidence and brief.SYSTEM_PROMPT).

# ---------------------------------------------------------------------------
# Sub-expressions reused inside INJECTION_PATTERNS for readability.
# ---------------------------------------------------------------------------
_CANCEL_VERB   = r"(?:ignore|disregard|forget|override)"
_SCOPE_WORD    = r"(?:previous|prior|above|earlier|all|your|these)"
_INSTR_NOUN    = r"(?:instructions?|rules?|prompts?|guidelines?|directions?)"
_AI_NOUN       = r"(?:AI|assistant|chatbot|language model|LLM|Granite)"
_AI_ROLE       = r"(?:AI|assistant|chatbot|bot|model|lawyer|attorney|legal advisor|\w+ mode|DAN)"
_LEGAL_ROLE    = r"(?:AI|assistant|lawyer|attorney|legal advisor)"
_OUTPUT_VERB   = r"(?:must|should|will|do not|don't|ignore|say|write|tell|output|respond|answer)"
_OUTCOME_CLAIM = r"(?:case is worth|will win|should (?:settle|sign|accept))"

INJECTION_PATTERNS = [
    # "ignore/disregard/forget/override … previous … instructions"
    rf"\b{_CANCEL_VERB}\b.{{0,40}}\b{_SCOPE_WORD}\b.{{0,20}}\b{_INSTR_NOUN}\b",
    # "new system prompt", "updated instructions"
    r"\b(new|updated|real) (instructions?|system prompt)\b",
    # bare "system prompt" anywhere in a document
    r"\bsystem prompt\b",
    # "you are now a lawyer / DAN / …"
    rf"\byou are (now|no longer) (an? |the |in )?{_AI_ROLE}\b",
    # "act as my legal advisor", "behave as an AI"
    rf"\b(act|behave) as (an?|the|my) {_LEGAL_ROLE}\b",
    # "pretend to be / you are / you're"
    r"\bpretend (to be|you are|you're)\b",
    # jailbreak keywords
    r"\bjailbreak|\bdeveloper mode\b|\bDAN mode\b",
    # "AI: say …", "Granite, please output …"  — text addressed directly to the model
    rf"\b{_AI_NOUN}\s*[:,]?\s*(?:please\s+)?{_OUTPUT_VERB}\b",
    # "say / write / output … case is worth / will win"
    rf"\b(say|write|state|tell the (?:user|client|lawyer)|output|respond with)\b.{{0,40}}\b{_OUTCOME_CLAIM}",
    # Chat-template tokens and role tags that have no business in a letter.
    r"<\|?(system|assistant|user|im_start|im_end)\|?>|\[/?INST\]|^\s*(system|assistant)\s*:",
    # Spanish equivalents: "ignora las instrucciones", "olvida tus reglas"
    r"\b(ignora|olvida|omite)\b.{0,40}\b(instrucciones|reglas)\b",
]
INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.I | re.M)


def injection_flags(evidence: list[Evidence]) -> list[str]:
    """Ids of evidence items that contain text trying to instruct an AI."""
    return [e.id for e in evidence if INJECTION_RE.search(e.text)]


def injection_warnings(evidence: list[Evidence]) -> list[str]:
    """One plain-language warning per flagged evidence item, for the brief's warnings list."""
    return [f"[{eid}] contains text that tries to give instructions to an AI. CaseBridge ignored "
            "those instructions and treated the item as evidence only. A lawyer may want to see it."
            for eid in injection_flags(evidence)]


def wrap_evidence(evidence_id: str, kind: str, title: str, text: str) -> str:
    """Fence one evidence item for the LLM so it reads as quoted data, never as instructions.

    Any tag that could close the fence early is neutralized first, so a document can't
    "break out" by writing </evidence> itself.
    """
    clean = re.sub(r"</?\s*evidence[^>]*>", "[tag removed]", text, flags=re.I)
    flag = ' flagged="possible-instructions"' if INJECTION_RE.search(text) else ""
    return f'<evidence id="{evidence_id}" kind="{kind}"{flag}>\n{title}\n{clean}\n</evidence>'


# --- Redaction for the lawyer-side case board -------------------------------------------
# Pattern-based, and tuned to fail closed: when unsure, hide it. Lawyers only see the real
# brief after the client accepts them.

# ---------------------------------------------------------------------------
# Building blocks for name and date patterns.
# _UP / _LO are Unicode-aware upper/lowercase ranges used in every name regex.
# ---------------------------------------------------------------------------
_UP, _LO = "A-ZÀ-ÖØ-Þ", "a-zß-öø-ÿ"

# One capitalised word, optionally containing an internal apostrophe or hyphen.
# Covers: "Lopez", "O'Brien", "Smith-Jones", "García".
_WORD = rf"[{_UP}](?:[''][{_UP}])?[{_LO}]+(?:[-''][{_UP}]?[{_LO}]+)*"

# A full name: one to three _WORD tokens separated by spaces.
# Captures: "Maria", "Maria Lopez", "Rosa María Martínez".
NAME = rf"({_WORD}(?:\s{_WORD}){{0,2}})"

# A date in any of three common formats:
#   numeric:   01/15/2026  or  2026-01-15
#   long form: January 15, 2026
_DATE = (r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"   # numeric short:  MM/DD/YY(YY)
         r"|\d{4}-\d{2}-\d{2}"                   # ISO:            YYYY-MM-DD
         r"|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
         r"\s+\d{1,2},?\s+\d{4})")               # long form:      Month D, YYYY

# ---------------------------------------------------------------------------
# Reusable sub-expressions for PII_PATTERNS.
# ---------------------------------------------------------------------------

# Digit word in English or Spanish (used for spelled-out phone numbers).
_DIGIT_WORD = (r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine"
               r"|cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)")

# Street-type suffixes recognised in address patterns.
_STREET_SUFFIX = (r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Way"
                  r"|Ct|Court|Blvd|Boulevard|Pl|Place|Ter|Terrace"
                  r"|Pkwy|Parkway|Hwy|Highway|Cir|Circle)")

# Keywords that precede a policy / claim / record number.
_ID_KEYWORD = (r"(?i:policy|claim|member|account|MRN|medical record"
               r"|driver'?s license|DL|report|incident|reference|ref)")

PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # order matters: most specific patterns first so they win over generic ones

    # GPS coordinates: "37.3230, -121.9480"
    (re.compile(r"-?\b\d{1,3}\.\d{3,},\s*-?\d{1,3}\.\d{3,}\b"), "[LOCATION]"),

    # Email address
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[EMAIL]"),

    # Date of birth preceded by a label: "DOB: 03/08/1984", "born on January 3, 2000"
    (re.compile(rf"\b(DOB|D\.O\.B\.|[Dd]ate of birth|[Bb]orn(?: on)?|[Ff]echa de nacimiento|"
                rf"[Nn]acid[oa] el)\s*[:\-]?\s*{_DATE}"), r"\1 [REDACTED]"),

    # SSN: 3-2-4 digit groups separated by dashes
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),

    # Full 10-digit phone (optional +1 / country code), various separators
    (re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[PHONE]"),

    # 7-digit fragment: "555-0142", "555 - 0142"
    (re.compile(r"\b\d{3}\s*[.-]\s*\d{4}\b"), "[PHONE]"),

    # Phone spelled out in words: "five five five zero one four two" (≥7 digit-words)
    (re.compile(rf"\b(?:{_DIGIT_WORD}[\s,-]+){{6,}}{_DIGIT_WORD}\b", re.I), "[PHONE]"),

    # VIN: 17-char alphanumeric excluding I, O, Q
    (re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"), "[VIN]"),

    # California plate: digit + 3 letters + 3 digits  e.g. "7ABC123"
    (re.compile(r"\b\d[A-Z]{3}\d{3}\b"), "[PLATE]"),

    # Plate preceded by a label: "Plate: 7ABC123", "License plate no. XYZ"
    (re.compile(r"\b([Pp]late|[Pp]laca|[Ll]icense plate)(\s*(?:no\.?|number|#))?\s*[:#]?\s*[A-Z0-9-]{2,8}\b"),
     r"\1 [PLATE]"),

    # Police / collision report number: two letters, dash, two digits, dash, 4+ digits
    (re.compile(r"\b[A-Z]{2}-\d{2}-\d{4,}\b"), "[REPORT #]"),

    # Policy / claim / MRN / DL number preceded by a keyword label
    (re.compile(rf"\b({_ID_KEYWORD}(?:\s*(?i:no\.?|number|#))?)\s*[:#]?\s*(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{{3,}}\b"),
     r"\1 [ID]"),

    # Street address: house number + optional direction + street name + suffix + optional unit
    (re.compile(rf"\b\d{{1,6}}\s+(?:[NSEW]\.?\s+)?[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s{_STREET_SUFFIX}\b\.?"
                r"(?:,?\s*(?:Apt|Apartment|Unit|Suite|Ste|#)\.?\s*\w+)?"), "[ADDRESS]"),

    # Unit-only: "Apt 4", "Unit #12B"
    (re.compile(r"\b(?:Apt|Apartment|Unit)\.?\s*#?\s*\d+\w?\b"), "[ADDRESS]"),

    # California ZIP code, optionally with +4 extension
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
# Speech-to-text can drop capitals: "my name is rosa martinez". Only unambiguous cues here.
# Captures up to three lowercase name tokens after the intro phrase.
LOWER_INTRO_RE = re.compile(
    r"(?i:my name is|me llamo|mi nombre es|patient:|nombre:)\s+"
    rf"([{_LO}''-]+"           # first name token (lowercase, may contain ' or -)
    rf"(?:\s[{_LO}''-]+){{0,2}})"  # up to two more tokens
)
INTRO_STOP = {"and", "y", "i", "im", "my", "from", "de", "del", "la", "el", "is", "es", "but", "pero",
              "so", "and", "the", "a", "was", "fui", "estaba", "soy", "am", "me", "mi", "tengo"}
# Names that are also everyday words: replaced only when capitalized, to keep the brief readable.
COMMON_WORDS = {"will", "mark", "grant", "bill", "may", "june", "april", "rose", "frank", "art", "hope",
                "joy", "faith", "pat", "sue", "dawn", "rob", "ray", "guy", "jack", "chase", "page",
                "lane", "wade", "ford", "cole", "shaw", "rich", "drew", "gay", "penny", "summer",
                "sky", "river", "dean", "nick", "victor", "angel"}
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
    for m in LOWER_INTRO_RE.finditer(joined):
        words = []
        for w in m.group(1).split():
            if w in INTRO_STOP:
                break
            words.append(w)
        if words:
            names.setdefault(" ".join(words).title(), "[CLIENT]")
    # Also catch first-name-only and surname-only mentions ("Maria said", "Ms. Lopez").
    for full, role in list(names.items()):
        for part in full.split():
            if len(part) > 2:
                names.setdefault(part, role)
    for name, role in list(names.items()):
        names.setdefault(_plain(name), role)
    return names


def _name_re(name: str) -> re.Pattern:
    """Whole-name match, any case ("rosa", "ROSA"), except names that are everyday words."""
    flags = 0 if name.lower() in COMMON_WORDS else re.I
    return re.compile(rf"(?<![\w\[]){re.escape(name)}(?![\w\]])", flags)


def redact(text: str, names: dict[str, str]) -> str:
    for rx, token in PII_PATTERNS:
        text = rx.sub(token, text)
    for name in sorted(names, key=len, reverse=True):
        text = _name_re(name).sub(names[name], text)
    return re.sub(r"(\[[A-Z #]+\])(?:\s+\1)+", r"\1", text)   # "[CLIENT] [CLIENT]" -> "[CLIENT]"


def find_leaks(data: Any, names: dict[str, str]) -> list[str]:
    """Final check on anything a lawyer will see: list every known name or PII pattern still present."""
    blob = str(data)
    leaks = [n for n in names if _name_re(n).search(blob)]
    for rx, _ in PII_PATTERNS:
        # Skip matches that are already inside a placeholder (e.g. "[PHONE]").
        leaks += [m.group(0) for m in rx.finditer(blob) if "[" not in m.group(0)]
    # Deduplicate and drop sub-strings already covered by a longer match.
    return [x for i, x in enumerate(leaks) if x not in leaks[:i] and not any(x in y for y in leaks if y != x)]


HIDDEN_STATEMENT = "[Statement hidden to protect the client's identity]"

# Fields that hold fixed values (enum keys, ISO dates, statute citations), not free text.
_FIXED = {"case_type", "client_side", "county", "engine", "languages", "date", "sources"}


def _redact_all(value: Any, names: dict[str, str], key: str | None = None) -> Any:
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
                f["text"], f["when"] = HIDDEN_STATEMENT, None
    if find_leaks(d["summary"], names):
        d["summary"] = "[Summary hidden to protect the client's identity]"
    return d


# --- Privacy receipt, client review and the posting gate -----------------------------------
# Privacy the client can see: before anything is posted, the client is shown exactly what was
# hidden, can hide any extra line themselves, and the post is refused if a leak remains.

PLACEHOLDER_LABELS = {
    "[CLIENT]": "your name", "[OTHER PARTY]": "the other party's name",
    "[ADJUSTER]": "insurance adjusters' names", "[PERSON]": "other people's names",
    "[PHONE]": "phone numbers", "[EMAIL]": "email addresses", "[ADDRESS]": "street addresses",
    "[ZIP]": "ZIP codes", "[LOCATION]": "GPS locations", "[PLATE]": "licence plates",
    "[REPORT #]": "police report numbers", "[ID]": "claim, policy and record numbers",
    "[SSN]": "Social Security numbers", "[VIN]": "vehicle ID numbers", "[REDACTED]": "dates of birth",
}


def privacy_summary(red: dict) -> dict[str, int]:
    """Count what redaction hid in an anonymized brief, in plain words:
    {"your name": 4, "phone numbers": 2, ...}. Shown to the client as a privacy receipt."""
    blob = str(red)
    counts = {label: blob.count(token) for token, label in PLACEHOLDER_LABELS.items()}
    counts["whole statements (failed the leak check)"] = blob.count(HIDDEN_STATEMENT)
    counts["statements you chose to hide"] = red.get("client_hidden", 0)
    return {label: n for label, n in counts.items() if n}


def fact_key(section: str, index: int) -> str:
    """Stable id for one statement in a brief, used by the client's "hide this line" choice."""
    return f"{section}:{index}"


def hide_facts(red: dict, hidden: set[str]) -> dict:
    """Remove the statements the client chose to hide (keys from fact_key) before posting.

    The client stays in control: anything they don't want a stranger to read, even if it
    contains no personal detail, never reaches the lawyer board.
    """
    removed = 0
    for section in ("timeline", "parties", "injuries", "damages"):
        kept = []
        for i, f in enumerate(red[section]):
            if fact_key(section, i) in hidden:
                removed += 1
            else:
                kept.append(f)
        red[section] = kept
    red["client_hidden"] = red.get("client_hidden", 0) + removed
    return red


def posting_blockers(red: dict, names: dict[str, str]) -> list[str]:
    """The gate before the lawyer board: any identifier still present blocks the post.
    redact_brief already fails closed, so this should always be empty. It is the second lock."""
    return find_leaks(red, names)

