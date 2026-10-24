"""Shared store: the lawyer directory, posted (anonymized) cases and connect requests, in one SQLite
file. Standard library only. Every browser window reads the same file, so a client and a lawyer in
two windows see the same board.

What is stored, and when:
  * lawyers: the fictional profiles from data/lawyers.json, re-synced on every start.
  * cases: only what the client chose to post, already redacted (safety.redact_brief).
  * the client's full brief: only after they accept a lawyer, for that lawyer to read.
delete_case removes the case, its requests and the shared brief.

The file is data/casebridge.db (git-ignored); CASEBRIDGE_DB points somewhere else (tests use a temp file).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LAWYERS_FILE = DATA_DIR / "lawyers.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lawyers (id TEXT PRIMARY KEY, profile TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    posted TEXT NOT NULL,          -- the board is ordered by this, never by value
    owner TEXT,                    -- the browser session that posted it; NULL for the seeded demo cases
    data TEXT NOT NULL,            -- the anonymized case (JSON)
    shared_brief TEXT              -- the full brief, set only when the client accepts a lawyer
);
CREATE TABLE IF NOT EXISTS requests (
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lawyer_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'connected')),
    PRIMARY KEY (case_id, lawyer_id)
);
"""


def db_path() -> Path:
    return Path(os.getenv("CASEBRIDGE_DB", DATA_DIR / "casebridge.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(seed_cases: list[dict] = ()) -> None:
    """Create the tables, sync the lawyer directory from lawyers.json, and add the demo cases once."""
    with closing(_connect()) as conn, conn:
        conn.executescript(SCHEMA)
        lawyers = json.loads(LAWYERS_FILE.read_text(encoding="utf-8"))
        conn.execute("DELETE FROM lawyers")
        conn.executemany("INSERT INTO lawyers VALUES (?, ?)",
                         [(l["id"], json.dumps(l, ensure_ascii=False)) for l in lawyers])
        for case in seed_cases:
            data = {k: v for k, v in case.items() if k not in ("connect_requests", "connected")}
            conn.execute("INSERT OR IGNORE INTO cases (id, posted, owner, data) VALUES (?, ?, NULL, ?)",
                         (case["id"], case["posted"], json.dumps(data, ensure_ascii=False)))


def load_lawyers() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT profile FROM lawyers ORDER BY CAST(SUBSTR(id, 2) AS INTEGER)").fetchall()
    return [json.loads(r[0]) for r in rows]


def list_cases(owner: str | None = None) -> list[dict]:
    """Every posted case, newest first, with its connect_requests / connected lawyer ids.
    `mine` is set on the cases this browser session posted."""
    with closing(_connect()) as conn:
        cases = conn.execute("SELECT id, owner, data, shared_brief FROM cases ORDER BY posted DESC, id DESC").fetchall()
        reqs = conn.execute("SELECT case_id, lawyer_id, status FROM requests ORDER BY rowid").fetchall()
    out = []
    for cid, case_owner, data, shared in cases:
        case = json.loads(data)
        case["connect_requests"] = [l for c, l, s in reqs if c == cid and s == "requested"]
        case["connected"] = [l for c, l, s in reqs if c == cid and s == "connected"]
        case["mine"] = owner is not None and case_owner == owner
        case["shared_brief"] = json.loads(shared) if shared else None
        out.append(case)
    return out


def add_case(case: dict, owner: str) -> str:
    """Post an anonymized case. The id is the next free C-number."""
    with closing(_connect()) as conn, conn:
        n = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        case_id = f"C-{1040 + n}"
        while conn.execute("SELECT 1 FROM cases WHERE id = ?", (case_id,)).fetchone():
            n += 1
            case_id = f"C-{1040 + n}"
        data = {k: v for k, v in case.items() if k not in ("connect_requests", "connected", "mine", "shared_brief")}
        data["id"] = case_id
        conn.execute("INSERT INTO cases (id, posted, owner, data) VALUES (?, ?, ?, ?)",
                     (case_id, data["posted"], owner, json.dumps(data, ensure_ascii=False)))
    return case_id


def request_connect(case_id: str, lawyer_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO requests VALUES (?, ?, 'requested')", (case_id, lawyer_id))


def accept(case_id: str, lawyer_id: str, full_brief: dict | None = None) -> None:
    """The client accepts a lawyer. Only now is their full brief stored, for the lawyers they accepted."""
    with closing(_connect()) as conn, conn:
        conn.execute("UPDATE requests SET status = 'connected' WHERE case_id = ? AND lawyer_id = ?",
                     (case_id, lawyer_id))
        if full_brief is not None:
            conn.execute("UPDATE cases SET shared_brief = ? WHERE id = ?",
                         (json.dumps(full_brief, ensure_ascii=False), case_id))


def delete_case(case_id: str) -> None:
    """Remove a posted case, its connect requests and any shared brief."""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM requests WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
