"""Turn uploaded files and typed notes into Evidence items with stable ids."""
from __future__ import annotations

import io
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
