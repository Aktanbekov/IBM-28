"""Turn uploaded files and typed notes into Evidence items with stable ids."""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path

from .models import Evidence
from .safety import clean_speech

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEMO_DIR = DATA_DIR / "demo_case"
DEMO_CASES = {
    "maria": DEMO_DIR,                       # rear-end crash, San Jose
    "rosa": DATA_DIR / "demo_case_rosa",     # slip and fall in a grocery store, Fremont
    "bao": DATA_DIR / "demo_case_bao",       # pedestrian hit in crosswalk, San Jose
}

# Whisper language codes -> names used by matching (lawyers.json "languages").
LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "vi": "Vietnamese", "tl": "Tagalog", "zh": "Mandarin",
    "ko": "Korean", "ar": "Arabic", "hi": "Hindi", "ta": "Tamil", "pt": "Portuguese", "ru": "Russian",
}
# Choices for "Which language will you speak?" in the app, each shown in its own language.
# Telling Whisper the language skips auto-detection, which often guesses wrong on short
# recordings (and then the original-language transcript is lost).
SPOKEN_LANGUAGES = {
    "Detect automatically": None, "English": "en", "Español (Spanish)": "es",
    "Tiếng Việt (Vietnamese)": "vi", "中文 (Mandarin)": "zh", "Tagalog": "tl", "한국어 (Korean)": "ko",
    "العربية (Arabic)": "ar", "हिन्दी (Hindi)": "hi", "தமிழ் (Tamil)": "ta", "Português (Portuguese)": "pt",
    "Русский (Russian)": "ru",
}
_whisper_model = None
_whisper_error: Exception | None = None   # remembered so a missing model doesn't stall every upload


MAX_PDF_PAGES = 50   # a brief needs a few pages; a 5,000-page upload would stall the app


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[PDF text extraction unavailable: pip install pypdf]"
    try:   # a damaged, encrypted or hostile PDF must not crash the app
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:MAX_PDF_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages).strip()
    except Exception as exc:
        return f"[Could not read this PDF ({type(exc).__name__}). Please type what it says.]"
    if len(reader.pages) > MAX_PDF_PAGES:
        text += f"\n[Only the first {MAX_PDF_PAGES} pages were read.]"
    return text or "[No text found in this PDF. If it is a scan, please type what it says.]"


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


def transcribe(data: bytes, file_name: str = "audio.m4a",
               language: str | None = None) -> tuple[str, str | None]:
    """Voice memo -> (English text, detected language name).

    language is a Whisper code ("es", "vi") chosen by the client, or None to auto-detect.

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
    lang_arg = {"language": language} if language else {}   # only passed when the client chose one
    try:  # decoded in memory, so the audio is never written to disk
        segments, info = model.transcribe(io.BytesIO(data), task="translate", vad_filter=True, **lang_arg)
        text = " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as exc:
        return f"[Could not transcribe this audio ({type(exc).__name__}). Please type what it says.]", None

    # Treat low-confidence language detection as unknown (not needed when the client chose it).
    if not language and getattr(info, "language_probability", 1.0) < 0.5:
        return text or "[No speech detected in this recording.]", None

    code = language or info.language
    language = LANGUAGE_NAMES.get(code, code)

    # For non-English audio, append the original-language transcript so the brief preserves
    # exactly what the client said (useful for lawyers who share that language).
    if language != "English":
        try:
            orig_segments, _ = model.transcribe(io.BytesIO(data), task="transcribe", vad_filter=True,
                                                language=code)
            orig_text = " ".join(seg.text.strip() for seg in orig_segments).strip()
            if orig_text:
                label = f"Original ({language}):"
                text = f"{text}\n{label} {orig_text}" if text else f"{label} {orig_text}"
        except Exception:
            pass  # original-language pass is best-effort; never raises

    return text or "[No speech detected in this recording.]", language


def voice_evidence(data: bytes, file_name: str, language: str | None = None) -> Evidence:
    """Build a voice Evidence item. The title records the original language, which the brief
    uses to set the client's languages (see brief.build). language: see transcribe()."""
    text, language = transcribe(data, file_name, language)
    if not text.startswith("["):   # a lawyer reads the facts, not the "um"s and swearing
        text = clean_speech(text)[0] or "[No usable speech in this recording.]"
    if language is None and text.startswith("["):
        title = f"Voice memo {file_name} (needs a typed transcript)"
    elif language is None:
        title = f"Voice memo {file_name} (transcribed, language unclear)"
    elif language == "English":
        title = f"Voice memo {file_name} (transcribed)"
    else:
        title = f"Voice memo {file_name} (transcribed, originally in {language})"
    return Evidence(id="", kind="voice", title=title, text=text, file_name=file_name)


# --- Photo metadata -----------------------------------------------------------------------
# Phone photos carry EXIF data: when the photo was taken, and often the exact GPS spot. The
# time helps the timeline (a photo taken minutes after the crash backs up the story). The GPS
# spot can reveal where someone lives, so it is written in a form the redactor recognizes and
# it never reaches a lawyer before the client accepts them. strip_metadata() removes all of it
# from the image itself, for whenever a photo file is shared.

EXIF_IFD, GPS_IFD = 0x8769, 0x8825          # pointers to the Exif and GPS sub-directories
DATETIME_ORIGINAL, DATETIME = 36867, 306    # "taken at" (camera), then "file changed" (fallback)


def _gps_degrees(dms, ref) -> float:
    """EXIF stores (degrees, minutes, seconds) as rationals; S and W are negative."""
    deg = float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600
    return -deg if str(ref).upper() in ("S", "W") else deg


def photo_metadata(data: bytes) -> dict:
    """Read {"taken": datetime | None, "gps": (lat, lon) | None} from a photo. Never raises:
    screenshots, edited photos and formats Pillow can't open simply return no metadata."""
    meta = {"taken": None, "gps": None}
    try:
        from PIL import Image
        exif = Image.open(io.BytesIO(data)).getexif()
        raw = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(DATETIME)
        if raw:
            meta["taken"] = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
        gps = exif.get_ifd(GPS_IFD)
        if gps.get(2) and gps.get(4):       # 1/2 = latitude ref/value, 3/4 = longitude ref/value
            meta["gps"] = (round(_gps_degrees(gps[2], gps.get(1, "N")), 4),
                           round(_gps_degrees(gps[4], gps.get(3, "E")), 4))
    except Exception:
        pass
    return meta


def photo_note(meta: dict) -> str:
    """Plain-language line added to a photo's evidence text. The date is written the way the
    rules engine reads dates, so the photo lands in the timeline."""
    parts = []
    if meta.get("taken"):
        t = meta["taken"]
        hour = t.strftime("%I:%M %p").lstrip("0").lower()
        parts.append(f"Photo taken {t:%B} {t.day}, {t.year} at {hour} (from the photo's metadata).")
    if meta.get("gps"):
        lat, lon = meta["gps"]
        parts.append(f"The photo also recorded a GPS location ({lat:.4f}, {lon:.4f}). "
                     "Lawyers won't see it unless you accept them.")
    return " ".join(parts)


def strip_metadata(data: bytes) -> bytes:
    """Return the same picture with EXIF (time, GPS, phone model) removed. Pillow only writes
    metadata it finds in .info or is handed, so clearing .info and re-saving drops it. Unreadable files come back as-is."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        fmt = img.format or "PNG"
        clean = img.copy()          # pixels only; drop exif, GPS, text chunks and comments
        clean.info.clear()
        out = io.BytesIO()
        clean.save(out, format=fmt)
        return out.getvalue()
    except Exception:
        return data


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


def _read_evidence_file(path: Path) -> Evidence:
    """One demo file: "key: value" header lines, a "---" line, then the evidence text."""
    header, _, body = path.read_text(encoding="utf-8").partition("\n---\n")
    meta = dict(line.split(": ", 1) for line in header.strip().splitlines())
    return Evidence(id="", kind=meta["kind"], title=meta["title"], text=body.strip(),
                    file_name=meta.get("file"))


def load_demo_case(name: str = "maria") -> list[Evidence]:
    """A fictional demo case from data/. "maria": voice memo, photos, police report, insurer
    letter. "rosa": Spanish voice memo, store incident report, urgent care, adjuster text.
    "bao": Vietnamese-speaking pedestrian, police report, ER summary, insurer letter."""
    return number([_read_evidence_file(p) for p in sorted(DEMO_CASES[name].glob("*.txt"))])


TRICK_LETTER = DATA_DIR / "demo_extras" / "trick_letter.txt"


def load_trick_letter() -> Evidence:
    """A fictional insurer letter with instructions for an AI hidden in an HTML comment, to add
    to any case in the demo. CaseBridge flags it, ignores the instructions, and blocks the
    advice it asks for. The caller numbers it: ingest.number(evidence + [load_trick_letter()])."""
    return _read_evidence_file(TRICK_LETTER)
