# scripts/photo_to_text_test.py
# Standalone test: photo of a document -> extracted text, via Claude's vision API.
# Requires: pip install anthropic
# Requires: export ANTHROPIC_API_KEY="your-key-here"

import base64
import sys
from pathlib import Path

import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


def extract_text_from_photo(image_path: str) -> str:
    image_bytes = Path(image_path).read_bytes()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    # Guess media type from extension (good enough for a quick test)
    ext = Path(image_path).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    # TODO (yours to write/tune): this prompt decides what gets extracted
    # and how well it lines up with rules.py's checklist keywords
    # (e.g. ["police","collision report"], ["diagnosis","discharge","medical"], etc.)
    prompt = "Transcribe all the text visible in this photo of a document, as accurately and completely as possible, preserving the original structure (headers, dates, names, numbers) exactly as written. If any part is blurry, cut off, or illegible, say so explicitly rather than guessing what it might say. Output only the transcribed text."

    response = client.messages.create(
        model="claude-sonnet-5-5",
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
    return ""  # no text block found


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/photo_to_text_test.py <path-to-image>")
        sys.exit(1)
    print(extract_text_from_photo(sys.argv[1]))
