"""Turn uploaded files and typed notes into Evidence items with stable ids."""
from __future__ import annotations

import io
import os
from pathlib import Path

from .models import Evidence

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEMO_DIR = DATA_DIR / "demo_case"
DEMO_CASES = {
    "maria": DEMO_DIR,                       # rear-end crash, San Jose
    "rosa": DATA_DIR / "demo_case_rosa",     # slip and fall in a grocery store, Fremont
}

# Whisper language codes -> names used by matching (lawyers.json "languages").
LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "vi": "Vietnamese", "tl": "Tagalog", "zh": "Mandarin",
    "ko": "Korean", "ar": "Arabic", "hi": "Hindi", "ta": "Tamil", "pt": "Portuguese", "ru": "Russian",
}
_whisper_model = None
_whisper_error: Exception | None = None   # remembered so a missing model doesn't stall every upload


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[PDF text extraction unavailable: pip install pypdf]"
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _load_whisper():
    """Load faster-whisper once. Model size via WHISPER_MODEL (default "base")."""
    global _whisper_model, _whisper_error
    if _whisper_error is not None:
        raise _whisper_error
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel(os.environ.get("WHISPER_MODEL", "base"),
                                          device="cpu", compute_type="int8")
        except Exception as exc:
            _whisper_error = exc
            raise
    return _whisper_model


def transcribe(data: bytes, file_name: str = "audio.m4a") -> tuple[str, str | None]:
    """Voice memo -> (English text, detected language name).

    Runs locally with faster-whisper, so audio never leaves the machine. Non-English speech is
    translated to English, because the rules engine and lawyers read English; the detected
    language is kept so matching can find a lawyer who speaks it.

    If info.language_probability < 0.5 the language is treated as unknown (None).
    When the detected language is not English a second task="transcribe" pass keeps the
    original-language transcript and appends it to the text under an "Original (<Language>):"
    line, so the brief can reproduce what the client actually said.

    Never raises: if Whisper is missing or fails, returns a placeholder and None so the
    client can type the transcript instead.
    """
    try:
        model = _load_whisper()
    except Exception as exc:  # not installed, or model not downloaded and no network
        return f"[Automatic transcription unavailable ({type(exc).__name__}). Please type what the memo says.]", None
    try:  # decoded in memory, so the audio is never written to disk
        segments, info = model.transcribe(io.BytesIO(data), task="translate", vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as exc:
        return f"[Could not transcribe this audio ({type(exc).__name__}). Please type what it says.]", None

    # Treat low-confidence language detection as unknown.
    if getattr(info, "language_probability", 1.0) < 0.5:
        return text or "[No speech detected in this recording.]", None

    language = LANGUAGE_NAMES.get(info.language, info.language)

    # For non-English audio, append the original-language transcript so the brief preserves
    # exactly what the client said (useful for lawyers who share that language).
    if language != "English":
        try:
            orig_segments, _ = model.transcribe(io.BytesIO(data), task="transcribe", vad_filter=True)
            orig_text = " ".join(seg.text.strip() for seg in orig_segments).strip()
            if orig_text:
                label = f"Original ({language}):"
                text = f"{text}\n{label} {orig_text}" if text else f"{label} {orig_text}"
        except Exception:
            pass  # original-language pass is best-effort; never raises

    return text or "[No speech detected in this recording.]", language


def voice_evidence(data: bytes, file_name: str) -> Evidence:
    """Build a voice Evidence item. The title records the original language, which the brief
    uses to set the client's languages (see brief.build)."""
    text, language = transcribe(data, file_name)
    if language is None and text.startswith("["):
        title = f"Voice memo {file_name} (needs a typed transcript)"
    elif language is None:
        title = f"Voice memo {file_name} (transcribed, language unclear)"
    elif language == "English":
        title = f"Voice memo {file_name} (transcribed)"
    else:
        title = f"Voice memo {file_name} (transcribed, originally in {language})"
    return Evidence(id="", kind="voice", title=title, text=text, file_name=file_name)


def kind_for(file_name: str) -> str:
    ext = Path(file_name).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".heic", ".webp"}:
        return "photo"
    if ext in {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".opus", ".webm"}:
        return "voice"
    if ext in {".pdf", ".doc", ".docx"}:
        return "document"
    return "note"


def number(items: list[Evidence]) -> list[Evidence]:
    for i, ev in enumerate(items, start=1):
        ev.id = f"E{i}"
    return items


def load_demo_case(name: str = "maria") -> list[Evidence]:
    """A fictional demo case from data/. "maria": voice memo, photos, police report, insurer
    letter. "rosa": Spanish voice memo, store incident report, urgent care, adjuster text."""
    items = []
    for path in sorted(DEMO_CASES[name].glob("*.txt")):
        header, _, body = path.read_text(encoding="utf-8").partition("\n---\n")
        meta = dict(line.split(": ", 1) for line in header.strip().splitlines())
        items.append(Evidence(id="", kind=meta["kind"], title=meta["title"],
                              text=body.strip(), file_name=meta.get("file")))
    return number(items)
