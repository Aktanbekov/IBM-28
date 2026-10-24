"""Turn uploaded files and typed notes into Evidence items with stable ids."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

from .models import Evidence

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo_case"


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[PDF text extraction unavailable: pip install pypdf]"
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def kind_for(file_name: str) -> str:
    ext = Path(file_name).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".heic", ".webp"}:
        return "photo"
    if ext in {".mp3", ".m4a", ".wav", ".ogg"}:
        return "voice"
    if ext in {".pdf", ".doc", ".docx"}:
        return "document"
    return "note"


def photo_text(data: bytes, file_name: str) -> tuple[str, str]:
    """Run two-pass Claude analysis on a photo.

    Pass 1 – verbatim OCR of all visible text.
    Pass 2 – legal-relevance filter; returns structured JSON.

    Returns (text, kind) where kind is "document" if the photo contains a
    legible structured document, otherwise "photo".

    Falls back to ("[photo uploaded, no description yet]", "photo") when
    ANTHROPIC_API_KEY is not set, so offline / rules mode still works.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "[photo uploaded, no description yet]", "photo"

    try:
        import anthropic
    except ImportError:
        return "[photo uploaded — pip install anthropic for auto-analysis]", "photo"

    client = anthropic.Anthropic(api_key=api_key)
    model = "claude-sonnet-5-5"

    # --- Pass 1: verbatim OCR ---
    ext = Path(file_name).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    image_b64 = base64.standard_b64encode(data).decode("utf-8")

    ocr_prompt = (
        "Transcribe all the text visible in this photo of a document, as accurately and "
        "completely as possible, preserving the original structure (headers, dates, names, "
        "numbers) exactly as written. If any part is blurry, cut off, or illegible, say so "
        "explicitly rather than guessing what it might say. Output only the transcribed text."
    )
    ocr_resp = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": ocr_prompt},
            ],
        }],
    )
    raw = next((b.text for b in ocr_resp.content if b.type == "text"), "")
    if not raw.strip():
        return "[photo: no text detected]", "photo"

    # --- Pass 2: legal-relevance analysis ---
    analysis_system = (
        "You are a legal intake assistant. You read raw text extracted from accident-scene "
        "photos or document photos and pull out only the facts that matter to a "
        "personal-injury lawyer.\n\n"
        "Rules you must follow without exception:\n"
        "- Output ONLY valid JSON that matches the schema below. No prose before or after.\n"
        "- Never predict outcomes, give legal advice, or estimate case value.\n"
        "- Use null for any field you cannot find. Use [] for empty lists.\n"
        "- 'legally_relevant_facts' must be plain, factual sentences only (3-8 bullets).\n"
        "- 'items_not_extracted' should name categories of noise you deliberately dropped.\n"
        "- Set 'is_legible_document' to true only when the image clearly shows a readable "
        "structured document (police report, medical record, insurance letter, repair "
        "estimate, court filing, etc.). Set it to false for scene/damage photos."
    )
    schema = {
        "source_description": "string",
        "is_legible_document": "boolean",
        "date": "string | null",
        "time": "string | null",
        "location": "string | null",
        "parties": [{"role": "string", "name": "string | null", "contact": "string | null",
                     "plate": "string | null", "insurance": "string | null"}],
        "vehicle_damage": [{"vehicle_description": "string", "damage_description": "string"}],
        "injuries": [{"person": "string | null", "description": "string"}],
        "damages": [{"label": "string", "amount": "string"}],
        "legally_relevant_facts": ["string"],
        "items_not_extracted": "string | null",
    }
    analysis_prompt = (
        f"Here is the raw text transcribed from a photo:\n\n---\n{raw}\n---\n\n"
        f"Fill in the following JSON schema with only the legally relevant facts.\n"
        f"Schema:\n{json.dumps(schema, indent=2)}"
    )
    analysis_resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=analysis_system,
        messages=[{"role": "user", "content": analysis_prompt}],
    )
    analysis_raw = next((b.text for b in analysis_resp.content if b.type == "text"), "")
    analysis_raw = analysis_raw.strip()
    if analysis_raw.startswith("```"):
        analysis_raw = analysis_raw.split("```")[1]
        if analysis_raw.startswith("json"):
            analysis_raw = analysis_raw[4:]
    try:
        analysis = json.loads(analysis_raw.strip())
    except json.JSONDecodeError:
        # If JSON parsing fails, keep the raw OCR text
        return raw, "photo"

    # --- Upgrade: build final text and decide kind ---
    facts = analysis.get("legally_relevant_facts") or []
    if analysis.get("is_legible_document"):
        kind = "document"
        lines = [analysis.get("source_description", "Extracted document.")]
        if analysis.get("date"):
            lines.append(f"Date: {analysis['date']}.")
        if analysis.get("time"):
            lines.append(f"Time: {analysis['time']}.")
        if analysis.get("location"):
            lines.append(f"Location: {analysis['location']}.")
        for p in analysis.get("parties") or []:
            parts = [p.get("role", "Party")]
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
            lines.append(f"Damages: {dmg.get('label', '')}: {dmg.get('amount', '')}.")
        lines.extend(facts)
        text = " ".join(lines)
    else:
        kind = "photo"
        text = " ".join(facts) if facts else raw

    return text, kind


def number(items: list[Evidence]) -> list[Evidence]:
    for i, ev in enumerate(items, start=1):
        ev.id = f"E{i}"
    return items


def load_demo_case() -> list[Evidence]:
    """Maria's case: a rambling voice memo, photos, police report, insurer letter."""
    items = []
    for path in sorted(DEMO_DIR.glob("*.txt")):
        header, _, body = path.read_text().partition("\n---\n")
        meta = dict(line.split(": ", 1) for line in header.strip().splitlines())
        items.append(Evidence(id="", kind=meta["kind"], title=meta["title"],
                              text=body.strip(), file_name=meta.get("file")))
    return number(items)
