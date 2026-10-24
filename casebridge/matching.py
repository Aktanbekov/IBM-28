"""Match a case to lawyers. Hard filters first (practice area, which side they represent),
then an explainable fit score. No case 'value' is ever computed or shown."""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

LAWYERS_FILE = Path(__file__).resolve().parent.parent / "data" / "lawyers.json"


@lru_cache(maxsize=1)
def _lawyers_from_disk() -> tuple[dict, ...]:
    # utf-8 explicitly: Windows would otherwise read "español" in the reviews as "espaÃ±ol".
    return tuple(json.loads(LAWYERS_FILE.read_text(encoding="utf-8")))


def load_lawyers() -> list[dict]:
    """The lawyer directory, read from disk once. Each call gets its own copy, so a caller
    that edits a profile can't change what the next caller sees."""
    return copy.deepcopy(list(_lawyers_from_disk()))


def speaks_with(client_languages: list[str], lawyer_languages: list[str]) -> bool:
    """Language is a hard filter only when the client doesn't speak English: a lawyer they
    can't talk to can't take their case. Bilingual clients see everyone, Spanish speakers ranked up."""
    if not client_languages or "English" in client_languages:
        return True
    return any(l in lawyer_languages for l in client_languages)


def match(case_type: str, side: str, county: str | None, languages: list[str],
          lawyers: list[dict] | None = None) -> tuple[list[dict], dict]:
    lawyers = lawyers if lawyers is not None else load_lawyers()
    results, excluded = [], {"practice_area": 0, "side": 0, "language": 0}
    unclear = case_type == "other"      # e.g. only an insurer letter: don't leave the client with nobody
    for lw in lawyers:
        if not unclear and case_type not in lw["practice_areas"]:
            excluded["practice_area"] += 1
            continue
        if side not in lw["sides"]:
            excluded["side"] += 1
            continue
        if not speaks_with(languages, lw["languages"]):
            excluded["language"] += 1
            continue
        area = ("Handles injury cases (confirm your case type to narrow this list)" if unclear
                else f"Handles {case_type.replace('_', ' ')} cases")
        score, why = 5.0, [area, f"Represents the {side} side"]
        if county and county in lw["counties"]:
            score += 3
            why.append(f"Practices in {county} County")
        shared = [l for l in languages if l in lw["languages"] and l != "English"]
        if shared:
            score += 2
            why.append(f"Speaks {', '.join(shared)}")
        score += lw["rating"] - 4          # small nudge for reviews, never dominant
        if lw.get("free_consultation"):
            why.append("Free first consultation")
        results.append({**lw, "fit_score": round(score, 1), "why": why})
    results.sort(key=lambda r: (-r["fit_score"], -r["rating"]))
    return results, excluded
