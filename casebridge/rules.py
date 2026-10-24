"""Deterministic extraction. Works offline, and is also the source of truth for
deadlines and missing-evidence checks even when an LLM writes the narrative."""
from __future__ import annotations

import re
from datetime import date, datetime

from .models import CaseBrief, Evidence, Fact

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b")
TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{2}:\d{2})\b", re.I)

CASE_KEYWORDS = {
    "auto_accident": ["car", "vehicle", "truck", "collision", "rear", "driver", "traffic", "bumper"],
    "premises": ["slipped", "slip", "fell", "wet floor", "store", "stairs", "premises"],
    "dog_bite": ["dog", "bite", "bit me"],
    "workplace": ["at work", "my employer", "on the job", "workers comp", "forklift"],
    "medical": ["surgery", "misdiagnosed", "misdiagnosis", "doctor made", "malpractice", "wrong medication"],
}
DEFENSE_CUES = ["i hit", "i rear-ended", "suing me", "sued me", "lawsuit against me",
                "claim against me", "my fault", "i ran the light"]
PLAINTIFF_CUES = ["hit me", "struck vehicle 1", "rear-ended me", "hit from behind",
                  "bit me", "i was injured", "his insurance", "her insurance"]
INJURY_WORDS = ["pain", "whiplash", "strain", "fracture", "broken bone", "concussion",
                "bruise", "emergency room", "diagnosis", "physical therapy", "injur",
                "sprain", "contusion", "swell", "urgent care", "hurt"]
PARTY_WORDS = ["driver", "insurance", "insured", "adjuster", "witness", "officer", "employer", "owner"]

CITY_TO_COUNTY = {
    "san jose": "Santa Clara", "santa clara": "Santa Clara", "sunnyvale": "Santa Clara",
    "palo alto": "Santa Clara", "mountain view": "Santa Clara", "cupertino": "Santa Clara",
    "san francisco": "San Francisco", "oakland": "Alameda", "berkeley": "Alameda",
    "fremont": "Alameda", "hayward": "Alameda", "san mateo": "San Mateo",
    "redwood city": "San Mateo", "daly city": "San Mateo", "walnut creek": "Contra Costa",
    "concord": "Contra Costa", "richmond": "Contra Costa",
}
GOVERNMENT_CUES = ["city bus", "vta", "bart", "muni", "caltrans", "city of", "county vehicle",
                   "police car", "school bus", "pothole"]

# What a lawyer will usually ask for, by case type: (label, evidence kind or None, keywords)
CHECKLIST = {
    "auto_accident": [
        ("Police / collision report", "document", ["police", "collision report"]),
        ("Photos of the scene or vehicles", "photo", []),
        ("Medical records", "document", ["diagnosis", "discharge", "medical"]),
        ("Written repair estimate", "document", ["estimate", "invoice"]),
        ("Other driver's insurance details", None, ["insurance"]),
        ("Witness contact information", None, ["witness"]),
        ("Proof of lost wages (pay stubs / employer letter)", "document", ["pay stub", "wage", "employer"]),
    ],
    "premises": [
        ("Photos of the hazard", "photo", []),
        ("Incident report from the property", "document", ["incident report"]),
        # Stores often record over camera footage within days, so this is time-sensitive.
        ("Request to keep the security camera footage", None, ["footage", "camera", "cctv", "video"]),
        ("Medical records", "document", ["diagnosis", "discharge", "medical"]),
        ("Witness contact information", None, ["witness"]),
    ],
    "dog_bite": [
        ("Photos of the injuries", "photo", []),
        ("Medical records", "document", ["diagnosis", "discharge", "medical", "urgent care"]),
        ("Animal control or bite report", "document", ["animal control", "bite report"]),
        ("Dog owner's name and contact details", None, ["owner"]),
        ("Dog's vaccination records", None, ["vaccin", "rabies"]),
        ("Witness contact information", None, ["witness"]),
    ],
}
DEFAULT_CHECKLIST = [
    ("Medical records", "document", ["diagnosis", "discharge", "medical"]),
    ("Photos", "photo", []),
    ("Witness contact information", None, ["witness"]),
]

CONTACT_RE = re.compile(r"\(?\d{3}\)?[\s.-]?\d{3}-\d{4}|[\w.]+@[\w.]+")


def sentences(ev: Evidence) -> list[str]:
    # Don't split after honorifics like "Ms." or "Dr.".
    parts = re.split(r"(?<!\bMs\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)(?<!\bSra\.)(?<!\bSr\.)(?<=[.!?])\s+",
                     ev.text)
    return [s.strip() for s in parts if s.strip()]


def all_text(evidence: list[Evidence]) -> str:
    return " ".join(e.text for e in evidence).lower()


def _count_words(text: str, phrase: str) -> int:
    """Whole-word count, so "car" doesn't match "urgent care", "scar" or "card"."""
    return len(re.findall(rf"\b{re.escape(phrase)}\b", text))


def detect_case_type(evidence: list[Evidence]) -> str:
    text = all_text(evidence)
    scores = {k: sum(_count_words(text, w) for w in words) for k, words in CASE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def detect_side(evidence: list[Evidence]) -> str:
    text = all_text(evidence)
    defense = sum(text.count(c) for c in DEFENSE_CUES)
    plaintiff = sum(text.count(c) for c in PLAINTIFF_CUES)
    return "defense" if defense > plaintiff else "plaintiff"


LANGUAGES = ["Spanish", "Vietnamese", "Tagalog", "Mandarin", "Cantonese", "Korean", "Arabic",
             "Hindi", "Tamil", "Portuguese", "Russian"]
NO_ENGLISH_CUES = ["don't speak english", "do not speak english", "don't speak much english",
                   "no english", "no hablo inglés", "no hablo ingles", "no hablo mucho inglés"]


def detect_languages(evidence: list[Evidence]) -> list[str]:
    """Languages the client speaks, from transcript titles ("originally in Spanish") and what
    they say about themselves. English is dropped only when they say they don't speak it."""
    found = []
    for ev in evidence:
        if ev.kind not in ("voice", "note"):
            continue                       # letters from insurers say nothing about the client
        blob = f"{ev.title} {ev.text}".lower()
        found += [lang for lang in LANGUAGES if lang.lower() in blob and lang not in found]
    english = not any(c in all_text(evidence) for c in NO_ENGLISH_CUES) or not found
    return found + (["English"] if english else [])


def detect_county(evidence: list[Evidence]) -> str | None:
    text = all_text(evidence)
    m = re.search(r"([a-z ]+?) county", text)
    if m:
        name = m.group(1).strip().split(",")[-1].strip().title()
        if name:
            return name
    for city, county in CITY_TO_COUNTY.items():
        if city in text:
            return county
    return None


def parse_date(text: str) -> date | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()


def incident_date(evidence: list[Evidence]) -> date | None:
    # Prefer official documents, then anything else.
    for ev in sorted(evidence, key=lambda e: e.kind != "document"):
        d = parse_date(ev.text)
        if d:
            return d
    return None


def _similar(a: str, b: str) -> bool:
    wa, wb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) > 0.5


def collect(evidence: list[Evidence], predicate) -> list[Fact]:
    facts: list[Fact] = []
    for ev in evidence:
        for s in sentences(ev):
            if not predicate(s):
                continue
            dupe = next((f for f in facts if _similar(f.text, s)), None)
            if dupe:
                if ev.id not in dupe.sources:
                    dupe.sources.append(ev.id)
                continue
            when = DATE_RE.search(s) or TIME_RE.search(s)
            facts.append(Fact(text=s, sources=[ev.id], when=when.group(0) if when else None))
    return facts


def missing_evidence(evidence: list[Evidence], case_type: str) -> list[str]:
    missing = []
    for label, kind, words in CHECKLIST.get(case_type, DEFAULT_CHECKLIST):
        pool = [e for e in evidence if kind is None or e.kind == kind]
        if label.startswith("Witness"):
            # A witness is only "covered" if we actually have a way to reach them.
            ok = any("witness" in s.lower() and CONTACT_RE.search(s) and "lost" not in s.lower()
                     for e in evidence for s in sentences(e))
        elif words:
            ok = any(w in f"{e.title} {e.text}".lower() for e in pool for w in words)
        else:
            ok = bool(pool)
        if not ok:
            missing.append(label)
    return missing


def deadlines(evidence: list[Evidence], case_type: str) -> list[dict]:
    """California general rules only. Shown as 'ask a lawyer to confirm', never as advice."""
    out = []
    start = incident_date(evidence)
    text = all_text(evidence)
    if start:
        def plus(years=0, months=0):
            m = start.month - 1 + months
            y = start.year + years + m // 12
            return start.replace(year=y, month=m % 12 + 1).isoformat()
        out.append({"label": "General personal-injury filing deadline (CA, 2 years)",
                    "date": plus(years=2), "basis": "Cal. Code Civ. Proc. § 335.1"})
        if case_type == "auto_accident":
            out.append({"label": "Property-damage filing deadline (CA, 3 years)",
                        "date": plus(years=3), "basis": "Cal. Code Civ. Proc. § 338"})
        if any(c in text for c in GOVERNMENT_CUES):
            out.append({"label": "Claim against a government entity (CA, 6 months)",
                        "date": plus(months=6), "basis": "Cal. Gov. Code § 911.2"})
    for ev in evidence:
        for s in sentences(ev):
            if re.search(r"\b(by|before|no later than)\b", s, re.I) and parse_date(s) and \
                    re.search(r"sign|return|respond|release", s, re.I):
                out.append({"label": f"Response requested in: {ev.title}",
                            "date": parse_date(s).isoformat(), "basis": f"[{ev.id}]"})
    return out


# The client asking us for a decision ("Should I sign?"). We answer honestly that we can't,
# and point to what we can do. Only the client's own words count (notes and voice memos).
ADVICE_QUESTION_RE = re.compile(
    r"\b(should i|do i have to|must i|is it (a )?good idea to) (sign|accept|settle|take|reject|sue)\b|"
    r"\bis (this|it|that) a (good|fair|bad) (offer|deal|settlement)\b|"
    r"\bhow much is my (case|claim) worth\b|"
    r"\b(debo|deber[ií]a) (firmar|aceptar)\b", re.I)


def warnings(evidence: list[Evidence]) -> list[str]:
    out = []
    for ev in evidence:
        if ev.kind in ("note", "voice") and ADVICE_QUESTION_RE.search(ev.text):
            out.append(f"You asked for a decision [{ev.id}]. CaseBridge can't answer that, because "
                       "it would be legal advice. What it can do: explain what the documents ask and "
                       "by when, and help you choose a lawyer to look at it first. Many offer a free "
                       "first consultation.")
    for ev in evidence:
        low = ev.text.lower()
        if "release" in low and ("settlement" in low or "sign" in low):
            out.append(f"A settlement release was found [{ev.id}]. Signing a release usually ends "
                       "the claim. This is a question to bring to a lawyer before signing.")
    return out


# --- Insurer-tactics alerts --------------------------------------------------------------
# Common moves in insurer letters and calls that stressed people agree to without knowing what
# they mean. Each alert explains the term in plain words and offers a question to bring to a
# lawyer. It never says what to do, so it stays on the right side of the no-advice rule.
# (The settlement-release warning lives in warnings() above, so it isn't repeated here.)

INSURER_TACTICS = [
    {"title": "Recorded statement requested",
     "cues": ["recorded statement", "record a statement", "record your statement",
              "grabar una declaración", "declaración grabada"],
     "meaning": "The insurer wants to record you describing what happened. A recording can be "
                "used later to question details of your claim.",
     "ask": "Do I have to give a recorded statement, and can a lawyer be present if I do?"},
    {"title": "\"Full and final\" settlement language",
     "cues": ["full and final", "final settlement", "all claims", "any and all claims"],
     "meaning": "An offer that would close every part of the claim, including injuries or costs "
                "that only show up later.",
     "ask": "Would this offer cover medical care I might still need?"},
    {"title": "Medical records authorization",
     "cues": ["medical authorization", "authorization to release", "hipaa", "all medical records",
              "complete medical history", "enclosed authorization"],
     "meaning": "A form that lets the insurer collect your medical history, sometimes far beyond "
                "this injury.",
     "ask": "Can the authorization be limited to this injury and this time period?"},
    {"title": "Suggestion that you share the blame",
     "cues": ["partly at fault", "partially at fault", "partly responsible", "share the fault",
              "shared fault", "comparative fault", "comparative negligence"],
     "meaning": "In California, a person's share of blame can reduce what a claim recovers, so this "
                "wording matters.",
     "ask": "How does shared fault work in California for a case like mine?"},
    {"title": "Pressure to decide quickly",
     "cues": ["resolve this quickly", "offer expires", "limited time", "today only", "act quickly",
              "respond immediately", "as soon as possible to receive"],
     "meaning": "Wording that pushes for a fast decision. Insurer deadlines are not the same as "
                "legal filing deadlines.",
     "ask": "Do I have to decide by this date, and can it be extended?"},
    {"title": "Suggestion that a lawyer isn't needed",
     "cues": ["don't need a lawyer", "do not need a lawyer", "don't need an attorney",
              "no need for an attorney", "no need for a lawyer", "without involving lawyers"],
     "meaning": "The insurer works for the other side. Many injury lawyers offer a free first "
                "consultation.",
     "ask": "Could a lawyer review this offer before I respond?"},
]
SHORT_WINDOW_DAYS = 45      # a response date this soon after the incident gets its own alert


def insurer_alerts(evidence: list[Evidence]) -> list[dict]:
    """Find insurer tactics in the evidence. Returns {"title", "meaning", "ask", "sources"}."""
    alerts = []
    for tactic in INSURER_TACTICS:
        sources = [e.id for e in evidence if any(c in e.text.lower() for c in tactic["cues"])]
        if sources:
            alerts.append({"title": tactic["title"], "meaning": tactic["meaning"],
                           "ask": tactic["ask"], "sources": sources})
    # A response deadline only weeks after the incident: injuries may not be fully known yet.
    start = incident_date(evidence)
    if start:
        for d in deadlines(evidence, "other"):
            if d["basis"].startswith("[E"):        # response dates found in a document
                days = (date.fromisoformat(d["date"]) - start).days
                if 0 <= days <= SHORT_WINDOW_DAYS:
                    alerts.append({
                        "title": f"Short response window ({days} days after the incident)",
                        "meaning": "Some injuries take weeks to be fully diagnosed. A decision this "
                                   "early may happen before the full cost of care is known.",
                        "ask": "Is it too early to know what this injury will cost?",
                        "sources": [d["basis"].strip("[]")]})
    return alerts


# --- Contradiction check -----------------------------------------------------------------
# Stressed people misremember, and forms get filled in wrong. When two pieces of evidence
# disagree on a key detail, a lawyer wants to know on day one, not at a deposition. We only
# compare things we can read reliably: the incident date and time, left/right body parts,
# and licence plates. Every finding cites the evidence on each side.

INCIDENT_CUES = re.compile(r"\b(collision|collided|crash|accident|hit|struck|rear-ended|fell|fall|"
                           r"slipped|tripped|bit|bitten|incident)\b", re.I)
BODY_SIDE_RE = re.compile(r"\b(left|right)\s+(knee|wrist|arm|leg|shoulder|ankle|hip|hand|foot|"
                          r"elbow|eye|ear|side|rib|ribs|thumb|finger)\b", re.I)
PLATE_RE = re.compile(r"\b\d[A-Z]{3}\d{3}\b")
TIME_TOLERANCE_MIN = 30     # "around 5:40 pm" vs "17:42" is the same moment


def _minutes(t: str) -> int | None:
    """'5:40 pm' / '17:42' / '9 pm' -> minutes after midnight."""
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t.strip(), re.I)
    if not m:
        return None
    h, mins, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    return h * 60 + mins


def _cite(found: dict) -> str:
    """{'October 2, 2026': ['E1', 'E4']} -> 'October 2, 2026 [E1, E4]; ...'"""
    return "; ".join(f"{value} [{', '.join(ids)}]" for value, ids in found.items())


def contradictions(evidence: list[Evidence]) -> list[dict]:
    """Key details that differ between evidence items. Returns {"topic", "text", "sources"}."""
    out = []
    dates: dict[str, list[str]] = {}
    times: dict[str, list[str]] = {}
    for ev in evidence:
        for s in sentences(ev):
            if not INCIDENT_CUES.search(s):
                continue
            d = parse_date(s)
            if d:
                dates.setdefault(f"{d:%B} {d.day}, {d.year}", []).append(ev.id)   # portable: no %-d
            t = TIME_RE.search(s)
            if t and ev.kind != "photo":         # photo captions describe when the photo was taken
                times.setdefault(t.group(0), []).append(ev.id)
    if len(dates) > 1:
        out.append({"topic": "Date of the incident",
                    "text": f"The evidence gives different dates for the incident: {_cite(dates)}.",
                    "sources": sorted({i for ids in dates.values() for i in ids})})
    mins = {t: _minutes(t) for t in times}
    valid = [m for m in mins.values() if m is not None]
    if valid and max(valid) - min(valid) > TIME_TOLERANCE_MIN:
        out.append({"topic": "Time of the incident",
                    "text": f"The evidence gives different times for the incident: {_cite(times)}.",
                    "sources": sorted({i for ids in times.values() for i in ids})})

    # Same body part on different sides in different documents ("right knee" vs "left knee").
    sides: dict[str, dict[str, list[str]]] = {}
    for ev in evidence:
        for side, part in BODY_SIDE_RE.findall(ev.text):
            sides.setdefault(part.lower(), {}).setdefault(side.lower(), [])
            if ev.id not in sides[part.lower()][side.lower()]:
                sides[part.lower()][side.lower()].append(ev.id)
    for part, by_side in sides.items():
        if len(by_side) > 1:
            left, right = set(by_side["left"]), set(by_side["right"])
            if left != right and not (left & right):   # both sides in one document is not a conflict
                found = {f"{side} {part}": ids for side, ids in by_side.items()}
                out.append({"topic": f"Injured {part}: left or right?",
                            "text": f"The evidence disagrees about which {part} was injured: {_cite(found)}.",
                            "sources": sorted(left | right)})

    plates: dict[str, list[str]] = {}
    for ev in evidence:
        for p in PLATE_RE.findall(ev.text):
            plates.setdefault(p, []).append(ev.id)
    if len(plates) > 1:
        out.append({"topic": "Licence plate",
                    "text": f"More than one plate number appears: {_cite(plates)}. "
                            "Check which vehicle each one belongs to.",
                    "sources": sorted({i for ids in plates.values() for i in ids})})
    return out


# --- How to get missing evidence ------------------------------------------------------------
# Practical, general steps for each checklist item. Information, not legal advice, and worded
# for a stressed person. Keys match the labels in CHECKLIST / DEFAULT_CHECKLIST.

EVIDENCE_TIPS = {
    "Police / collision report": "Ask the police department that came to the scene for a copy. "
        "Many offer online requests; the report number speeds it up.",
    "Photos of the scene or vehicles": "Photograph the vehicles before repairs, and the place it "
        "happened if it is safe to go back.",
    "Photos of the hazard": "If it is safe, photograph the spot again and anything that is still "
        "there, like a missing warning sign.",
    "Photos": "Photograph your injuries every few days as they change, and anything that was "
        "damaged.",
    "Medical records": "Ask each clinic or hospital for your records and an itemized bill. "
        "You have a right to a copy of your own records.",
    "Written repair estimate": "Ask the body shop for a written, itemized estimate, even if you "
        "haven't decided on repairs.",
    "Other driver's insurance details": "The police report often lists the other driver's "
        "insurer. Keep every letter they send.",
    "Witness contact information": "Write down anyone who saw it. Nearby businesses may have "
        "cameras, but footage is often erased within days, so ask soon.",
    "Proof of lost wages (pay stubs / employer letter)": "Keep your pay stubs, or ask your "
        "employer for a short letter listing the days you missed and your pay.",
    "Request to keep the security camera footage": "Ask the store or property in writing, soon, "
        "to keep the camera video of that day. Many systems erase it within days or weeks.",
    "Photos of the injuries": "Photograph the bite or wound every few days as it heals.",
    "Animal control or bite report": "Ask your city or county animal control for a copy of the "
        "bite report. Clinics often file one automatically.",
    "Dog owner's name and contact details": "Write down the owner's name and how to reach them, "
        "and the dog's name if you know it.",
    "Dog's vaccination records": "Animal control can usually confirm whether the dog's rabies "
        "vaccination is current. Tell your doctor what you learn.",
    "Incident report from the property": "Ask the store or property manager in writing for a "
        "copy. Write down who you asked and when, even if they say no.",
}


def how_to_get(label: str) -> str | None:
    """General steps for collecting one missing item, or None if we have no tip for it."""
    return EVIDENCE_TIPS.get(label)


def build_brief(evidence: list[Evidence]) -> CaseBrief:
    case_type = detect_case_type(evidence)
    side = detect_side(evidence)
    county = detect_county(evidence)
    timeline = collect(evidence, lambda s: bool(DATE_RE.search(s) or TIME_RE.search(s)))
    timeline.sort(key=lambda f: (parse_date(f.text) or date.max, f.text))
    brief = CaseBrief(
        case_type=case_type,
        client_side=side,
        county=county,
        summary="",
        timeline=timeline,
        parties=collect(evidence, lambda s: any(w in s.lower() for w in PARTY_WORDS)),
        injuries=collect(evidence, lambda s: any(w in s.lower() for w in INJURY_WORDS)
                         and "settlement" not in s.lower()),
        damages=collect(evidence, lambda s: "$" in s),
        missing_evidence=missing_evidence(evidence, case_type),
        deadlines=deadlines(evidence, case_type),
        warnings=warnings(evidence),
        alerts=insurer_alerts(evidence),
        contradictions=contradictions(evidence),
    )
    when = incident_date(evidence)
    brief.summary = (
        f"Potential {side} matter: {case_type.replace('_', ' ')}"
        f"{' on ' + when.strftime('%B %d, %Y') if when else ''}"
        f"{' in ' + county + ' County' if county else ''}. "
        f"{len(evidence)} pieces of evidence, {len(brief.injuries)} injury-related facts, "
        f"{len(brief.missing_evidence)} items a lawyer will likely ask for are missing."
    )
    return brief
