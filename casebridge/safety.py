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

INJECTION_PATTERNS = [
    # Attempts to cancel or replace the model's instructions.
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your|these)\b"
    r".{0,20}\b(instructions?|rules?|prompts?|guidelines?|directions?)\b",
    r"\b(new|updated|real) (instructions?|system prompt)\b",
    r"\bsystem prompt\b",
    # Role-play and jailbreak phrasing.
    r"\byou are (now|no longer) (an? |the |in )?(AI|assistant|chatbot|bot|model|lawyer|attorney|"
    r"legal advisor|\w+ mode|DAN)\b",
    r"\b(act|behave) as (an?|the|my|your) (AI|assistant|lawyer|attorney|legal advisor)\b",
    r"\bpretend (to be|you are|you're)\b",
    r"\bjailbreak|\bdeveloper mode\b|\bDAN mode\b",
    # Text addressed to an AI rather than to a person.
    r"\b(AI|assistant|chatbot|language model|LLM|Granite)\s*[:,]?\s*(please\s+)?"
    r"(must|should|will|do not|don't|ignore|say|write|tell|output|respond|answer)\b",
    r"\b(say|write|state|tell the (user|client|lawyer)|output|respond with)\b.{0,40}"
    r"\b(case is worth|will win|should (settle|sign|accept))",
    # Chat-template tokens and role tags that have no business in a letter.
    r"<\|?(system|assistant|user|im_start|im_end)\|?>|\[\s*/?\s*INST\s*\]|^\s*(system|assistant)\s*:",
    # Spanish equivalents.
    r"\b(ignora|olvida|omite)\b.{0,40}\b(instrucciones|reglas)\b",
    # Vietnamese equivalents, written without accents because _scan_text strips them first:
    # "bỏ qua ... hướng dẫn" (skip the instructions), "đóng vai luật sư" (play the lawyer).
    r"\b(bo qua|phot lo|quen)\b.{0,40}\b(huong dan|chi dan|chi thi|quy tac)\b",
    r"\b(dong vai|gia vo la|gia lam)\b.{0,40}\b(luat su|tro ly|AI|chatbot)\b",
]
# re.S lets ".{0,40}" cross a line break, so "ignore\nall previous instructions" still matches.
INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.I | re.M | re.S)

# Invisible characters that can be slipped inside a word ("i​gnore") to dodge the regex.
ZERO_WIDTH_RE = re.compile("[­᠎​-‏⁠-⁤﻿]")

# Cyrillic and Greek letters that look identical to Latin ones ("іgnore" with a Cyrillic і).
# NFKD doesn't touch these, so they are mapped by hand. Only used for scanning, never shown.
CONFUSABLES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
    "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ї": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
    "ԛ": "q", "ԝ": "w", "ɡ": "g",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "У": "Y", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u",
    "χ": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "đ": "d", "Đ": "D",   # Vietnamese d-bar has no NFKD decomposition
})


def _scan_text(text: str) -> str:
    """The text as the injection check sees it: invisible characters removed, look-alike letters
    turned into Latin ones, and accents dropped (NFKD), so "Bỏ qua" reads as "Bo qua".

    Only the check uses this. The evidence the client and lawyer see is never altered.
    """
    text = ZERO_WIDTH_RE.sub("", text).translate(CONFUSABLES)
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def has_injection(text: str) -> bool:
    """True if the text looks like it is trying to give instructions to an AI."""
    return bool(INJECTION_RE.search(_scan_text(text)))


def injection_flags(evidence) -> list[str]:
    """Ids of evidence items that contain text trying to instruct an AI."""
    return [e.id for e in evidence if has_injection(e.text)]


def injection_warnings(evidence) -> list[str]:
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
    flag = ' flagged="possible-instructions"' if has_injection(text) else ""
    return f'<evidence id="{evidence_id}" kind="{kind}"{flag}>\n{title}\n{clean}\n</evidence>'


# --- Redaction for the lawyer-side case board -------------------------------------------
# Pattern-based, and tuned to fail closed: when unsure, hide it. Lawyers only see the real
# brief after the client accepts them.

_UP, _LO = "A-ZÀ-ÖØ-Þ", "a-zß-öø-ÿ"
_WORD = rf"[{_UP}](?:['’][{_UP}])?[{_LO}]+(?:[-'’][{_UP}]?[{_LO}]+)*"   # also O'Brien, Smith-Jones
NAME = rf"({_WORD}(?:\s{_WORD}){{0,2}})"          # "Maria Lopez", "Rosa María Martínez"
_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_DATE = (r"(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|"           # 03/08/1984, 08.03.1984
         rf"{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}|{_MONTHS},?\s+\d{{4}}|"         # March 8, 1984 / March 1984
         r"(?:19|20)\d{2})")                                                   # 1984 (after a birth label)
_NUM_WORDS = (r"zero|oh|one|two|three|four|five|six|seven|eight|nine|"
              r"cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve")
_GPS_NUM = r"-?\d{1,3}\.\d{3,}"
_DMS = r"\d{1,3}°\s*\d{1,2}[′']\s*\d{1,2}(?:\.\d+)?[″\"]?\s*"                 # 37°19′22″

PII_PATTERNS = [  # (regex, replacement); order matters: specific before generic
    # GPS: decimal "37.3230, -121.9480" (comma or semicolon) and degrees "37°19′22″N 121°57′17″W".
    (re.compile(rf"(?<![\d.]){_GPS_NUM}\s*[,;]\s*{_GPS_NUM}\b"), "[LOCATION]"),
    (re.compile(rf"{_DMS}[NS]\s*,?\s*{_DMS}[EW]\b"), "[LOCATION]"),
    # Email, including "name @ host", the full-width ＠ and "name(at)host".
    (re.compile(r"\b[\w.+-]+\s*(?:@|＠|\(at\)|\[at\])\s*[\w-]+(?:\.[\w-]+)+\b", re.I), "[EMAIL]"),
    # Dates of birth after a label, in many formats, English and Spanish.
    (re.compile(rf"\b((?i:DOB|D\.O\.B\.?|date of birth|born(?: on| in)?|fecha de nacimiento|"
                rf"nacid[oa] (?:el|en)))\s*[:\-]?\s*{_DATE}\b"), r"\1 [REDACTED]"),
    # SSN with dashes, spaces, dots or nothing between the groups.
    (re.compile(r"\b\d{3}([\s.-]?)\d{2}\1\d{4}\b"), "[SSN]"),
    (re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}\s*[.-]\s*\d{4}\b"), "[PHONE]"),                 # 555-0142, 555 - 0142
    (re.compile(rf"\b(?:(?:{_NUM_WORDS})[\s,-]+){{6,}}(?:{_NUM_WORDS})\b", re.I), "[PHONE]"),  # spelled out
    # Digits and number words mixed in one token: "four0eight".
    (re.compile(rf"\b(?=\w*\d)(?=\w*[a-z])(?:(?:{_NUM_WORDS})|\d)+\b", re.I), "[PHONE]"),
    # VIN: 17 characters with both letters and digits, any case.
    (re.compile(r"\b(?=[A-Za-z0-9]{17}\b)(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])"
                r"[A-HJ-NPR-Za-hj-npr-z0-9]{17}\b"), "[VIN]"),
    (re.compile(r"\b\d[A-Za-z]{3}\d{3}\b"), "[PLATE]"),                   # California plate, any case
    (re.compile(r"\b((?i:plate|placa|license plate))(\s*(?i:no\.?|number|#))?\s*[:#]?\s*[A-Za-z0-9-]{2,8}\b"),
     r"\1 [PLATE]"),
    (re.compile(r"\b[A-Za-z]{2}-\d{2}-\d{4,}\b"), "[REPORT #]"),
    (re.compile(r"\b((?i:policy|claim|member|account|MRN|medical record|driver'?s license|DL|report|"
                r"incident|reference|ref)(?:\s*(?i:no\.?|number|#))?)\s*[:#]?\s*"
                r"(?=[A-Za-z0-9-]*\d)[A-Za-z0-9][A-Za-z0-9-]{3,}\b"), r"\1 [ID]"),
    # Prefixed IDs written on their own, lowercase too: "hc-55190".
    (re.compile(r"\b[A-Za-z]{2,3}-\d{4,}\b"), "[ID]"),
    (re.compile(r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s"
                r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|Blvd|Boulevard|Pl|Place|"
                r"Ter|Terrace|Pkwy|Parkway|Hwy|Highway|Cir|Circle)\b\.?"
                r"(?:,?\s*(?:Apt|Apartment|Unit|Suite|Ste|#)\.?\s*\w+)?"), "[ADDRESS]"),
    # House number + street name with no suffix, before a city: "4120 Peralta, Fremont". Not years.
    (re.compile(r"\b(?!(?:19|20)\d{2}\b)\d{2,6}\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?(?=,\s*[A-Z][a-z]+)"),
     "[ADDRESS]"),
    (re.compile(r"\bP\.?\s?O\.?\s*Box\s+\d+\b", re.I), "[ADDRESS]"),
    # A bare house number right before a unit: "4120, apartment 12".
    (re.compile(r"\b\d{2,6}(?=,?\s*(?i:apt|apartment|unit|suite|#))"), "[ADDRESS]"),
    (re.compile(r"\b(?:Apt|Apartment|Unit)\.?\s*#?\s*\d+\w?\b", re.I), "[ADDRESS]"),
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
    ("[ADJUSTER]", [rf"[Aa]djuster:?\s+{NAME}", rf"{NAME}, (?:a |the |your )?(?:claims )?adjuster"]),
    ("[PERSON]", [rf"(?i:witness|manager|employee|officer|nurse|supervisor|clerk|cashier|gerente|"
                  rf"testigo)(?: named|:|,)? {NAME}",
                  rf"\b(?:Dr|Mr|Ms|Mrs|Sr|Sra|Srta)\.?\s+{NAME}", rf"(?:named|called|llamad[oa]) {NAME}", rf"[Tt]his is {NAME}",
                  rf"(?:Sincerely|Regards|Atentamente),?\s+{NAME}"]),
]
# Speech-to-text can drop capitals: "my name is rosa martinez". Only unambiguous cues here.
LOWER_INTRO_RE = re.compile(r"(?i:my name is|me llamo|mi nombre es|patient:|nombre:)\s+"
                            rf"([{_LO}'’-]+(?:\s[{_LO}'’-]+){{0,2}})")
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
             "Driver", "Vehicle", "Police", "Officer", "Store", "Manager", "Insurance", "Doctor", "Dr",
             "Contact", "Call", "Please", "Hi", "Hello", "Dear", "Thanks", "Thank", "Regards"}


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
    # Nicknames of first names ("Rosie" for Rosa). Over-hiding is the safe direction here.
    for full, role in list(names.items()):
        if " " in full:
            for nick in _nicknames(_plain(full.split()[0])):
                if nick.lower() not in COMMON_WORDS:
                    names.setdefault(nick, role)
    return names


# Scans and photos of documents swap letters for look-alike digits: "Mar1a L0pez".
LOOKALIKES = {"o": "o0", "i": "i1l", "l": "l1i", "a": "a4@", "e": "e3", "s": "s5$", "b": "b8", "g": "g9", "t": "t7"}


def _name_re(name: str) -> re.Pattern:
    """Whole-name match, any case ("rosa", "ROSA") and with look-alike digits ("R0sa"),
    except names that are everyday words, which only match exactly as written."""
    if name.lower() in COMMON_WORDS:
        return re.compile(rf"(?<![\w\[]){re.escape(name)}(?![\w\]])")
    body = "".join(f"[{re.escape(LOOKALIKES[c])}]" if c in LOOKALIKES else re.escape(c)
                   for c in name.lower())
    return re.compile(rf"(?<![\w\[]){body}(?![\w\]])", re.I)


def _nicknames(first: str) -> list[str]:
    """Common pet forms of a first name: Rosa -> Rosie, Rosita, Rosy. Only for names of 4+
    letters ending in a vowel, so short names don't turn into everyday words."""
    if len(first) < 4 or first[-1].lower() not in "aeiou":
        return []
    stem = first[:-1]
    return [stem + end for end in ("ie", "y", "ita", "ito", "i")]


def redact(text: str, names: dict[str, str]) -> str:
    text = ZERO_WIDTH_RE.sub("", text)   # "Ma\u200bria" must not slip past the name match
    for rx, token in PII_PATTERNS:
        text = rx.sub(token, text)
    for name in sorted(names, key=len, reverse=True):
        text = _name_re(name).sub(names[name], text)
    return re.sub(r"(\[[A-Z #]+\])(?:\s+\1)+", r"\1", text)   # "[CLIENT] [CLIENT]" -> "[CLIENT]"


def find_leaks(data, names: dict[str, str]) -> list[str]:
    """Final check on anything a lawyer will see: list every known name or PII pattern still present."""
    blob = ZERO_WIDTH_RE.sub("", str(data))
    leaks = [n for n in names if _name_re(n).search(blob)]
    for rx, _ in PII_PATTERNS:
        leaks += [m.group(0) for m in rx.finditer(blob) if "[" not in m.group(0)]
    return [x for i, x in enumerate(leaks) if x not in leaks[:i] and not any(x in y for y in leaks if y != x)]


HIDDEN_STATEMENT = "[Statement hidden to protect the client's identity]"

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

