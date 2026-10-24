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
    "medical": ["surgery", "misdiagnos", "doctor made", "malpractice", "wrong medication"],
}
DEFENSE_CUES = ["i hit", "i rear-ended", "suing me", "sued me", "lawsuit against me",
                "claim against me", "my fault", "i ran the light"]
PLAINTIFF_CUES = ["hit me", "struck vehicle 1", "rear-ended me", "hit from behind",
                  "bit me", "i was injured", "his insurance", "her insurance"]
INJURY_WORDS = ["pain", "whiplash", "strain", "fracture", "broken bone", "concussion",
                "bruise", "emergency room", "diagnosis", "physical therapy", "injur"]
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
        ("Medical records", "document", ["diagnosis", "discharge", "medical"]),
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
    parts = re.split(r"(?<!\bMs)(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<=[.!?])\s+", ev.text)
    return [s.strip() for s in parts if s.strip()]


def all_text(evidence: list[Evidence]) -> str:
    return " ".join(e.text for e in evidence).lower()


def detect_case_type(evidence: list[Evidence]) -> str:
    text = all_text(evidence)
    scores = {k: sum(text.count(w) for w in words) for k, words in CASE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def detect_side(evidence: list[Evidence]) -> str:
    text = all_text(evidence)
    defense = sum(text.count(c) for c in DEFENSE_CUES)
    plaintiff = sum(text.count(c) for c in PLAINTIFF_CUES)
    return "defense" if defense > plaintiff else "plaintiff"


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


def warnings(evidence: list[Evidence]) -> list[str]:
    out = []
    for ev in evidence:
        low = ev.text.lower()
        if "release" in low and ("settlement" in low or "sign" in low):
            out.append(f"A settlement release was found [{ev.id}]. Signing a release usually ends "
                       "the claim. This is a question to bring to a lawyer before signing.")
    return out


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
