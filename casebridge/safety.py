"""Responsible-AI layer: citation enforcement, no-legal-advice guardrail, PII redaction."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import CaseBrief, Evidence, Fact

# The assistant organizes facts. It must never predict outcomes, value a case, or tell
# the person what legal action to take.
_LEGAL_ACT = r"(accept|sign|reject|refuse|decline|settle|sue|file|counter|take (?:the|their|that|this) (?:money|offer|deal|settlement|check))"
_SOFT = r"(?:\s+(?:probably|definitely|really|just|absolutely|certainly|likely|not|never|seriously|strongly|consider|think about))*"
ADVICE_PATTERNS = [
    # Predicting the outcome: "you'll win", "you're likely to lose", "a jury would side with you".
    r"\byou(?:'ll|'d|'re| will| would| are| could| can| might| should)?(?:\s+\w+){0,3}?\s+(win|lose|prevail)\b"
    r"(?!\s+(?:consciousness|your|my|his|her|their|time|wages|weight|sleep|work|income|the use|track|balance|control))",
    r"\byou (will|would|should|are going to) (win|lose)\b",
    r"\b(jury|judge|court)\s+(?:would|will|is likely to|should|could)\s+(?:probably |likely |definitely |almost certainly )?"
    r"(side|rule|find|award|agree|believe)\b",
    # Telling the person what to do: "you should accept", "you ought to settle", "don't sign".
    rf"\byou(?:'d| would)?\s+(?:should|ought to|must|need to|have to|had better|'d better|better){_SOFT}"
    rf"(?:\s+\w+)?\s+{_LEGAL_ACT}\b",
    r"\bshould(n't| not)? you (accept|sign|reject|settle|sue|file)\b",
    rf"(?:^|[.!?:]\s+|\n)(?:please\s+|just\s+)?(?:don't|do not|never)\s+{_LEGAL_ACT}\b",
    rf"(?:^|[.!?:]\s+|\n)(?:just\s+)?(accept|reject|refuse|settle for|sue)\s+(?:the|their|this|that|it|them|him|her)\b",
    r"\bI(?:'d| would)? (?:strongly )?(?:recommend|suggest|advise|urge)\b",
    rf"\bI(?:'d| would)(?:\s+\w+)?\s+{_LEGAL_ACT}\b",
    r"\b(?:my|our) (?:advice|recommendation)\b",
    r"\bit(?:'s| is| would be| might be| may be) (?:wise|smart|best|a good idea|a bad idea|in your (?:best )?interest) to\b",
    r"\byour best (?:option|move|bet|choice) is\b",
    r"\bthere(?:'s| is) no (?:point|use|reason) (?:in )?(?:fighting|suing|contesting|waiting|hiring)\b",
    r"\bmost people (?:in your (?:situation|position|shoes) )?(?:would )?(?:settle|accept|sign|sue|take)\b",
    # Putting a value on the case: "your claim is easily worth six figures", "you could get $50,000".
    r"\b(case|claim|lawsuit|suit|injur(?:y|ies))\b[^.?!\n]{0,25}\bworth\b"
    r"(?!\s+(?:fighting|pursuing|noting|mentioning|keeping|reporting|a look|the (?:effort|time|trouble)|it)\b)",
    r"\b(?:this|it|that)(?:'s| is| could be| may be| might be| would be)\s+(?:\w+\s+)?worth\s+"
    r"(?:\$|\d|six|seven|a lot|more|up to|around|about|at least|over)",
    r"\byou(?:'d|'re| could| might| can| would| should| are likely to| stand to)(?:\s+\w+)?\s+"
    r"(?:get|recover|receive|be awarded|collect|walk away with)\s+(?:up to |around |about |at least |over |more than )?"
    r"(?:\$|\d|six figures|seven figures|a lot|compensation|damages|a settlement)",
    r"\bexpect(?:ed)?\s+(?:to (?:get|receive|recover)\s+)?(?:a\s+)?(?:settlement|payout|award|around \$|about \$|up to \$|at least \$|\$)",
    r"\bguarantee",
    r"\b(strong|weak|winning|losing|good|solid|great|excellent|airtight|slam[- ]dunk) (case|claim)\b",
    r"\bsettle for \$",
    r"\b(case|claim)\s+(?:should|will|would|could|might)\s+(?:probably |likely |easily )?settle\b",
    # Spanish: "debería firmar", "le conviene aceptar", "su caso vale", "tiene un caso fuerte", "ganará"
    r"\bdeber[ií]a(s|n)? (aceptar|firmar|rechazar|demandar|llegar a un acuerdo|conformarse)\b",
    r"\b(le|te|les) conviene (aceptar|firmar|rechazar|demandar|llegar a un acuerdo|conformarse)\b",
    r"\b(su|tu) (caso|reclamo) vale\b",
    r"\b(tiene|tienes|tienen) un (?:buen caso|caso (?:muy )?(?:fuerte|s[oó]lido|ganado|bueno))\b",
    r"\b(usted )?(ganar[áa]|perder[áa]|vas? a ganar|vas? a perder)\b",
    # Vietnamese, matched without accents (see _advice_text): "bà nên ký" (you should sign),
    # "vụ này đáng giá" (this case is worth), "bà sẽ thắng" (you will win).
    r"\b(ba|ong|anh|chi|ban|em|co|chu|bac|cau)\s+nen\s+(ky|chap nhan|tu choi|kien|hoa giai|dong y|nhan tien)\b",
    r"\bvu (?:kien |viec )?nay\b.{0,20}\b(dang gia|tri gia)\b",
    r"\b(ba|ong|anh|chi|ban|em|co|chu|bac|cau)\s+(?:chac chan )?se\s+(thang|thua)\b",
]
ADVICE_RE = re.compile("|".join(f"(?:{p})" for p in ADVICE_PATTERNS), re.I)


# --- Spoken-transcript cleanup ------------------------------------------------------------
# Voice memos are recorded in shock: "this stupid driver crashed my car hm hm, f*** him, what
# do I do". A lawyer needs the facts, not the filler sounds, swearing, insults or questions to
# no one. The audio itself is never changed; only the transcript the brief is built from is.
SPEECH_NOISE = [
    # Curses aimed at someone, removed as a whole phrase: "fuck him", "screw that guy".
    r"\b(?:fuck|screw|damn|to hell with)\s+(?:him|her|them|you|it|that|this)"
    r"(?:\s+(?:guy|man|woman|lady|driver|person))?\b",
    r"\bwhat the (?:fuck|hell|heck)\b",
    # Asking for help out loud: not a fact about the accident.
    r"\b(?:i don'?t know )?what (?:do|should|can) i do\b\??|\b(?:i don'?t know )?what to do\b\??",
    # Swear words, including Whisper's own masking ("f***ing").
    r"\bf+u+c+k+(?:ing|in'?|ed|er|ers|s)?\b|\bf\*+[a-z]*|\b(?:bull)?shit(?:ty|s)?\b"
    r"|\bgod ?damn(?:ed|it)?\b|\bdamn(?:ed|it)?\b|\bbitch(?:es)?\b|\bcrap\b|\bass(?:holes?)?\b"
    r"|\bbastards?\b|\bwtf\b",
    # Insults about the other person. The fact ("the driver crashed my car") stays.
    r"\b(?:stupid|idiot(?:ic|s)?|moron(?:ic|s)?|dumb(?:ass)?|jerk)\b",
    # Filler sounds.
    r"\b(?:u+h+m*|u+m+|h+m+|m{2,}|e+r+m+|a+h+|e+h+)\b",
]
SPEECH_NOISE_RE = re.compile("|".join(f"(?:{p})" for p in SPEECH_NOISE), re.I)
REPEATED_WORD_RE = re.compile(r"(^|[.!?]\s+|\n)(\w{1,3})(?:[\s,]+\2\b)+\s*[.!?]?\s*(?=\S|$)", re.I)


def clean_speech(text: str) -> tuple[str, int]:
    """Remove filler sounds, swearing, insults and spoken help-questions from a transcript.
    Returns (clean text, number of pieces removed)."""
    clean, removed = SPEECH_NOISE_RE.subn("", text)
    # A sentence that is one short word said over and over ("Him, him." is Whisper's
    # usual mishearing of "hmm, hmm"; "No no no.") carries no fact.
    clean, stutters = REPEATED_WORD_RE.subn(r"\1", clean)
    removed += stutters
    if not removed:
        return text, 0
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r" +([,.!?;:])", r"\1", clean)                # "car ," -> "car,"
    clean = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", clean)          # ", ," -> ","
    clean = re.sub(r"[,;:]+\s*([.!?])", r"\1", clean)              # ",." -> "."
    clean = re.sub(r"([.!?])(?:\s*[,.!?;:])+", r"\1", clean)       # ". ," -> "."
    clean = re.sub(r"(^|\n)[ ,.!?;:]+", r"\1", clean)               # punctuation left at a line start
    clean = re.sub(r"[ ,;:]+(\n|$)", r"\1", clean).strip()
    clean = re.sub(r"(^|[.!?]\s+|\n)([a-z])", lambda m: m.group(1) + m.group(2).upper(), clean)
    if clean and clean[-1].isalnum():
        clean += "."
    return clean, removed


def _advice_text(text: str) -> str:
    """The text as the advice check sees it: the same clean-up as the injection scan (no hidden
    characters, look-alike letters or accents), with curly apostrophes made straight."""
    return _scan_text(text).replace("’", "'").replace("‘", "'")


def is_advice(text: str) -> bool:
    return bool(ADVICE_RE.search(_advice_text(str(text))))


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


# --- Numbers check -------------------------------------------------------------------------
# The most common, most harmful hallucination in a brief is a wrong number: a speed, an amount,
# a date, a time. Every number in a statement must appear in the evidence it cites. This runs
# in every mode, so it works offline too.

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    text = re.sub(r"\bE\d+\b", " ", text)   # evidence ids are not claims
    found = set()
    for raw in _NUMBER_RE.findall(text):
        n = raw.rstrip(",.").replace(",", "")
        n = re.sub(r"\.0+$", "", n).lstrip("0") or "0"
        found.add(n)
    return found


_MONTH_NUMBERS = {m: str(i) for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
_MONTH_NAME_RE = re.compile(r"\b(" + "|".join(f"{m}|{m[:3]}" for m in _MONTH_NUMBERS) + r")\b\.?", re.I)


def _evidence_numbers(text: str) -> set[str]:
    found = _numbers(text)
    for m in _MONTH_NAME_RE.findall(text):   # "October 2" also supports "10/2"
        found.add(next(v for k, v in _MONTH_NUMBERS.items() if k.startswith(m.lower())))
    for h, _ in re.findall(r"\b(\d{1,2}):(\d{2})\b", text):   # 17:42 also supports "5:42 pm"
        h = int(h)
        found |= {str(h % 12 or 12), str(h + 12 if h < 12 else h)}
    return found


def unsupported_numbers(text: str, cited_texts: list[str]) -> list[str]:
    """Numbers in a statement that none of its cited evidence contains, in order."""
    supported = set().union(*(_evidence_numbers(t) for t in cited_texts)) if cited_texts else set()
    return sorted(_numbers(text) - supported, key=text.find)


def check_numbers(brief: CaseBrief, evidence_texts: dict[str, str]) -> int:
    """Flag facts (and the summary) with numbers their evidence doesn't contain. Returns the count."""
    flagged = 0
    for section in ("timeline", "parties", "injuries", "damages"):
        for f in getattr(brief, section):
            missing = unsupported_numbers(f.text, [evidence_texts[s] for s in f.sources if s in evidence_texts])
            if missing:
                f.guardian_flags.append(f"⚠ {', '.join(missing)} not in [{', '.join(f.sources)}]")
                flagged += 1
    # The rules summary states counts the app computed ("6 pieces of evidence"); only a
    # model-written summary can invent a number.
    missing = [] if brief.engine == "rules" else unsupported_numbers(brief.summary, list(evidence_texts.values()))
    if missing:
        brief.summary_guardian_flags.append(f"⚠ {', '.join(missing)} not in the evidence")
        flagged += 1
    return flagged


def apply_guardrails(brief: CaseBrief, valid_ids: set[str],
                     evidence_texts: dict[str, str] | None = None) -> CaseBrief:
    dropped_total, blocked = 0, 0
    for section in ("timeline", "parties", "injuries", "damages"):
        facts, dropped = enforce_citations(getattr(brief, section), valid_ids)
        dropped_total += dropped
        clean = []
        for f in facts:
            if is_advice(f.text) or is_advice(f.when or ""):   # a model can put advice in "when" too
                blocked += 1
            else:
                clean.append(f)
        setattr(brief, section, clean)
    if is_advice(brief.summary):
        blocked += 1
        # Drop every sentence that reads as advice; keep the rest of the summary.
        brief.summary = " ".join(s for s in re.split(r"(?<=[.!?])\s+", brief.summary.strip())
                                 if not is_advice(s))
    if dropped_total:
        brief.warnings.append(f"Removed {dropped_total} AI-generated statement(s) with no source evidence.")
    if blocked:
        brief.warnings.append(f"Blocked {blocked} statement(s) that read like legal advice or outcome predictions.")

    kept = [f for section in ("timeline", "parties", "injuries", "damages") for f in getattr(brief, section)]
    brief.checks.append({
        "id": "sources", "name": "Sources", "status": "flag" if dropped_total else "pass",
        "detail": f"{len(kept)} statements, each pointing to the evidence it came from."
                  + (f" {dropped_total} with no source {'was' if dropped_total == 1 else 'were'} removed."
                     if dropped_total else "")})
    if evidence_texts is not None:
        wrong = check_numbers(brief, evidence_texts)
        if wrong:
            brief.warnings.append(f"Flagged {wrong} statement(s) with a number that isn't in the evidence they cite.")
        count = sum(len(_numbers(f.text)) for f in kept)
        brief.checks.append({
            "id": "numbers", "name": "Numbers", "status": "flag" if wrong else "pass",
            "detail": (f"{wrong} statement{' contains' if wrong == 1 else 's contain'} a number its source "
                       "doesn't have." if wrong else
                       f"All {count} numbers (dates, times, amounts) appear in the evidence they cite.")})
    brief.checks.append({
        "id": "advice", "name": "Legal advice", "status": "flag" if blocked else "pass",
        "detail": (f"{blocked} statement{'' if blocked == 1 else 's'} blocked for predicting an outcome, telling you what to do, "
                   "or putting a value on the case." if blocked else
                   "Nothing predicts an outcome, tells you what to do, or puts a value on the case.")})
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


def injection_flags(evidence: list[Evidence]) -> list[str]:
    """Ids of evidence items that contain text trying to instruct an AI."""
    # The title is scanned too: for an upload it is the file name, which anyone can write.
    return [e.id for e in evidence if has_injection(f"{e.title}\n{e.text}")]


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
    # The title (a file name for uploads) goes on one line with no tags or quotes, so it can't
    # open a fake item or close this one.
    safe_title = re.sub(r"[<>\"\r\n]+", " ", title).strip()
    safe_kind = re.sub(r"[^a-z]", "", kind.lower())
    flag = ' flagged="possible-instructions"' if has_injection(f"{title}\n{text}") else ""
    return f'<evidence id="{evidence_id}" kind="{safe_kind}"{flag}>\n{safe_title}\n{clean}\n</evidence>'


# --- Redaction for the lawyer-side case board -------------------------------------------
# Pattern-based, and tuned to fail closed: when unsure, hide it. Lawyers only see the real
# brief after the client accepts them.

# Latin letters with accents beyond Latin-1, by case: Vietnamese "Bảo", "Nguyễn", Polish "Łukasz".
_EXT = [chr(c) for c in [*range(0x100, 0x250), *range(0x1E00, 0x1F00)]]
_UP = "A-ZÀ-ÖØ-Þ" + "".join(c for c in _EXT if c.isupper())
_LO = "a-zß-öø-ÿ" + "".join(c for c in _EXT if c.islower())
_WORD = rf"[{_UP}](?:['’][{_UP}])?[{_LO}]+(?:[-'’][{_UP}]?[{_LO}]+)*"   # also O'Brien, Smith-Jones
NAME = rf"({_WORD}(?:\s{_WORD}){{0,2}})"          # "Maria Lopez", "Rosa María Martínez"
# Forms and scans write names in capitals, often surname first: "LOPEZ, MARIA". Only used after
# an unambiguous label, because capitals are also used for headings.
_CAPS = rf"[{_UP}]{{2,}}(?:['’-][{_UP}]+)*"
CAPS_NAME = rf"({_CAPS}(?:,?[ \t]+{_CAPS}){{0,2}})"
_INITIAL = rf"(?:[{_UP}]\.\s*)?"                  # "Officer J. Ramirez"
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
    # Starts only where a run of email characters starts (not at every \b inside it): with \b,
    # a long "word-word-word-..." with no @ backtracked from every position and took seconds.
    (re.compile(r"(?<![\w.+-])[\w.+-]+\s*(?:@|＠|\(at\)|\[at\])\s*[\w-]+(?:\.[\w-]+)+\b", re.I), "[EMAIL]"),
    # Social media handles: "@marialopez84". After the email pattern, so "a@b.com" stays an email.
    (re.compile(r"(?<![\w.@])@[A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?\b"), "[HANDLE]"),
    # Dates of birth after a label, in many formats, English and Spanish.
    (re.compile(rf"\b((?i:DOB|D\.O\.B\.?|date of birth|birth ?date|birthday(?: is)?|born(?: on| in)?|"
                rf"fecha de nacimiento|cumplea[ñn]os(?: es)?|nacid[oa] (?:el|en)))\s*[:\-]?\s*{_DATE}\b"), r"\1 [REDACTED]"),
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
    (re.compile(r"\b\d[\s-][A-Z]{3}[\s-]\d{3}\b"), "[PLATE]"),               # spaced: "7 ABC 123"
    (re.compile(r"\b((?i:plate|placa|license plate))(\s*(?i:no\.?|number|#))?\s*[:#]?\s*[A-Za-z0-9-]{2,8}\b"),
     r"\1 [PLATE]"),
    (re.compile(r"\b[A-Za-z]{2}-\d{2}-\d{4,}\b"), "[REPORT #]"),
    (re.compile(r"\b((?i:policy|claim|member|account|MRN|medical record|driver'?s license|DL|report|"
                r"incident|reference|ref|ID)(?:\s*(?i:no\.?|number|#|ID))?)\s*[:#]?\s*"
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
    rf"[Mm]y name(?: is|'s|’s) {NAME}", rf"\bI am {NAME}", rf"\bI'm {NAME}", rf"[Mm]e llamo {NAME}",
    rf"[Mm]i nombre es {NAME}", rf"(?:Patient|Claimant|Client|Customer|Name|Nombre):\s*{NAME}",
    rf"(?:Dear|Hi|Hello|Hola|Estimad[oa]) (?:Ms\.|Mr\.|Mrs\.|Sra\.|Sr\.)?\s*{NAME}", rf"Vehicle 1:[^.]*?driver {NAME}",
    rf"(?i:tôi tên là|tên tôi là|tôi là)\s+{NAME}",                       # Vietnamese: "my name is"
    rf"(?:[Mm]y name is|MY NAME IS|(?i:patient|claimant|client|insured|name|nombre)\s*:)\s*{CAPS_NAME}",
]
ROLE_PATTERNS = [
    ("[CLIENT]", CLIENT_NAME_PATTERNS),
    ("[OTHER PARTY]", [rf"driver,? (?:his|her) name is {NAME}", rf"Vehicle 2:[^.]*?driver {NAME}",
                       rf"(?i:the other driver|the driver|other driver|el otro conductor|el conductor)"
                       rf"(?:,| was| is| named| called| fue| era|:)*\s+{NAME}",
                       rf"our insured {NAME}", rf"(?:owner|defendant):?\s+{NAME}"]),
    ("[ADJUSTER]", [rf"[Aa]djuster:?\s+{NAME}", rf"{NAME}, (?:a |the |your )?(?:claims )?adjuster"]),
    ("[PERSON]", [rf"(?i:witness|manager|employee|officer|deputy|detective|sergeant|sgt|trooper|paramedic|"
                  rf"nurse|supervisor|clerk|cashier|gerente|testigo)\.?(?: named|:|,)? {_INITIAL}{NAME}",
                  rf"\b(?:Dr|Mr|Ms|Mrs|Sr|Sra|Srta)\.?\s+{_INITIAL}{NAME}", rf"(?:named|called|llamad[oa]) {NAME}",
                  rf"[Tt]his is {NAME}",
                  rf"(?:Sincerely|Regards|Atentamente|Signed|Signature|Firma(?:do)?)[,:]?\s+{NAME}",
                  # Family and friends: "my son Daniel", "my husband, Carlos Ruiz", "mi esposo Juan".
                  rf"\b(?i:my|mi|our|his|her|their)\s+(?i:son|daughter|husband|wife|partner|boyfriend|girlfriend|"
                  rf"fianc[ée]e?|brother|sister|mother|father|mom|dad|mum|grandson|granddaughter|grandmother|"
                  rf"grandfather|grandma|grandpa|cousin|aunt|uncle|niece|nephew|friend|neighbou?r|co-?worker|boss|"
                  rf"roommate|esposo|esposa|marido|hijo|hija|hermano|hermana|madre|padre|mam[aá]|pap[aá]|nieto|"
                  rf"nieta|abuelo|abuela|primo|prima|t[ií]o|t[ií]a|amigo|amiga|novio|novia|vecino|vecina|jefe)"
                  rf"(?:,| named| called| llamad[oa])?\s+{NAME}"]),
]
# Speech-to-text can drop capitals: "my name is rosa martinez". Only unambiguous cues here.
LOWER_INTRO_RE = re.compile(r"(?i:my name is|my name['’]s|me llamo|mi nombre es|patient:|nombre:)\s+"
                            rf"([{_LO}'’-]+(?:\s[{_LO}'’-]+){{0,2}})")
INTRO_STOP = {"and", "y", "i", "im", "my", "from", "de", "del", "la", "el", "is", "es", "but", "pero",
              "so", "the", "a", "was", "fui", "estaba", "soy", "am", "me", "mi", "tengo"}
# Names that are also everyday words: replaced only when capitalized, to keep the brief readable.
COMMON_WORDS = {"will", "mark", "grant", "bill", "may", "june", "april", "rose", "frank", "art", "hope",
                "joy", "faith", "pat", "sue", "dawn", "rob", "ray", "guy", "jack", "chase", "page",
                "lane", "wade", "ford", "cole", "shaw", "rich", "drew", "gay", "penny", "summer",
                "sky", "river", "dean", "nick", "victor", "angel"}
# Capitalized words the name patterns can swallow but which are never names.
NOT_NAMES = {"I", "The", "And", "But", "So", "My", "He", "She", "They", "We", "His", "Her", "Our",
             "Okay", "Yes", "No", "Not", "Very", "Really", "Just", "Sorry", "Scared", "Fine", "Here",
             "Driver", "Vehicle", "Police", "Officer", "Store", "Manager", "Insurance", "Doctor", "Dr",
             "Contact", "Call", "Please", "Hi", "Hello", "Dear", "Thanks", "Thank", "Regards",
             # Labels that sit next to capitalized names on forms: "LOPEZ, MARIA DOB 03/08/1984".
             "DOB", "MRN", "SSN", "DL", "ID", "AGE", "SEX", "DATE", "ER", "MD", "RN", "CA", "USA", "PHONE",
             "ADDRESS", "MALE", "FEMALE", "M", "F", "N/A", "NA"}


def _plain(s: str) -> str:
    """Strip accents, so "Martínez" also catches "Martinez"."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# Names with no cue around them ("Kevin said he was sorry") are caught by common first names and
# surnames (US, Spanish, Vietnamese, Chinese, Korean, Indian). Words that are also everyday English
# ("Will", "Brown", "Young", "Do", "Long") are left out on purpose. Over-hiding is the safe side.
FIRST_NAMES = set("""
Aaron Adam Adrian Ahmed Aisha Alan Albert Alberto Alejandra Alejandro Alex Alexander Alexis Alfredo Alice
Alicia Alma Amanda Amber Amir Amit Amy Ana Anand Andrea Andres Andrew Angela Angelica Anh Anita Ann Anna
Anthony Antonio Arjun Armando Arturo Ashley Barbara Benjamin Beatriz Betty Blanca Bao Brandon Brenda Brian
Brittany Bryan Camila Carlos Carmen Carol Carolina Catherine Cesar Chad Charles Cheng Chris Christian
Christina Christine Christopher Cindy Claudia Cristina Cynthia Daniel Daniela David Deborah Debra Denise
Dennis Derek Diana Diego Donald Donna Dorothy Douglas Duc Dung Edgar Eduardo Edward Elena Elizabeth Emily
Emma Enrique Eric Erica Erik Ernesto Esther Eugene Evelyn Fatima Fernando Francisco Gabriel Gabriela Gary
George Gerardo Gloria Gonzalo Gregory Guadalupe Guillermo Gustavo Hai Hannah Hao Harold Heather Hector
Helen Hieu Hoa Hung Hyun Isabel Ivan Jacob Jaime Jake James Jamal Jasmine Jason Javier Jeffrey Jennifer
Jeremy Jesse Jessica Jesus Ji Jia Jin Joanna Joel John Jonathan Jorge Jose Joseph Joshua Joyce Juan Juana
Judith Julia Julian Julie Justin Karen Katherine Kathleen Kathryn Kayla Kelly Kenneth Kevin Kim Kimberly
Krishna Kyle Larry Laura Lauren Leticia Lina Linda Lisa Lucia Luis Luz Madison Manuel Marco Marcos
Margaret Maria Mariana Marie Marisol Marta Martha Martin Mary Matthew Megan Melissa Mia Michael Michelle
Miguel Min Minh Mohammed Monica Nancy Natalia Nathan Nicholas Nicole Noah Olga Olivia Omar Oscar Pablo
Pamela Patricia Patrick Paul Paula Pedro Peter Phuong Pooja Priya Rachel Rafael Rahul Rajesh Ramon Raul
Rebecca Ricardo Richard Roberto Robert Rocio Rodrigo Ronald Rosa Ruth Ryan Samantha Samuel Sandra Sara
Sarah Scott Sean Sergio Sharon Shirley Silvia Sofia Sonia Stephanie Stephen Steven Sunil Susan Teresa
Thanh Thao Thomas Timothy Tuan Tyler Valeria Vanessa Veronica Vikram Virginia Walter Wei William Xiao
Yesenia Yolanda Yong Yuki Zachary
""".split())
SURNAMES = set("""
Acosta Aguilar Alvarado Alvarez Anderson Bui Castillo Castro Chavez Chen Cho Choi Cruz Dang Diaz Dinh
Dominguez Duong Ellison Espinoza Estrada Flores Garcia Gomez Gonzales Gonzalez Gupta Gutierrez Guzman
Hernandez Herrera Hoang Holt Huang Huynh Jackson Jimenez Johnson Juarez Kang Kumar Lam Lee Li Lin Liu
Lopez Luna Martinez Mehta Mendez Mendoza Molina Morales Moreno Munoz Ngo Nguyen Ortega Ortiz Patel
Pena Perez Pham Phan Ramirez Ramos Reyes Rios Rivera Rodriguez Romero Ruiz Salazar Sanchez Sandoval Shah
Sharma Silva Singh Smith Soto Suarez Thompson Torres Tran Trinh Truong Vargas Vasquez Vazquez Vega
Vo Vu Wang Whitmore Williams Wilson Wong Wu Yang Zhang Zhao
""".split())
# Place names built on a person's name ("San Jose", "Santa Clara", "Stevens Creek Blvd").
_PLACE_BEFORE = re.compile(r"(?:San|Santa|Santo|St\.?|Saint|Mount|Mt\.?|Fort|Lake|Port|Los|Las|El)\s+$")
_PLACE_AFTER = re.compile(r"\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|"
                          r"Pl|Place|Creek|Park|Center|Centre|Hospital|Medical|Clinic|Market|Insurance|Mutual|"
                          r"County|City|Police|School|University|College|Bank|Plaza|Mall|Expressway|Freeway)\b")
_CAP_WORD_RE = re.compile(rf"(?<![\w\[]){_WORD}")
_NEXT_WORD_RE = re.compile(rf"[ \t]+({_WORD})")


def _dictionary_names(text: str) -> list[str]:
    """Names with no cue, from the first-name and surname lists: "Kevin Holt", "Kevin", "Nguyen"."""
    found = []
    for m in _CAP_WORD_RE.finditer(text):
        word = m.group(0)
        if word not in FIRST_NAMES and _plain(word) not in SURNAMES:
            continue
        if _PLACE_BEFORE.search(text[max(0, m.start() - 8):m.start()]) or _PLACE_AFTER.match(text, m.end()):
            continue
        # Up to two more capitalized words belong to the name: "Kevin Holt said", "Tran Van Minh".
        end = m.end()
        for _ in range(2):
            nxt = _NEXT_WORD_RE.match(text, end)
            if not nxt or nxt.group(1) in NOT_NAMES or _PLACE_AFTER.match(text, nxt.end()):
                break
            word, end = f"{word} {nxt.group(1)}", nxt.end()
        found.append(word)
    return found


def find_names(texts: list[str]) -> dict[str, str]:
    """Map each detected person name, its parts and its unaccented spelling to a role placeholder."""
    joined = "\n".join(texts)
    names: dict[str, str] = {}
    for role, patterns in ROLE_PATTERNS:
        for p in patterns:
            for m in re.finditer(p, joined):
                words = [w.strip(",").title() if w.strip(",").isupper() else w.strip(",")
                         for w in m.group(1).split() if w.strip(",") not in NOT_NAMES]
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
    for name in _dictionary_names(joined):
        names.setdefault(name, "[PERSON]")
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


def _accent_variants() -> dict[str, str]:
    """Every accented Latin letter, grouped by its plain letter: "a" -> "aàáâãäåāăą…ạảấầ…".

    Names are often found in the English text ("Nguyen Thi Bao") but also appear with their
    accents elsewhere, such as the Vietnamese original of a memo ("Nguyễn Thị Bảo").
    """
    groups: dict[str, set[str]] = {}
    for cp in [*range(0xC0, 0x250), *range(0x1E00, 0x1F00)]:   # Latin-1, Extended-A/B, Additional
        ch = chr(cp).lower()
        base = _plain(ch)
        if len(base) == 1 and base.isascii() and base.isalpha():
            groups.setdefault(base, {base}).add(ch)
    groups["d"].add("đ")   # Vietnamese d-bar has no NFKD decomposition
    return {base: "".join(sorted(chars)) for base, chars in groups.items()}


ACCENT_VARIANTS = _accent_variants()


def _name_re(name: str) -> re.Pattern:
    """Whole-name match, any case ("rosa", "ROSA"), with or without accents ("Bao", "Bảo") and
    with look-alike digits ("R0sa"), except names that are everyday words, which only match
    exactly as written."""
    if name.lower() in COMMON_WORDS:
        return re.compile(rf"(?<![\w\[]){re.escape(name)}(?![\w\]])")
    body = ""
    for c in name.lower():
        base = _plain(c)
        chars = {c} | set(ACCENT_VARIANTS.get(base, "")) | set(LOOKALIKES.get(base, ""))
        body += f"[{re.escape(''.join(sorted(chars)))}]" if len(chars) > 1 else re.escape(c)
    return re.compile(rf"(?<![\w\[]){body}(?![\w\]])", re.I)


def _nicknames(first: str) -> list[str]:
    """Common pet forms of a first name: Rosa -> Rosie, Rosita, Rosy. Only for names of 4+
    letters ending in a vowel, so short names don't turn into everyday words."""
    if len(first) < 4 or first[-1].lower() not in "aeiou":
        return []
    stem = first[:-1]
    return [stem + end for end in ("ie", "y", "ita", "ito", "i")]


def redact(text: str, names: dict[str, str], swaps: list[tuple[str, str]] | None = None) -> str:
    """Replace personal details with placeholders. Pass a list as swaps to also get every
    (original, placeholder) pair in order, e.g. for the app's client-to-lawyer view animation."""
    def sub(rx: re.Pattern, token: str, text: str) -> str:
        def one(m: re.Match) -> str:
            new = m.expand(token)
            if swaps is not None:
                swaps.append((m.group(0), new))
            return new
        return rx.sub(one, text)

    text = ZERO_WIDTH_RE.sub("", text)   # "Ma\u200bria" must not slip past the name match
    for rx, token in PII_PATTERNS:
        text = sub(rx, token, text)
    for name in sorted(names, key=len, reverse=True):
        text = sub(_name_re(name), names[name], text)
    return re.sub(r"(\[[A-Z #]+\])(?:\s+\1)+", r"\1", text)   # "[CLIENT] [CLIENT]" -> "[CLIENT]"


def find_leaks(data: Any, names: dict[str, str]) -> list[str]:
    """Final check on anything a lawyer will see: list every known name or PII pattern still present."""
    blob = ZERO_WIDTH_RE.sub("", str(data))
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
    "[ZIP]": "ZIP codes", "[HANDLE]": "social media handles", "[LOCATION]": "GPS locations", "[PLATE]": "licence plates",
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

