# scripts/photo_analysis_test.py
# Two-pass pipeline:
#   Pass 1  – extract_text_from_photo()  : raw transcription (verbatim OCR)
#   Pass 2  – analyze_photo_text()       : structured legal-relevance analysis
#
# The second pass fills a fixed form and returns JSON.
# If the photo turns out to contain a legible document the Evidence kind is
# promoted from "photo" to "document".
#
# Requires: pip install anthropic
# Requires: export ANTHROPIC_API_KEY="your-key-here"
#
# Usage:
#   python scripts/photo_analysis_test.py <path-to-image>

import base64
import json
import sys
from pathlib import Path

import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

# ---------------------------------------------------------------------------
# Pass 1 – verbatim transcription (unchanged from photo_to_text_test.py)
# ---------------------------------------------------------------------------


def extract_text_from_photo(image_path: str) -> str:
    image_bytes = Path(image_path).read_bytes()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    ext = Path(image_path).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    prompt = (
        "Transcribe all the text visible in this photo of a document, as accurately and "
        "completely as possible, preserving the original structure (headers, dates, names, "
        "numbers) exactly as written. If any part is blurry, cut off, or illegible, say so "
        "explicitly rather than guessing what it might say. Output only the transcribed text."
    )

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


# ---------------------------------------------------------------------------
# Pass 2 – structured legal-relevance analysis
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM = """\
You are a legal intake assistant. You read raw text extracted from accident-scene photos or \
document photos and pull out only the facts that matter to a personal-injury lawyer.

Rules you must follow without exception:
- Output ONLY valid JSON that matches the schema below. No prose before or after.
- Never predict outcomes, give legal advice, or estimate case value.
- Use null for any field you cannot find. Use [] for empty lists.
- "legally_relevant_facts" must be plain, factual sentences only (3–8 bullets).
- "items_not_extracted" should name categories of noise you deliberately dropped.
- Set "is_legible_document" to true only when the image clearly shows a readable \
  structured document (police report, medical record, insurance letter, repair estimate, \
  court filing, etc.). Set it to false for scene/damage photos where no document is visible.
"""

ANALYSIS_SCHEMA = {
    "source_description": "string — one sentence describing what this photo/document appears to be",
    "is_legible_document": "boolean — true if photo shows a readable structured document",
    "date": "string | null — date visible in the image, e.g. 'October 2, 2026'",
    "time": "string | null — time visible in the image, e.g. '5:42 PM'",
    "location": "string | null — address, intersection, or city/state visible",
    "parties": [
        {
            "role": "string — e.g. driver, witness, officer, insurer",
            "name": "string | null",
            "contact": "string | null — phone or email",
            "plate": "string | null — license plate",
            "insurance": "string | null — insurer name or policy number",
        }
    ],
    "vehicle_damage": [
        {
            "vehicle_description": "string — year/make/model/color if known",
            "damage_description": "string",
        }
    ],
    "injuries": [
        {
            "person": "string | null",
            "description": "string",
        }
    ],
    "damages": [
        {
            "label": "string — what the dollar amount refers to",
            "amount": "string — e.g. '$4,200'",
        }
    ],
    "legally_relevant_facts": ["string — plain factual sentence"],
    "items_not_extracted": "string | null — categories of text deliberately omitted",
}


def analyze_photo_text(raw_text: str) -> dict:
    """Pass 2: ask Claude to fill the legal-relevance form from the raw transcription."""
    prompt = (
        f"Here is the raw text transcribed from a photo:\n\n"
        f"---\n{raw_text}\n---\n\n"
        f"Fill in the following JSON schema with only the legally relevant facts. "
        f"Schema:\n{json.dumps(ANALYSIS_SCHEMA, indent=2)}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            # Strip markdown code fences if the model wraps the JSON
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
    return {}


# ---------------------------------------------------------------------------
# Evidence upgrader
# ---------------------------------------------------------------------------

def upgrade_evidence(raw_text: str, analysis: dict, original_kind: str = "photo") -> dict:
    """
    Decide the final kind and text for the Evidence item.

    - If is_legible_document is True  → kind becomes "document", text becomes
      a compact prose summary built from the structured fields.
    - Otherwise                       → kind stays "photo", text becomes the
      bullet list of legally_relevant_facts (much shorter than verbatim OCR).
    """
    facts = analysis.get("legally_relevant_facts") or []

    if analysis.get("is_legible_document"):
        kind = "document"
        # Build a compact, structured prose block that rules.py can parse with
        # its existing date/keyword/sentence regexes.
        lines = [analysis.get("source_description", "Extracted document.")]
        if analysis.get("date"):
            lines.append(f"Date: {analysis['date']}.")
        if analysis.get("time"):
            lines.append(f"Time: {analysis['time']}.")
        if analysis.get("location"):
            lines.append(f"Location: {analysis['location']}.")
        for p in analysis.get("parties") or []:
            parts = [f"{p.get('role', 'Party')}"]
            if p.get("name"):
                parts.append(p["name"])
            if p.get("plate"):
                parts.append(f"plate {p['plate']}")
            if p.get("insurance"):
                parts.append(f"insured by {p['insurance']}")
            if p.get("contact"):
                parts.append(p["contact"])
            lines.append(", ".join(parts) + ".")
        for vd in analysis.get("vehicle_damage") or []:
            lines.append(f"Damage: {vd.get('vehicle_description', 'vehicle')} — "
                         f"{vd.get('damage_description', '')}.")
        for inj in analysis.get("injuries") or []:
            who = inj.get("person") or "Unknown person"
            lines.append(f"Injury ({who}): {inj.get('description', '')}.")
        for dmg in analysis.get("damages") or []:
            lines.append(
                f"Damages: {dmg.get('label', '')}: {dmg.get('amount', '')}.")
        lines.extend(facts)
        text = " ".join(lines)
    else:
        kind = original_kind  # stays "photo"
        text = " ".join(facts) if facts else raw_text

    return {"kind": kind, "text": text}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/photo_analysis_test.py <path-to-image>")
        sys.exit(1)

    image_path = sys.argv[1]
    print("=== Pass 1: raw transcription ===")
    raw = extract_text_from_photo(image_path)
    print(raw)

    print("\n=== Pass 2: structured analysis ===")
    analysis = analyze_photo_text(raw)
    print(json.dumps(analysis, indent=2))

    print("\n=== Evidence upgrade result ===")
    result = upgrade_evidence(raw, analysis)
    print(f"kind : {result['kind']}")
    print(f"text :\n{result['text']}")
