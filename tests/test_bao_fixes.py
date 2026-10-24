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


def _deadline_dates(text):
    ev = [Evidence(id="E1", kind="document", title="Police report", text=text)]
    return {d["basis"]: d["date"] for d in rules.deadlines(ev, "auto_accident")}


def test_month_end_incident_gets_the_last_day_of_the_month():
    # A city bus makes the 6-month government claim apply. There is no February 31.
    d = _deadline_dates("Date: August 31, 2026. A city bus hit my car. I have neck pain.")
    assert d["Cal. Gov. Code § 911.2"] == "2027-02-28"
    assert d["Cal. Code Civ. Proc. § 335.1"] == "2028-08-31"


def test_leap_day_incident_does_not_crash():
    d = _deadline_dates("Date: February 29, 2028. I was rear-ended. I have neck pain.")
    assert d["Cal. Code Civ. Proc. § 335.1"] == "2030-02-28"
    assert d["Cal. Code Civ. Proc. § 338"] == "2031-02-28"


def test_summary_counts_read_naturally():
    s = rules.build_brief(load_demo_case("bao")).summary
    assert "1 item a lawyer will likely ask for is missing" in s
    assert "October 14, 2026" in s
    maria = rules.build_brief(load_demo_case("maria")).summary
    assert "October 2, 2026" in maria and "3 items a lawyer will likely ask for are missing" in maria


def test_bare_form_time_is_not_a_timeline_row():
    texts = [f.text for f in rules.build_brief(load_demo_case("bao")).timeline]
    assert "Time: 08:53." not in texts
    rosa = [f.text for f in rules.build_brief(load_demo_case("rosa")).timeline]
    assert any("10:30" in t for t in rosa)   # a time inside a real sentence stays


def _split(text):
    return rules.sentences(Evidence(id="E1", kind="note", title="t", text=text))


def test_street_abbreviation_mid_sentence_does_not_split():
    assert _split("I was on Oak St. near the park. Then it happened.") == [
        "I was on Oak St. near the park.", "Then it happened."]
    assert _split("421 Oak St. The accident was there.") == ["421 Oak St.", "The accident was there."]


def test_lawyer_directory_is_cached_but_each_caller_gets_a_copy():
    from casebridge import matching
    first = matching.load_lawyers()
    first[0]["name"] = "changed"
    assert matching.load_lawyers()[0]["name"] != "changed"
    assert any("español" in str(l) for l in matching.load_lawyers())   # read as UTF-8


def test_offers_with_different_amounts_are_not_merged():
    from casebridge.ingest import load_trick_letter, number
    ev = number(load_demo_case("bao") + [load_trick_letter()])
    damages = rules.build_brief(ev).damages
    assert [f.sources for f in damages] == [["E5"], ["E6"]]
    assert rules._similar("I hurt my neck on October 2.", "I hurt my neck on October 2!")
