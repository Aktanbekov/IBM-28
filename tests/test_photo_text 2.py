"""Photo reading (Claude vision, optional): it must never crash the upload and never send GPS out."""
import io
import sys
import types

from PIL import Image

from casebridge import ingest


def _jpeg_with_gps() -> bytes:
    img, exif = Image.new("RGB", (40, 30), "white"), Image.Exif()
    exif[0x0132] = "2026:10:02 17:44:00"                              # DateTime
    exif[0x8825] = {1: "N", 2: (37.0, 19.0, 12.0), 3: "W", 4: (121.0, 57.0, 3.0)}   # GPS
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_no_key_means_placeholder(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text, kind = ingest.photo_text(_jpeg_with_gps(), "scene.jpg")
    assert text.startswith("[") and kind == "photo"


def test_api_failure_never_crashes(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    fake = types.ModuleType("anthropic")
    class Client:
        def __init__(self, **kw):
            self.messages = self
        def create(self, **kw):
            raise ConnectionError("wifi down")
    fake.Anthropic = Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    text, kind = ingest.photo_text(_jpeg_with_gps(), "scene.jpg")
    assert text == "[photo could not be read automatically (ConnectionError)]" and kind == "photo"


def test_photo_is_sent_without_gps():
    data = _jpeg_with_gps()
    assert ingest.photo_metadata(data).get("gps")
    sent, media_type = ingest._image_for_upload(data)
    assert media_type == "image/jpeg"
    assert not ingest.photo_metadata(sent).get("gps")


def test_other_formats_are_converted_to_png():
    out = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(out, format="BMP")
    assert ingest._image_for_upload(out.getvalue())[1] == "image/png"
