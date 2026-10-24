"""Fixes found while reviewing Bao's demo case (Vietnamese-speaking pedestrian, San Jose)."""
from casebridge import rules, safety
from casebridge.ingest import load_demo_case
from casebridge.models import Evidence


def _bao():
    ev = load_demo_case("bao")
    return ev, safety.find_names([e.text for e in ev])


def test_accented_name_is_redacted_in_the_vietnamese_original():
    ev, names = _bao()
    out = safety.redact(ev[0].text, names)
    for part in ("Nguyễn", "Thị", "Bảo"):
        assert part not in out
    assert "Original (Vietnamese)" in out   # the rest of the line survives


def test_accent_insensitive_names_work_both_ways():
    names = {"Martínez": "[CLIENT]", "Bao": "[CLIENT]"}
    assert safety.redact("Rosa Martinez and Bảo", names) == "Rosa [CLIENT] and [CLIENT]"
    assert safety.find_leaks("note from Bảo", {"Bao": "[CLIENT]"}) == ["Bao"]


def test_pedestrian_is_not_asked_for_a_repair_estimate():
    ev, _ = _bao()
    assert rules.on_foot(ev)
    assert "Written repair estimate" not in rules.missing_evidence(ev, "auto_accident")


def test_driver_is_still_asked_for_a_repair_estimate():
    ev = load_demo_case("maria")
    assert not rules.on_foot(ev)
    assert "Written repair estimate" in rules.missing_evidence(ev, "auto_accident")


def test_pedestrian_with_own_car_damaged_still_gets_the_estimate_item():
    ev = [Evidence(id="E1", kind="voice", title="memo",
                   text="I was in the crosswalk. Afterwards the driver backed into my car too.")]
    assert not rules.on_foot(ev)
    assert "Written repair estimate" in rules.missing_evidence(ev, "auto_accident")


def test_every_data_file_is_utf8():
    """A demo file saved in another encoding on Windows breaks accented-name redaction."""
    from casebridge.ingest import DATA_DIR
    for path in DATA_DIR.rglob("*"):
        if path.is_file() and path.suffix in {".txt", ".json", ".md"}:
            path.read_bytes().decode("utf-8")


def _county(text):
    return rules.detect_county([Evidence(id="E1", kind="document", title="t", text=text)])


def test_county_is_read_from_the_list_of_california_counties():
    assert _county("Fremont is in Alameda County.") == "Alameda"
    assert _county("Superior Court, County of Contra Costa") == "Contra Costa"
    assert _county("Filed in San Luis Obispo County") == "San Luis Obispo"


def test_county_vehicle_is_not_a_county_name():
    # Used to return "A". Now it falls through to the city lookup.
    assert _county("I was hit by a county vehicle in Oakland.") == "Alameda"
    assert _county("I was hit by a county vehicle.") is None
