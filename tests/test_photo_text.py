"""Photo reading (OpenAI vision, optional): it must never crash the upload and never send GPS out."""
import io
import json

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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    text, kind = ingest.photo_text(_jpeg_with_gps(), "scene.jpg")
    assert text.startswith("[") and kind == "photo"


def test_api_failure_never_crashes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    def down(req, timeout=60):
        raise ConnectionError("wifi down")
    monkeypatch.setattr(ingest.urllib.request, "urlopen", down)
    text, kind = ingest.photo_text(_jpeg_with_gps(), "scene.jpg")
    assert text == "[photo could not be read automatically (ConnectionError)]" and kind == "photo"


def test_document_photo_is_read_and_sent_without_gps(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    replies = iter(["TRAFFIC COLLISION REPORT. Date: October 2, 2026.",
                    json.dumps({"source_description": "Photo of a police report.", "is_legible_document": True,
                                "date": "October 2, 2026", "legally_relevant_facts": ["Vehicle 2 struck Vehicle 1."]})])
    sent = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=60):
        sent.append(json.loads(req.data))
        return Reply(json.dumps({"choices": [{"message": {"content": next(replies)}}]}).encode())
    monkeypatch.setattr(ingest.urllib.request, "urlopen", fake_urlopen)
    text, kind = ingest.photo_text(_jpeg_with_gps(), "report.jpg")
    assert kind == "document" and "October 2, 2026" in text and "Vehicle 2 struck Vehicle 1." in text
    image_url = sent[0]["messages"][0]["content"][0]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    import base64
    assert not ingest.photo_metadata(base64.b64decode(image_url.split(",", 1)[1])).get("gps")


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
