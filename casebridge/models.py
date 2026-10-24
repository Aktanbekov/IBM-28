"""Core data types. Every fact in a brief carries the evidence ids it came from."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Evidence:
    id: str            # "E1", "E2", ...
    kind: str          # note | voice | photo | document
    title: str
    text: str          # extracted text, transcript, or photo caption
    file_name: str | None = None


@dataclass
class Fact:
    text: str
    sources: list[str]  # evidence ids, e.g. ["E1", "E3"]
    when: str | None = None


@dataclass
class CaseBrief:
    case_type: str                  # key into PRACTICE_AREAS
    client_side: str                # "plaintiff" | "defense"
    county: str | None
    summary: str
    timeline: list[Fact] = field(default_factory=list)
    parties: list[Fact] = field(default_factory=list)
    injuries: list[Fact] = field(default_factory=list)
    damages: list[Fact] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    deadlines: list[dict] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["English"])
    warnings: list[str] = field(default_factory=list)
    engine: str = "rules"

    def to_dict(self) -> dict:
        return asdict(self)


PRACTICE_AREAS = {
    "auto_accident": "Car / auto accident",
    "premises": "Slip & fall / premises liability",
    "dog_bite": "Dog bite",
    "workplace": "Workplace injury",
    "medical": "Medical malpractice",
    "other": "Other / unclear",
}
