"""Shared store: one board for every browser window; the full brief is stored only after the client accepts."""
from casebridge import matching, store

SEED = [{"id": "C-1031", "case_type": "auto_accident", "client_side": "plaintiff", "county": "Alameda",
         "posted": "2026-10-22", "languages": ["English"], "summary": "Seed case.", "missing_evidence": [],
         "connect_requests": [], "connected": []}]


def test_lawyers_come_from_the_store_and_match_the_json():
    store.init(SEED)
    lawyers = matching.load_lawyers()
    assert len(lawyers) == 24 and lawyers[0]["id"] == "L1" and lawyers[-1]["id"] == "L24"


def test_two_sessions_share_one_board_and_consent_gates_the_brief():
    store.init(SEED)
    cid = store.add_case({"case_type": "auto_accident", "client_side": "plaintiff", "county": "Santa Clara",
                          "posted": "2026-10-23", "summary": "[CLIENT] was rear-ended."}, owner="client-window")
    lawyer_view = {c["id"]: c for c in store.list_cases(owner="lawyer-window")}
    assert cid in lawyer_view and not lawyer_view[cid]["mine"] and lawyer_view[cid]["shared_brief"] is None

    store.request_connect(cid, "L1")
    mine = {c["id"]: c for c in store.list_cases(owner="client-window")}[cid]
    assert mine["mine"] and mine["connect_requests"] == ["L1"]

    store.accept(cid, "L1", {"summary": "Maria Lopez was rear-ended.", "parties": []})
    case = {c["id"]: c for c in store.list_cases()}[cid]
    assert case["connected"] == ["L1"] and case["shared_brief"]["summary"].startswith("Maria")


def test_board_is_newest_first_never_by_value():
    store.init(SEED)
    store.add_case({"case_type": "premises", "client_side": "plaintiff", "posted": "2026-10-24",
                    "summary": "Newest."}, owner="x")
    posted = [c["posted"] for c in store.list_cases()]
    assert posted == sorted(posted, reverse=True)


def test_delete_removes_case_requests_and_shared_brief():
    store.init(SEED)
    cid = store.add_case({"case_type": "auto_accident", "client_side": "plaintiff", "posted": "2026-10-23",
                          "summary": "To delete."}, owner="o")
    store.request_connect(cid, "L2")
    store.accept(cid, "L2", {"summary": "full", "parties": []})
    store.delete_case(cid)
    assert cid not in {c["id"] for c in store.list_cases()}


def test_matching_falls_back_to_json_if_the_store_fails(monkeypatch):
    monkeypatch.setattr(store, "load_lawyers", lambda: (_ for _ in ()).throw(OSError("disk")))
    assert len(matching.load_lawyers()) == 24
