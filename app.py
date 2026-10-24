"""CaseBridge MVP: messy evidence in -> cited case brief -> matched lawyers -> anonymized lawyer board.

Run: streamlit run app.py
"""
from __future__ import annotations

import copy
import html
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import streamlit as st

from casebridge import brief as brief_agent
from casebridge import ingest, llm, matching, rules, safety, scoreboard, store
from casebridge.models import CaseBrief, Evidence, Fact, PRACTICE_AREAS

st.set_page_config(page_title="CaseBridge", page_icon=":material/edit_note:", layout="wide")

SEED_BOARD = [
    {"id": "C-1031", "case_type": "auto_accident", "client_side": "plaintiff", "county": "Alameda",
     "posted": "2026-10-22", "languages": ["English"],
     "summary": "Pedestrian struck in a crosswalk by a turning rideshare vehicle. ER visit, wrist fracture "
                "[E3]. Police report and dashcam footage available [E1, E2].",
     "missing_evidence": ["Witness contact information"], "connect_requests": [], "connected": []},
    {"id": "C-1029", "case_type": "auto_accident", "client_side": "defense", "county": "Santa Clara",
     "posted": "2026-10-21", "languages": ["English", "Vietnamese"],
     "summary": "Client received a complaint after a low-speed parking-lot collision; disputes fault [E1]. "
                "Has photos of both vehicles [E2].",
     "missing_evidence": ["Police / collision report"], "connect_requests": [], "connected": []},
    {"id": "C-1024", "case_type": "premises", "client_side": "plaintiff", "county": "San Mateo",
     "posted": "2026-10-20", "languages": ["Spanish"],
     "summary": "Slipped on an unmarked wet floor in a grocery store; knee injury and physical therapy "
                "[E1, E4]. Store incident report requested [E2].",
     "missing_evidence": ["Witness contact information"], "connect_requests": [], "connected": []},
]

PAGES = ["1 · Tell us what happened", "2 · Your case brief", "3 · Find a lawyer", "Lawyer portal"]
# One highlighter colour per evidence id (E1, E2, ...), cycling. Colour only ever means "this came from that source".
HIGHLIGHTERS = ["#FFE45C", "#FF9FD0", "#9AF0B3", "#9ADCFF", "#D4C2FF", "#FFC9A3"]
KIND_ICONS = {"voice": "mic", "photo": "photo_camera", "document": "description", "note": "edit_note"}
SIDE_LABELS = {"plaintiff": "I was harmed (making a claim)", "defense": "Someone is claiming against me"}
SIDE_PLAIN = {"plaintiff": "people who were harmed", "defense": "people facing a claim"}

ss = st.session_state
ss.setdefault("evidence", [])
ss.setdefault("brief", None)
ss.setdefault("board", [dict(c) for c in SEED_BOARD])
ss.setdefault("sent_to", [])
ss.setdefault("my_case_id", None)
ss.setdefault("hidden", set())     # statements the client chose to hide from lawyers (safety.fact_key)
ss.setdefault("last_mic_id", None) # id of the last mic recording already added, to avoid re-processing
ss.setdefault("toast", None)       # a one-off message to show after the next rerun
ss.setdefault("owner", uuid.uuid4().hex)   # marks the cases this browser session posted, in the shared store


@st.cache_resource
def shared_store_ready() -> bool:
    """Create the shared database once per server. False -> fall back to a per-session board."""
    try:
        store.init(SEED_BOARD)
        return True
    except Exception:
        return False


# --- look and feel ---------------------------------------------------------------------

def _svg(path: str, fill: str) -> str:
    return ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E"
            f"%3Cpath d='{path}' fill='{fill.replace('#', '%23')}'/%3E%3C/svg%3E\")")


CHECK = "M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"
BRIEFCASE = ("M20 6h-4V4c0-1.1-.9-2-2-2h-4c-1.1 0-2 .9-2 2v2H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 "
             "2-.9 2-2V8c0-1.1-.9-2-2-2zm-6 0h-4V4h4v2z")

CSS = """
::selection{background:#FFE45C;color:#1E2230}
.cb-brand{font-size:1.5rem;font-weight:700;letter-spacing:-.01em;color:#fff;margin:0}
.cb-tagline{font-size:.85rem;line-height:1.45;color:#DCE3FA;margin:.25rem 0 0}
.cb-foot{font-size:.8rem;line-height:1.5;color:#DCE3FA}
.cb-foot b{color:#fff}
.cb-lead{font-size:1.0625rem;line-height:1.55;color:#1E2230;max-width:48rem;margin:0}
.cb-meta{font-size:.9rem;line-height:1.5;color:#4A5068;margin:0}
.cb-label{font-size:.95rem;font-weight:700;color:#1E2230;margin:0 0 .35rem}
.cb-h{font-size:1.3rem;font-weight:700;line-height:1.3;color:#1E2230;margin:.9rem 0 .1rem;padding:0}
.cb-chip{display:inline-block;padding:.15rem .55rem;border-radius:3px;background:#F0F3FC;color:#2A4BB8;
  border:1px solid #2A4BB8;font-size:.85rem;font-weight:700}
.cb-empty{font-size:.95rem;color:#4A5068;margin:.25rem 0}
.cb-tag{display:inline-block;margin-left:.4rem;padding:0 .4rem;border-radius:2px;font-size:.75rem;font-weight:700;
  line-height:1.4rem;color:#1E2230;white-space:nowrap;font-variant-numeric:tabular-nums}
.cb-tag:first-child{margin-left:0}
.cb-flag,.cb-unchecked{display:inline-block;margin-left:.4rem;padding:0 .45rem;border-radius:2px;font-size:.75rem;
  font-weight:700;line-height:1.25rem;white-space:nowrap;vertical-align:.05em;background:#fff}
.cb-flag{border:1.5px solid #1E2230;color:#1E2230}
.cb-unchecked{border:1px dashed #8A90A6;color:#4A5068}
.cb-flagged{text-decoration:underline wavy #1E2230;text-decoration-thickness:1px;text-underline-offset:.28em;
  text-decoration-skip-ink:none}
.cb-removed{text-decoration:line-through;text-decoration-thickness:1.5px;color:#4A5068}
.cb-caught{display:block;font-size:.85rem;color:#4A5068;margin-top:.1rem}
.cb-caught b{color:#1E2230}
.cb-list.cb-checks li{grid-template-columns:1.1rem 9rem 1fr;gap:.85rem;align-items:start}
.cb-check-name{font-weight:700}
.cb-check-detail{font-size:.9rem;color:#4A5068}
.cb-mark{width:1.1rem;height:1.1rem;margin-top:.15rem}
.cb-mark.pass{background:CHECK_BLUE center/contain no-repeat}
.cb-mark.flag{background:#1E2230;border-radius:2px;color:#fff;font-size:.75rem;font-weight:700;line-height:1.1rem;
  text-align:center}
.cb-mark.skip{height:0;margin-top:.7rem;border-top:2px solid #8A90A6}
.cb-check-foot{font-size:.9rem;color:#4A5068;margin:.35rem 0 0;padding-top:.6rem;border-top:1px solid #E3E5EC}
.cb-check-foot b{color:#1E2230}
.st-key-checks h3.cb-h{margin-top:.1rem}
[data-testid="stTabs"] [role="tab"] p{font-size:1rem;font-weight:700}
[data-testid="stTabs"] [role="tablist"]{gap:1.75rem}
.cb-trust{display:flex;flex-wrap:wrap;gap:.35rem 1.5rem;font-size:.95rem;color:#4A5068;margin:.6rem 0 .15rem}
.cb-trust b{color:#1E2230;font-variant-numeric:tabular-nums}
.cb-list.cb-data li{grid-template-columns:1fr;gap:.1rem}
.cb-lawyer{font-size:.9rem;color:#4A5068;margin:0 0 .3rem}
.cb-lawyer b{font-size:1.15rem;color:#1E2230;margin-right:.6rem}
.cb-why.cb-why-row{display:flex;flex-wrap:wrap;gap:.1rem 1.25rem;margin:0 0 .25rem}
.st-key-data h3.cb-h{margin-top:.1rem}
.cb-redact{display:inline-block;padding:0 .4rem;border-radius:2px;background:#1E2230;color:#fff;font-size:.72rem;
  font-weight:700;letter-spacing:.03em;line-height:1.35rem;white-space:nowrap}
ul.cb-list,ul.cb-why{list-style:none;margin:0;padding:0 !important}
.cb-list li{display:grid;grid-template-columns:1fr;gap:1rem;padding:.6rem 0;border-bottom:1px solid #E3E5EC;
  font-size:.95rem;line-height:1.5;color:#1E2230}
.cb-list li:last-child{border-bottom:0}
.cb-list.cb-dated li{grid-template-columns:7.25rem 1fr}
.cb-list.cb-stack li{grid-template-columns:1fr;gap:.1rem}
.cb-date{font-size:.85rem;font-weight:700;color:#4A5068;font-variant-numeric:tabular-nums;padding-top:.1rem}
.cb-date small{display:block;font-size:.78rem;font-weight:700}
.cb-urgent{color:#B42318}
.cb-basis{display:block;font-size:.85rem;color:#4A5068}
.cb-checklist li{grid-template-columns:1.1rem 1fr;gap:.75rem}
.cb-checklist li::before{content:"";width:1rem;height:1rem;margin-top:.2rem;border:1.5px solid #4A5068;border-radius:2px}
.cb-why li{display:flex;gap:.5rem;align-items:flex-start;font-size:.95rem;line-height:1.5;padding:.15rem 0}
.cb-why li::before{content:"";flex:none;width:1.1rem;height:1.1rem;margin-top:.15rem;
  background:CHECK_BLUE center/contain no-repeat}
.cb-notice{padding:.75rem 1rem;font-size:.95rem;line-height:1.55;color:#1E2230;border-top:2px solid #2A4BB8;
  background:#F0F3FC}
.cb-notice > b:first-child{display:block;margin-bottom:.15rem}
.cb-notice.cb-time{border-top-color:#B42318;background:#FDF3F1}
.cb-notice.cb-time b{color:#B42318}
.cb-notice.cb-note{border-top-color:#8A90A6;background:#F3F4F8}
.cb-notice.cb-safety{border-top-color:#1E2230;background:#F3F4F8}
.cb-notice.cb-state b{display:inline;margin:0}
.cb-source-head{display:flex;gap:.6rem;align-items:center;font-size:.9rem;color:#4A5068;margin-bottom:.5rem}
.cb-source{font-size:.92rem;line-height:1.65;color:#2C3142;white-space:pre-wrap;margin:0}
.cb-source mark{color:#1E2230;padding:.05rem .1rem;border-radius:2px}
.cb-strip{display:flex;flex-wrap:wrap;gap:.35rem 1.5rem;font-size:.9rem;color:#4A5068}
.cb-strip b{color:#1E2230}
.cb-case-head{display:flex;flex-wrap:wrap;align-items:center;gap:.3rem .9rem;font-size:.9rem;color:#4A5068}
.cb-case-head .cb-date{padding:0;font-size:.9rem;color:#1E2230}
.cb-case-head strong{color:#1E2230}
.st-key-confirm{border:1.5px solid #1E2230 !important}
.cb-stamp{display:inline-block;margin:.2rem 0 .5rem;padding:.15rem .7rem;border:3px solid #B42318;border-radius:4px;
  color:#B42318;font-weight:800;letter-spacing:.12em;font-size:1rem;transform:rotate(-4deg);
  animation:cb-slam .45s cubic-bezier(.2,1.6,.4,1) both}
@keyframes cb-slam{from{transform:scale(2.4) rotate(-12deg);opacity:0}to{transform:scale(1) rotate(-4deg);opacity:1}}
.cb-hidden-instr{background:#FDE2DE;outline:2px solid #B42318;border-radius:2px}
.st-key-score [data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
.cb-swap s{display:inline-block;max-width:30em;overflow:hidden;white-space:nowrap;vertical-align:bottom;
  text-decoration-color:#B42318;animation:cb-out .5s ease-in forwards;animation-delay:var(--d)}
.cb-swap .cb-redact{opacity:0;animation:cb-in .35s ease-out forwards;animation-delay:calc(var(--d) + .35s)}
@keyframes cb-out{60%{opacity:1;max-width:30em}to{opacity:0;max-width:0}}
@keyframes cb-in{from{opacity:0;transform:scale(.6)}to{opacity:1;transform:scale(1)}}
.cb-reveal{font-size:.95rem;line-height:1.9;color:#1E2230;margin:.35rem 0;padding:.35rem 0;border-bottom:1px solid #E3E5EC}

.st-key-nav [role="radiogroup"]{gap:.2rem;counter-reset:step}
.st-key-nav [role="radiogroup"] > div{counter-increment:step;width:100%}
.st-key-nav [data-testid="stRadioOption"]{width:100%;padding:.5rem .55rem;border-radius:4px;cursor:pointer}
.st-key-nav [data-testid="stRadioOption"]:hover{background:#2341A3}
.st-key-nav [data-testid="stRadioOption"] > div > div:first-child{display:none}
.st-key-nav [data-testid="stRadioOption"] p{display:flex;align-items:center;gap:.7rem;font-size:.95rem;color:#E4E9FB}
.st-key-nav [data-testid="stRadioOption"] p::before{content:counter(step);flex:none;width:1.5rem;height:1.5rem;
  border-radius:50%;border:1.5px solid #C3CDF5;display:grid;place-items:center;font-size:.75rem;font-weight:700;
  color:#fff;background:transparent center/.95rem no-repeat}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p{color:#1E2230;font-weight:700;width:fit-content;
  padding-right:.45rem;background:linear-gradient(transparent 8%,#FFE45C 8%,#FFE45C 92%,transparent 92%)
  right center/calc(100% - 1.85rem) 100% no-repeat}
[data-testid="stSidebarUserContent"]{min-height:calc(100vh - 5rem);display:flex;flex-direction:column}
[data-testid="stSidebarUserContent"] > div{flex:1;display:flex;flex-direction:column}
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]{flex:1}
[data-testid="stLayoutWrapper"]:has(> .st-key-railfoot){margin-top:auto}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p::before{background-color:#1E2230;
  border-color:#1E2230;color:#FFE45C}
.st-key-nav [role="radiogroup"] > div:nth-child(4){margin-top:1rem;padding-top:1rem;border-top:1px solid #4D68C6}
.st-key-nav [role="radiogroup"] > div:nth-child(4) p::before{content:"";border:0;border-radius:0;
  background-image:BRIEFCASE_WHITE}
.st-key-nav [role="radiogroup"] > div:nth-child(4) [data-selected="true"] p::before{background-color:transparent;
  background-image:BRIEFCASE_INK}
""".replace("CHECK_BLUE", _svg(CHECK, "#2A4BB8")) \
   .replace("BRIEFCASE_WHITE", _svg(BRIEFCASE, "#FFFFFF")) \
   .replace("BRIEFCASE_INK", _svg(BRIEFCASE, "#1E2230"))


def style(css: str):
    st.html(f"<style>{css}</style>")


def nav_progress_css() -> str:
    """Tick off the client steps that are done (evidence added, brief built, brief sent or case posted)."""
    done = [bool(ss.evidence), bool(ss.brief), bool(ss.sent_to or ss.my_case_id)]
    return "".join(
        f'.st-key-nav [role="radiogroup"] > div:nth-child({i}) [data-testid="stRadioOption"]'
        f':not([data-selected="true"]) p::before{{content:"";background-color:#fff;border-color:#fff;'
        f'background-image:{_svg(CHECK, "#2A4BB8")}}}'
        for i, ok in enumerate(done, 1) if ok)


# --- helpers ---------------------------------------------------------------------------

esc = html.escape
TOKEN_RE = re.compile(r"\[([^\[\]]+)\]")
EVIDENCE_ID_RE = re.compile(r"E\d+")
MONTH_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b")


def highlighter(eid: str) -> str:
    n = int(eid[1:]) if EVIDENCE_ID_RE.fullmatch(eid) else 1
    return HIGHLIGHTERS[(n - 1) % len(HIGHLIGHTERS)]


def tag(eid: str) -> str:
    return f'<span class="cb-tag" style="background:{highlighter(eid)}">{esc(eid)}</span>'


def flag_label(flag: str) -> str:
    """Engine flag text -> the reviewer's margin note: "⚠ Not grounded in [E1]" -> "Not supported by E1"."""
    text = flag.removeprefix("⚠").strip().replace("[", "").replace("]", "")
    return (text.replace("Summary not grounded in evidence", "Not supported by the evidence")
                .replace("Not grounded in", "Not supported by"))


def guardian_tags(flags: list) -> str:
    """Fact-check marks: an ink-outlined note for a problem (flags starting ⚠), a dashed one for "Not checked".
    Not highlighter colours: those only ever mean "this came from that source"."""
    return "".join(f'<span class="{"cb-flag" if str(f).startswith("⚠") else "cb-unchecked"}">'
                   f'{esc(flag_label(str(f)))}</span>' for f in flags)


def flagged(text_html: str, flags: list) -> str:
    """A wavy pen underline under a statement a check flagged, the way a reviewer marks a draft."""
    return f'<span class="cb-flagged">{text_html}</span>' if any(str(f).startswith("⚠") for f in flags) else text_html


def rich(text: str) -> str:
    """Escape text, turn [E1, E2] into evidence tags and [CLIENT]-style tokens into redaction marks."""
    def swap(m: re.Match) -> str:
        inner = m.group(1)
        ids = [p.strip() for p in inner.split(",")]
        if all(EVIDENCE_ID_RE.fullmatch(i) for i in ids):
            return "".join(tag(i) for i in ids)
        if inner == inner.upper() and any(ch.isalpha() for ch in inner):
            return f'<span class="cb-redact">{inner}</span>'
        return m.group(0)
    return TOKEN_RE.sub(swap, esc(text))


def short_date(text: str) -> str:
    return re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", MONTH_RE.sub(lambda m: m.group(1)[:3], text))


def fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def lead(text: str):
    st.html(f'<p class="cb-lead">{rich(text)}</p>')


def label(text: str):
    st.html(f'<p class="cb-label">{esc(text)}</p>')


def meta(text: str):
    """Secondary text that still has to be read (sources, rules, what is hidden), so not a faint caption."""
    st.html(f'<p class="cb-meta">{esc(text)}</p>')


def days_until(iso: str) -> int:
    return (date.fromisoformat(iso) - date.today()).days


def heading(text: str):
    st.html(f'<h3 class="cb-h">{esc(text)}</h3>')


def state_note(body: str):
    """A status line in the house style (pen-blue rule). `body` is trusted HTML built by the caller."""
    st.html(f'<div class="cb-notice cb-state">{body}</div>')


def show_facts(title: str, facts: list, dated: bool = False):
    heading(title)
    facts = [f if isinstance(f, dict) else f.__dict__ for f in facts]
    if not facts:
        st.html('<p class="cb-empty">Nothing found in the evidence.</p>')
        return
    rows = []
    for f in facts:
        tags = "".join(tag(s) for s in f["sources"])
        flags = f.get("guardian_flags") or []
        text, gflags = flagged(rich(f["text"]), flags), guardian_tags(flags)
        if dated:
            rows.append(f'<li><span class="cb-date">{esc(short_date(f.get("when") or ""))}</span>'
                        f'<span>{text} {tags}{gflags}</span></li>')
        else:
            when = f'<b>{esc(f["when"])}</b> · ' if f.get("when") else ""
            rows.append(f'<li><span>{when}{text} {tags}{gflags}</span></li>')
    st.html(f'<ul class="cb-list{" cb-dated" if dated else ""}">{"".join(rows)}</ul>')


def lawyer_card(lw: dict):
    """One matched lawyer. Practice area and side are true of every card, so they are said once above the
    list; the card shows only what else fits this case (county, language, free consultation)."""
    with st.container(border=True, key=f"lawyer_{lw['id']}"):
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        with c1:
            extra = lw["why"][2:]
            st.html(f'<p class="cb-lawyer"><b>{esc(lw["name"])}</b>{esc(lw["firm"])} · {lw["years"]} years · '
                    f'{esc(lw["fee_model"])}</p>'
                    + ('<ul class="cb-why cb-why-row">' + "".join(f"<li>{esc(w)}</li>" for w in extra) + "</ul>"
                       if extra else "")
                    + '<p class="cb-meta">'
                    + ("" if any(w.startswith("Speaks") for w in extra)
                       else f'Speaks {esc(", ".join(lw["languages"]))} · ')
                    + f'Rated {lw["rating"]} from {lw["reviews"]} reviews (sample data): '
                      f'<i>“{esc(lw["review_snippets"][0])}”</i></p>')
        with c2:
            if lw["id"] in ss.sent_to:
                st.html('<span class="cb-chip">Brief sent</span>')
            elif st.button("Send my brief", key=f"send_{lw['id']}", icon=":material/send:", width="stretch"):
                ss.sent_to.append(lw["id"])
                st.rerun()


def once(facts: list, seen: set[str]) -> list:
    """Facts not shown under an earlier heading. Keeps the first place a sentence appears."""
    out = []
    for f in facts:
        k = " ".join(f.text.lower().split())
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


CHECK_WARNINGS = ("Removed", "Blocked", "Flagged", "Fact check", "The fact check", "Set aside", "Granite's summary")
CHECK_ORDER = ["sources", "numbers", "conclusions", "guardian", "summary", "advice", "set_aside"]


def fool_the_checks(b, ev_by_id: dict) -> str:
    """Three made-up statements go through the same checks as the brief. Returns the result rows (HTML).
    Nothing here touches the client's brief."""
    first = next(iter(ev_by_id.values()))
    all_text = " ".join(e.text for e in ev_by_id.values())
    speed = next(n for n in (45, 55, 65, 75, 85) if str(n) not in all_text)
    invented = Fact(f"The other driver was going {speed} mph.", [first.id])
    advice = Fact("You should sign the release and settle now.", [first.id])
    uncited = Fact("The other driver admitted it was their fault.", [])
    test = CaseBrief(b.case_type, b.client_side, b.county, "", engine=b.engine, timeline=[invented, advice, uncited])
    safety.apply_guardrails(test, set(ev_by_id), {k: e.text for k, e in ev_by_id.items()})
    caught = ["the numbers check"] if invented.guardian_flags else []
    checker = llm.checker()
    if checker:
        with st.spinner(f"Asking {checker.split(' (')[0]}…"):
            verdict = llm.guardian_check(invented.text, brief_agent.GROUNDEDNESS_RISK, first.text)
        if verdict:
            invented.guardian_flags.append(f"⚠ Not grounded in [{first.id}]")
            where = "on this computer" if "local" in checker else "on IBM watsonx"
            caught.append(f"{checker.split(' (')[0]} ({where})")
    by = " and ".join(caught) or "no check"
    return ('<ul class="cb-list">'
            f'<li><span>{flagged(esc(invented.text), invented.guardian_flags)} {tag(first.id)}'
            f'{guardian_tags(invented.guardian_flags)}<span class="cb-caught">An invented speed. '
            f'Caught by <b>{esc(by)}</b>. It is set aside, out of the brief.</span></span></li>'
            f'<li><span><span class="cb-removed">{esc(advice.text)}</span> {tag(first.id)}'
            '<span class="cb-flag">Blocked: legal advice</span><span class="cb-caught">Advice, not a fact. '
            'Caught by <b>the legal-advice check</b>. It never reaches the brief.</span></span></li>'
            f'<li><span><span class="cb-removed">{esc(uncited.text)}</span>'
            '<span class="cb-flag">Removed: no source</span><span class="cb-caught">Points to no evidence. '
            'Caught by <b>the sources check</b>. It never reaches the brief.</span></span></li></ul>')


def show_checks(b, ev_by_id: dict):
    """How this brief was checked: one ruled row per check, then a live test with made-up statements."""
    checks = sorted(getattr(b, "checks", []), key=lambda c: CHECK_ORDER.index(c["id"]) if c["id"] in CHECK_ORDER else 99)
    mark = {"pass": '<span class="cb-mark pass"></span>', "flag": '<span class="cb-mark flag">!</span>',
            "skip": '<span class="cb-mark skip"></span>'}
    rows = "".join(f'<li>{mark.get(c["status"], mark["skip"])}<span class="cb-check-name">{esc(c["name"])}</span>'
                   f'<span class="cb-check-detail">{esc(c["detail"])}</span></li>' for c in checks)
    checker = llm.checker()
    writer = "rules on this computer" if b.engine == "rules" else f"IBM Granite ({llm.model_name()}) via {b.engine}"
    foot = (f"<b>Written by</b> {esc(writer)}. <b>Checked by</b> rules"
            + (f" and {esc(checker)}" if checker else "") + ". A statement a check finds unsupported is set "
            "aside and listed here, so you can see what was left out and why.")
    aside = next((c.get("items", []) for c in checks if c["id"] == "set_aside"), [])
    aside_html = ('<ul class="cb-list">' + "".join(
        f'<li><span><span class="cb-removed">{esc(i["text"])}</span> {"".join(tag(s) for s in i["sources"])}'
        f'{"".join(f"<span class=cb-flag>{esc(flag_label(r))}</span>" for r in i["reasons"])}</span></li>'
        for i in aside) + "</ul>") if aside else ""
    with st.container(border=True, key="checks"):
        heading("How this brief was checked")
        st.html(f'<ul class="cb-list cb-checks">{rows}</ul><p class="cb-check-foot">{foot}</p>')
        if aside_html:
            label("Set aside: not in the brief, and never shown to lawyers")
            st.html(aside_html)
        if st.button("Try to fool it: add made-up statements", key="fool", icon=":material/science:"):
            ss.fool_result = (id(b), fool_the_checks(b, ev_by_id))
        if ss.get("fool_result") and ss.fool_result[0] == id(b):
            label("Three made-up statements, run through the same checks. None of them is added to your brief.")
            st.html(ss.fool_result[1])


def show_deadlines(deadlines: list[dict], stacked: bool = False):
    rows = []
    for d in sorted(deadlines, key=lambda d: d["date"]):
        days = days_until(d["date"])
        urgent = 0 <= days <= 30
        note = ("<small>date has passed</small>" if days < 0
                else f'<small>in {days} day{"" if days == 1 else "s"}</small>' if urgent else "")
        basis = rich(d["basis"]) if d["basis"].startswith("[") else f'<span class="cb-basis">{esc(d["basis"])}</span>'
        rows.append(f'<li><span class="cb-date{" cb-urgent" if urgent else ""}">{fmt_date(d["date"])}{note}</span>'
                    f'<span>{esc(d["label"])} {basis}</span></li>')
    st.html(f'<ul class="cb-list {"cb-stack" if stacked else "cb-dated"}">{"".join(rows)}</ul>')


def notice(text: str, deadlines: list[dict]):
    """Brief warnings: findings from the evidence get the one red rule, safety-check results an ink one.

    A finding also shows any rule-derived response date within 30 days that comes from the same evidence."""
    if text.startswith(("Removed", "Blocked", "Flagged", "Fact check", "Granite")):
        kind, title, extra = "cb-safety", "Safety check", ""
    elif text.startswith(("LLM unavailable", "The fact check")):
        kind, title, extra = "cb-note", "Engine note", ""
    else:
        kind, title = "cb-time", "Found in your evidence"
        due = [d for d in deadlines if d["basis"].startswith("[") and d["basis"] in text
               and 0 <= days_until(d["date"]) <= 30]
        extra = "".join(f'<br>Response requested by <b class="cb-urgent">{fmt_date(d["date"])}</b>, in '
                        f'{days_until(d["date"])} day{"" if days_until(d["date"]) == 1 else "s"}.' for d in due)
    st.html(f'<div class="cb-notice {kind}"><b>{title}</b>{rich(text)}{extra}</div>')


def marked_source(ev: Evidence, facts: list) -> str:
    """The source text with every sentence the brief cites marked in that source's highlighter colour."""
    text = esc(ev.text)
    cited = {f.text for f in facts if ev.id in f.sources}
    for sentence in sorted(cited, key=len, reverse=True):
        s = esc(sentence)
        if s and s in text:
            text = text.replace(s, f'<mark style="background:{highlighter(ev.id)}">{s}</mark>', 1)
    return text


HIDDEN_INSTRUCTION_RE = re.compile(r"&lt;!--.*?--&gt;", re.S)


def flagged_ids() -> set[str]:
    """Evidence items that try to give instructions to an AI (see safety.has_injection)."""
    return set(safety.injection_flags(ss.evidence))


def blocked_stamp(text: str) -> str:
    """The BLOCKED stamp plus the text with any hidden <!-- ... --> instruction outlined in red."""
    marked = HIDDEN_INSTRUCTION_RE.sub(lambda m: f'<span class="cb-hidden-instr">{m.group(0)}</span>', esc(text))
    return ('<span class="cb-stamp">BLOCKED</span><p class="cb-meta">This item contains instructions aimed at an '
            'AI. CaseBridge ignored them and kept the item as evidence only.</p>'
            f'<p class="cb-source">{marked}</p>')


def reveal(text: str, names: dict[str, str], start: float = 0.0) -> tuple[str, float]:
    """A fact in the client's view whose personal details fade into lawyer-view placeholders one by one.
    Returns the HTML and the delay to start the next fact's animation at."""
    out, delay = esc(text), start
    for original, token in scoreboard.redaction_swaps(text, names):
        o = esc(original)
        if o not in out:
            continue
        chips = rich(token)
        out = out.replace(o, f'<span class="cb-swap" style="--d:{delay:.2f}s"><s>{o}</s>{chips}</span>', 1)
        delay += 0.35
    return out, delay


def engine_status(engine: str) -> tuple[str, str]:
    checker = llm.checker()
    if engine == "rules":
        return "Built offline with rules.", ("No AI model connected." if not checker else
                                             f"No chat model connected. Fact check: {checker}.")
    return ("Built with IBM Granite.",
            f"{llm.model_name()} through {engine}. Fact check: {checker or 'citations and rules'}.")


def go(target: str):
    ss.nav = target


@st.cache_resource
def _brief_cache() -> dict:
    return {}


@st.cache_resource
def _builder() -> tuple[ThreadPoolExecutor, dict, threading.Lock]:
    """One build at a time for the whole app: two Granite runs at once don't fit in a laptop's memory."""
    return ThreadPoolExecutor(max_workers=1), {}, threading.Lock()


def build_brief(evidence: list) -> "CaseBrief":
    """Same evidence and same engine -> the same brief, instantly. Granite on a laptop takes about a
    minute, so a demo can build once beforehand. The build runs outside the page's script, so a click
    elsewhere doesn't throw it away, and a second click waits for the build already running instead of
    starting another. A brief whose model or fact check failed is not kept, so the next build tries
    again. Each caller gets its own copy."""
    key = (tuple((e.id, e.kind, e.title, e.text, e.file_name) for e in evidence), llm.backend(), llm.checker())
    cache = _brief_cache()
    if key in cache:
        return copy.deepcopy(cache[key])
    pool, running, lock = _builder()
    with lock:
        job = running.get(key)
        if job is None:
            job = running[key] = pool.submit(brief_agent.build, copy.deepcopy(evidence))
    b = job.result()
    with lock:
        running.pop(key, None)
    if not any(w.startswith(("LLM unavailable", "The fact check")) for w in b.warnings):
        cache[key] = b
    return copy.deepcopy(b)


# --- the lawyer board: shared database when available, this session's memory otherwise --------

def board() -> list[dict]:
    """Every posted case, newest first. With the shared store, a client window and a lawyer window
    see the same cases."""
    if shared_store_ready():
        try:
            return store.list_cases(ss.owner)
        except Exception:
            pass
    return ss.board


def post_case(red: dict) -> str:
    red["posted"] = datetime.now().date().isoformat()
    if shared_store_ready():
        return store.add_case(red, ss.owner)
    red.update(id=f"C-{1040 + len(ss.board)}", connect_requests=[], connected=[], mine=True)
    ss.board.insert(0, red)
    return red["id"]


def request_connect(case: dict, lawyer_id: str):
    if shared_store_ready():
        store.request_connect(case["id"], lawyer_id)
    else:
        case["connect_requests"].append(lawyer_id)


def accept_lawyer(case: dict, lawyer_id: str):
    """Only now does the client's full brief leave their session, for the lawyers they accepted."""
    if shared_store_ready():
        store.accept(case["id"], lawyer_id, ss.brief.to_dict() if ss.brief else None)
    else:
        case["connect_requests"].remove(lawyer_id)
        case["connected"].append(lawyer_id)


def delete_my_case():
    """Remove everything this client added: the posted case and its requests, and the evidence and brief."""
    if ss.my_case_id:
        if shared_store_ready():
            store.delete_case(ss.my_case_id)
        ss.board = [c for c in ss.board if c["id"] != ss.my_case_id]
    ss.evidence, ss.brief, ss.sent_to, ss.hidden, ss.my_case_id = [], None, [], set(), None
    ss.pop("fool_result", None)
    ss.toast = "Your case was deleted from CaseBridge."
    ss.nav = PAGES[0]         # a callback, so the page can still change before the rail is drawn


def my_case() -> dict | None:
    return next((c for c in board() if c["id"] == ss.my_case_id), None)


def show_data_panel():
    """Where your data goes, in plain words, and a way to delete it. Reflects the engine actually in use."""
    backend, photos_out = llm.backend(), bool(os.environ.get("ANTHROPIC_API_KEY"))
    sent = {"watsonx": "Your evidence text is sent to IBM watsonx so Granite can write the brief.",
            "ollama": "Nothing for the brief: Granite runs on this computer."}.get(backend, "Nothing: the brief is "
                                                                                          "built on this computer.")
    if photos_out:
        sent += " Photos you upload are sent to Claude vision (Anthropic) to read them, with their location removed."
    local = ["redaction", "deadlines", "voice transcription (faster-whisper)"]
    if llm.checker() and "local" in llm.checker():
        local.append("the Granite Guardian fact check")
    rows = [("On this computer", ", ".join(local).capitalize() + "."),
            ("Sent to an AI service", sent),
            ("What lawyers see", "Only the anonymized brief, until you accept one. The lawyer you accept sees your "
                                 "full brief."),
            ("What is saved", "Your case is saved on the lawyer board only if you post it. Deleting removes it, "
                              "its requests and anything you shared.")]
    with st.container(border=True, key="data"):
        heading("Where your data goes")
        st.html('<ul class="cb-list cb-data">' + "".join(
            f'<li><span class="cb-check-name">{esc(k)}</span><span class="cb-check-detail">{esc(v)}</span></li>'
            for k, v in rows) + "</ul>")
        if backend == "watsonx":
            meta("IBM's own data retention applies to what is sent to watsonx. LLM_BACKEND=ollama keeps everything "
                 "on this computer.")
        with st.popover("Delete my case", icon=":material/delete:"):
            st.html('<p class="cb-meta">This removes your evidence, your brief and, if you posted it, your case and '
                    'its connect requests from CaseBridge. It can\'t be undone.</p>')
            st.button("Delete everything", key="delete_case", icon=":material/delete_forever:",
                      on_click=delete_my_case)


def evidence_names():
    return safety.find_names([e.text for e in ss.evidence])


def anonymized_brief() -> dict:
    """What a lawyer sees before the client accepts them: redacted, minus lines the client hid."""
    return safety.hide_facts(safety.redact_brief(ss.brief, evidence_names()), ss.hidden)


def privacy_receipt(red: dict):
    """The privacy receipt: what redaction (and the client) kept away from lawyers, in plain words."""
    hidden = safety.privacy_summary(red)
    if hidden:
        meta("Hidden from lawyers: " + ", ".join(f"{n} × {what}" for what, n in hidden.items()) + ".")


# --- sidebar ---------------------------------------------------------------------------

style(CSS)
if ss.toast:
    st.toast(ss.toast, icon=":material/check_circle:")
    ss.toast = None
style(nav_progress_css())

with st.sidebar:
    st.html('<p class="cb-brand">CaseBridge</p><p class="cb-tagline">From a stressful pile of evidence to the right '
            'lawyer, without legal advice from a bot.</p>')
    page = st.radio("Go to", PAGES, key="nav", label_visibility="collapsed",
                    format_func=lambda p: p.split(" · ")[-1])
    status, detail = engine_status(llm.backend())
    with st.container(key="railfoot"):
        st.html(f'<p class="cb-foot"><b>{status}</b> {detail}<br><br>Prototype. CaseBridge organizes information. '
                'It does not give legal advice.</p>')


# --- 1. Intake -------------------------------------------------------------------------

if page.startswith("1"):
    st.title("Tell us what happened", anchor=False)
    lead("You don't need to organize anything. Add whatever you have: a voice note, photos, letters, reports. "
         "We'll put it in order for a lawyer.")

    with st.container(horizontal=True):
        if st.button("Load demo case (Maria)", icon=":material/folder_open:"):
            ss.evidence = ingest.load_demo_case()
            ss.brief = None
        if st.button("Load demo case (Rosa)", icon=":material/folder_open:"):
            ss.evidence = ingest.load_demo_case("rosa")
            ss.brief = None
        if st.button("Load demo case (Bao)", icon=":material/folder_open:"):
            ss.evidence = ingest.load_demo_case("bao")
            ss.brief = None
        if st.button("Try a trick letter", icon=":material/warning:",
                     help="Adds a fictional insurer letter that hides instructions for an AI."):
            ss.evidence = ingest.number(ss.evidence + [ingest.load_trick_letter()])
            ss.brief = None
        if st.button("Clear", icon=":material/restart_alt:", type="tertiary"):
            ss.evidence, ss.brief = [], None

    with st.expander("Add your own evidence", expanded=not ss.evidence, icon=":material/add_circle:"):
        note = st.text_area("In your own words (any language, any order)", height=120)

        # --- In-browser mic recording -------------------------------------------
        # Short recordings make Whisper guess the language, and a wrong guess loses what the
        # client actually said. Letting them pick it fixes that; "Detect automatically" is default.
        spoken = st.pills("Which language will you speak?", list(ingest.SPOKEN_LANGUAGES),
                          default="Detect automatically", key="spoken_language")
        voice_lang = ingest.SPOKEN_LANGUAGES.get(spoken)   # None = detect automatically
        st.caption("CaseBridge turns speech into text itself, without sending it to an outside service. "
                   "We keep your own words and add "
                   "an English version for lawyers.")
        try:
            from streamlit_mic_recorder import mic_recorder
            recording = mic_recorder(
                start_prompt="🎙 Record a voice memo",
                stop_prompt="⏹ Stop recording",
                just_once=False,
                format="webm",
                key="mic",
            )
            if recording and recording.get("id") != ss.last_mic_id:
                ss.last_mic_id = recording["id"]
                with st.spinner("Transcribing your recording…"):
                    ev = ingest.voice_evidence(recording["bytes"], "mic_recording.webm", voice_lang)
                ss.evidence = ingest.number(ss.evidence + [ev])
                ss.brief = None
                st.rerun()
        except ImportError:
            pass  # mic recorder not installed; upload path still works

        uploads = st.file_uploader("Photos, PDFs, voice memos, text files", accept_multiple_files=True)
        captions = {}
        for up in uploads or []:
            kind = ingest.kind_for(up.name)
            if kind == "photo":
                st.image(up, width=220, alt=f"Uploaded photo {up.name}")
                captions[up.name] = st.text_input(f"What does {up.name} show?", key=f"cap_{up.name}")
            elif kind == "voice":
                st.audio(up)
                captions[up.name] = st.text_area(f"Transcript of {up.name} (optional: we transcribe it for you)",
                                                 key=f"cap_{up.name}")
        if st.button("Add to my case", icon=":material/add:"):
            new = []
            if note.strip():
                new.append(Evidence("", "note", "Written note from client", note.strip()))
            for up in uploads or []:
                kind = ingest.kind_for(up.name)
                data = up.getvalue()
                if kind == "document" and up.name.lower().endswith(".pdf"):
                    text = ingest.pdf_text(data)
                elif kind == "voice":
                    with st.spinner(f"Transcribing {up.name}…"):
                        ev = ingest.voice_evidence(data, up.name, voice_lang)
                    if captions.get(up.name):      # the client typed or corrected the transcript
                        ev.text = safety.clean_speech(captions[up.name])[0] or captions[up.name]
                        # Update the title whenever the client provided their own text,
                        # regardless of whether whisper succeeded, failed, or was unclear.
                        if not ev.title.endswith("(transcribed)") and \
                                "originally in" not in ev.title:
                            ev.title = f"Voice memo {up.name} (transcript typed by client)"
                    new.append(ev)
                    continue
                elif kind == "photo":
                    caption = (captions.get(up.name) or "").strip()
                    with st.spinner(f"Reading {up.name}…"):
                        auto, auto_kind = ingest.photo_text(data, up.name)
                    if auto.startswith("["):   # no key, offline or unreadable: the client's caption is the evidence
                        text = caption or f"[{kind} uploaded, no description yet]"
                    else:                      # the client's own words first, then what was read from the photo
                        text, kind = f"{caption} {auto}".strip(), auto_kind
                    # Time goes to the timeline; GPS is written so redaction hides it from lawyers.
                    # Use a local variable so the outer `note` (typed text) is not clobbered.
                    photo_note_text = ingest.photo_note(ingest.photo_metadata(data))
                    text = f"{text} {photo_note_text}".strip()
                else:
                    text = data.decode("utf-8", errors="ignore")
                new.append(Evidence("", kind, up.name, text, up.name))
            ss.evidence = ingest.number(ss.evidence + new)
            ss.brief = None

    if ss.evidence:
        st.subheader(f"Your evidence ({len(ss.evidence)} items)", anchor=False)
        meta("Each item gets its own id and colour. Every statement in your brief points back to one of them.")
        style("".join(
            f'.st-key-ev_{e.id} summary [data-testid="stMarkdownContainer"] p::before{{content:"{e.id}";'
            f'display:inline-block;margin-right:.6rem;padding:0 .4rem;border-radius:2px;font-size:.75rem;'
            f'font-weight:700;line-height:1.4rem;background:{highlighter(e.id)};color:#1E2230}}'
            for e in ss.evidence))
        injected = flagged_ids()   # not `flagged`: that name is the review-mark helper
        for e in ss.evidence:
            # Titles of uploads are file names: escape Markdown so "my_photo_1.jpg" or "[x](url)" shows as typed.
            safe = re.sub(r"([\\`*_{}\[\]()<>#+!|~-])", r"\\\1", e.title)
            title = f"{safe} · contains instructions to an AI" if e.id in injected else safe
            icon = "gpp_bad" if e.id in injected else KIND_ICONS.get(e.kind, "attach_file")
            with st.expander(title, icon=f":material/{icon}:", key=f"ev_{e.id}", expanded=e.id in injected):
                st.html(blocked_stamp(e.text) if e.id in injected else f'<p class="cb-source">{esc(e.text)}</p>')
                if e.kind == "voice":
                    meta("Filler sounds, swearing and insults are left out of the transcript. Your recording is unchanged.")
        built_now = False
        if st.button("Rebuild my case brief" if ss.brief else "Build my case brief",
                     type="secondary" if ss.brief else "primary",
                     icon=":material/refresh:" if ss.brief else ":material/arrow_forward:"):
            with st.status("Building your case brief…", expanded=True) as status:
                voices = sum(e.kind == "voice" for e in ss.evidence)
                st.write(f"Reading {len(ss.evidence)} pieces of evidence"
                         + (f", including {voices} voice memo{'s' if voices != 1 else ''}" if voices else ""))
                where = {"ollama": "on this computer", "watsonx": "on IBM watsonx"}.get(llm.backend())
                if where:
                    st.write(f"IBM Granite is writing your brief {where}. This usually takes about a minute "
                             "the first time. Please keep this page open.")
                ss.brief = build_brief(ss.evidence)
                ss.hidden = set()
                for k in [k for k in ss if str(k).startswith("hide_")]:
                    del ss[k]          # a new brief starts with nothing hidden
                red = safety.redact_brief(ss.brief, evidence_names())
                stats = scoreboard.brief_stats(ss.evidence, ss.brief, red)
                # Short pauses so each step can be read; the work above is already done.
                for line in (f"Found {stats['facts']} facts, and linked every one to its source",
                             f"Checked every letter for hidden instructions: "
                             f"{stats['hidden_instructions'] or 'none'} found",
                             f"Checked for legal advice: {stats['advice_given']} in your brief",
                             f"Hid {stats['details_hidden']} personal details from the lawyer view"):
                    time.sleep(0.35)
                    st.write(line)
                status.update(label="Your brief is ready", state="complete", expanded=False)
            built_now = True
        if built_now:
            state_note("<b>Your brief is ready.</b> Every statement in it points back to your evidence.")
        if ss.brief:
            st.button("Open my case brief", type="primary", icon=":material/arrow_forward:", on_click=go,
                      args=(PAGES[1],))
    style(nav_progress_css())


# --- 2. Brief --------------------------------------------------------------------------

elif page.startswith("2"):
    st.title("Your case brief", anchor=False)
    b = ss.brief
    if not b:
        state_note("Add your evidence and build your brief first. It takes a few seconds.")
        st.button("Go to Tell us what happened", type="primary", on_click=go, args=(PAGES[0],))
        st.stop()
    ev_by_id = {e.id: e for e in ss.evidence}

    # 1. The case in one paragraph, and the one thing to do: confirm what the AI inferred.
    lead(b.summary)
    if b.summary_guardian_flags:
        st.html(guardian_tags(b.summary_guardian_flags))
    # What CaseBridge did with this case. It counts our own work, never the case's strength or value.
    stats = scoreboard.brief_stats(ss.evidence, b, safety.redact_brief(b, evidence_names()))
    status, _ = engine_status(b.engine)
    st.html('<div class="cb-trust">'
            f'<span><b>{stats["facts_cited"]} of {stats["facts"]}</b> statements cite your evidence</span>'
            + (f'<span><b>{stats["set_aside"]}</b> set aside as unsupported</span>' if stats["set_aside"] else "") +
            f'<span><b>{stats["advice_given"]}</b> read as legal advice</span>'
            f'<span><b>{stats["details_hidden"]}</b> personal details hidden from lawyers</span>'
            f'<span><b>{stats["hidden_instructions"]}</b> hidden instructions</span></div>'
            f'<p class="cb-meta">{esc(status)} The tab <b>How it was checked</b> shows each check.</p>')
    only = [l for l in b.languages if l != "English"]
    if only and "English" not in b.languages:
        state_note(f"<b>You speak {esc(', '.join(only))}.</b> We'll only show lawyers who speak it too.")

    with st.container(border=True, key="confirm"):
        label("Please confirm. You know your situation best.")
        c1, c2, c3, c4 = st.columns([3, 4, 2.5, 2.5], vertical_alignment="bottom")
        keys = list(PRACTICE_AREAS)
        b.case_type = c1.selectbox("Type of case", keys, index=keys.index(b.case_type),
                                   format_func=PRACTICE_AREAS.get)
        b.client_side = c2.selectbox("Your side", ["plaintiff", "defense"],
                                     index=["plaintiff", "defense"].index(b.client_side),
                                     format_func=SIDE_LABELS.get)
        b.county = c3.text_input("County", b.county or "")
        c4.button("Find lawyers", type="primary", icon=":material/arrow_forward:", on_click=go,
                  args=(PAGES[2],), width="stretch")

    # 2. What needs attention now. Check results live in their own tab, so only evidence findings stay here.
    for w in b.warnings:
        if not w.startswith(CHECK_WARNINGS):
            notice(w, b.deadlines)
    # Insurer tactics, one line per document until opened: what each means, and a question for a lawyer.
    by_source: dict[str, list[dict]] = {}
    for a in b.alerts:
        by_source.setdefault(a["sources"][0], []).append(a)
    for src, alerts in by_source.items():
        name = ev_by_id[src].title if src in ev_by_id else src
        n = len(alerts)
        with st.expander(f"{src} · {name}: {n} thing{'s' if n != 1 else ''} to know", icon=":material/info:"):
            st.html('<ul class="cb-list">' + "".join(
                f'<li><span><b>{esc(a["title"])}</b><span class="cb-caught">{esc(a["meaning"])}<br>'
                f'<i>A question to ask a lawyer:</i> {esc(a["ask"])}</span></span></li>' for a in alerts) + "</ul>")
    for c in b.contradictions:
        st.html(f'<div class="cb-notice cb-note"><b>Details that don\'t match: {esc(c["topic"])}</b>'
                f'{rich(c["text"])} A lawyer will want to clear this up early. It is common and doesn\'t mean '
                'anyone did something wrong.</div>')

    # 3. Everything else, one question at a time.
    due_soon = sum(0 <= days_until(d["date"]) <= 30 for d in b.deadlines)
    t_facts, t_next, t_checks, t_privacy = st.tabs(
        ["What happened", "Deadlines and next steps", "How it was checked", "Privacy"], key="brief_tab")

    with t_facts:
        left, right = st.columns([3, 2], gap="large")
        all_facts = b.timeline + b.parties + b.injuries + b.damages
        seen: set[str] = set()      # the rules engine can file one sentence under two headings; show it once
        with left:
            show_facts("Timeline", once(b.timeline, seen), dated=True)
            show_facts("People and organizations involved", once(b.parties, seen))
            show_facts("Injuries and treatment", once(b.injuries, seen))
            show_facts("Costs and losses reported", once(b.damages, seen))
        with right:
            heading("Check a source")
            sid = st.selectbox("Evidence", list(ev_by_id), format_func=lambda i: f"{i} · {ev_by_id[i].title}",
                               label_visibility="collapsed")
            with st.container(border=True):
                src = ev_by_id[sid]
                english, _, original = src.text.partition("\nOriginal (")
                if sid in flagged_ids():
                    st.html(f'<div class="cb-source-head">{tag(sid)}</div>{blocked_stamp(src.text)}')
                elif original:      # voice memo: the client's own words next to the English version
                    lang, _, words = original.partition("): ")
                    t_en, t_own = st.tabs(["English", f"Your words ({lang})"])
                    with t_en:
                        shown = Evidence(src.id, src.kind, src.title, english)
                        st.html(f'<div class="cb-source-head">{tag(sid)}<span>Cited sentences are highlighted'
                                f'</span></div><p class="cb-source">{marked_source(shown, all_facts)}</p>')
                    with t_own:
                        st.html(f'<p class="cb-source">{esc(words)}</p>')
                else:
                    st.html(f'<div class="cb-source-head">{tag(sid)}<span>Cited sentences are highlighted</span>'
                            f'</div><p class="cb-source">{marked_source(src, all_facts)}</p>')

    with t_next:
        left, right = st.columns([1, 1], gap="large")
        with left:
            heading("Deadlines to confirm with a lawyer")
            if due_soon:
                meta(f"{due_soon} of these {'is' if due_soon == 1 else 'are'} within the next 30 days.")
            show_deadlines(b.deadlines, stacked=True)
            meta("General California rules. Exceptions apply. A lawyer must confirm every date.")
        with right:
            heading("What a lawyer will likely ask for")
            meta(f"You have {stats['evidence_covered']} of the {stats['evidence_checklist']} items a lawyer usually "
                 "asks for. This is about how complete your evidence is, not how strong your case is.")
            if b.missing_evidence:
                st.html('<ul class="cb-list cb-checklist">'
                        + "".join(f"<li><span>{esc(m)}" + (f'<br><small>How to get it: {esc(rules.how_to_get(m))}'
                                                           '</small>' if rules.how_to_get(m) else "") + "</span></li>"
                                  for m in b.missing_evidence) + "</ul>")
            else:
                st.html('<p class="cb-empty">No common items are missing.</p>')

    with t_checks:
        show_checks(b, ev_by_id)

    with t_privacy:
        left, right = st.columns([3, 2], gap="large")
        with left:
            heading("What a lawyer sees before you accept them")
            meta("Names, phone numbers, emails, plates and report numbers stay hidden until you accept a lawyer.")
            if st.toggle("Watch your details disappear", key="reveal"):
                names, delay, rows = evidence_names(), 0.0, []
                for f in b.timeline + b.parties + b.injuries + b.damages:
                    if scoreboard.redaction_swaps(f.text, names):
                        row, delay = reveal(f.text, names, delay)
                        rows.append(f'<p class="cb-reveal">{row}</p>')
                st.html("".join(rows) or '<p class="cb-empty">Nothing personal to hide in these statements.</p>')
            red = safety.redact_brief(b, evidence_names())
            receipt = st.container()       # filled after the checkboxes, so it reflects this click
            label("Their version of your summary")
            lead(red["summary"])
            with st.expander("Hide individual lines from lawyers", icon=":material/visibility_off:"):
                meta("Tick any line you'd rather not show to lawyers yet. You can share it later.")
                for section, title in (("timeline", "Timeline"), ("parties", "People involved"),
                                       ("injuries", "Injuries"), ("damages", "Costs and losses")):
                    heading(title)
                    for i, f in enumerate(red[section]):
                        key = safety.fact_key(section, i)
                        if st.checkbox(f"{f['text']} [{', '.join(f['sources'])}]", value=key in ss.hidden,
                                       key=f"hide_{key}", help="Hide this line from lawyers"):
                            ss.hidden.add(key)
                        else:
                            ss.hidden.discard(key)
            with receipt:
                privacy_receipt(safety.hide_facts(dict(red), ss.hidden))
        with right:
            show_data_panel()


# --- 3. Matches ------------------------------------------------------------------------

elif page.startswith("3"):
    st.title("Lawyers who handle cases like yours", anchor=False)
    b = ss.brief
    if not b:
        state_note("Build your case brief first, so we know which lawyers handle your kind of case.")
        st.button("Go to Tell us what happened", type="primary", on_click=go, args=(PAGES[0],))
        st.stop()

    results, excluded = matching.match(b.case_type, b.client_side, b.county or None, b.languages)
    n = len(results)
    lead(f"{n} lawyer{'' if n == 1 else 's'} handle{'s' if n == 1 else ''} {PRACTICE_AREAS[b.case_type].lower()} "
         f"cases for {SIDE_PLAIN[b.client_side]}. Send your brief to the one you choose, or post it anonymously "
         "and let them ask.")
    meta(f"Not shown: {excluded['practice_area']} with a different practice area, {excluded['side']} who only "
         "represent the other side"
         + (f", {excluded['language']} who don't speak your language" if excluded["language"] else "")
         + ". Lawyer profiles, ratings and reviews are sample data.")

    case = my_case()
    with st.container(border=True, key="post"):
        if case is None:
            label("Optional: let matching lawyers find you")
            st.html('<p class="cb-meta">Only an anonymized version is posted. Your name, phone number and other '
                    'details stay hidden until you accept a lawyer.</p>')
            if st.button("Post my anonymized case to the lawyer board", icon=":material/visibility_off:"):
                red = anonymized_brief()
                # Second lock: refuse to post if any known name or personal detail is still present.
                if safety.posting_blockers(red, evidence_names()):
                    st.error("We stopped this post because some personal details could still be read. "
                             "Please hide the lines that mention them on your case brief and try again.")
                    st.stop()
                ss.my_case_id = post_case(red)
                ss.toast = "Your anonymized case is on the lawyer board. You choose who sees the rest."
                st.rerun()
        else:
            label("Your anonymized case")
            st.html(f'<p class="cb-meta">Case <b>{esc(case["id"])}</b> is on the lawyer board. Lawyers see it without '
                    'your name or contact details.</p>')
            privacy_receipt(case)
            lawyers_by_id = {l["id"]: l for l in matching.load_lawyers()}
            for lid in case["connect_requests"]:
                lw = lawyers_by_id[lid]
                c1, c2 = st.columns([4, 1], vertical_alignment="center")
                with c1:
                    state_note(f"<b>{esc(lw['name'])}</b> ({esc(lw['firm'])}) asked to connect about your case.")
                if c2.button("Accept", key=f"acc_{lid}", type="primary", width="stretch"):
                    accept_lawyer(case, lid)
                    st.rerun()
            for lid in case["connected"]:
                lw = lawyers_by_id[lid]
                state_note(f"You accepted <b>{esc(lw['name'])}</b> ({esc(lw['firm'])}). They can now see your name "
                           "and full brief.")

    for lw in results[:5]:
        lawyer_card(lw)
    if n > 5:
        with st.expander(f"Show {n - 5} more lawyer{'' if n - 5 == 1 else 's'}", icon=":material/expand_more:"):
            for lw in results[5:]:
                lawyer_card(lw)


# --- Lawyer portal ---------------------------------------------------------------------

else:
    st.title("Lawyer portal", anchor=False)
    lawyers = matching.load_lawyers()
    by_id = {l["id"]: l for l in lawyers}
    c1, c2 = st.columns([2, 3], vertical_alignment="bottom", gap="large")
    me = by_id[c1.selectbox("Signed in as (demo lawyer)", list(by_id),
                            format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['firm']}")]
    c2.html(f'<div class="cb-strip"><span>Handles <b>{esc(", ".join(PRACTICE_AREAS[p] for p in me["practice_areas"]))}'
            f'</b></span><span>Represents <b>{esc(", ".join(me["sides"]))}</b></span>'
            f'<span>Counties <b>{esc(", ".join(me["counties"]))}</b></span></div>')

    mine_all = [c for c in board() if c["case_type"] in me["practice_areas"] and c["client_side"] in me["sides"]]
    inbox = 1 if me["id"] in ss.sent_to and ss.brief else 0
    tab_board, tab_inbox = st.tabs([f":material/view_list: Case board ({len(mine_all)})",
                                    f":material/inbox: Briefs sent to me ({inbox})"])
    with tab_board:
        meta("Cases in your practice areas and side, newest first. Never sorted by value, so no case is skipped for "
             "being small. Each stays anonymized until the client accepts you.")
        county_only = st.toggle("Only my counties", value=True)
        visible = [c for c in mine_all if not county_only or c.get("county") in me["counties"]]
        if not visible:
            st.html('<p class="cb-empty">No matching cases in your counties right now. Turn off "Only my counties" '
                    f'to see all {len(mine_all)}.</p>')
        for c in visible:
            with st.container(border=True, key=f"case_{c['id']}"):
                connected = me["id"] in c["connected"]
                # The full brief, only if the client accepted this lawyer (shared store, or this same session).
                shared = connected and (c.get("shared_brief") or (c.get("mine") and ss.brief and ss.brief.to_dict()))
                st.html(f'<div class="cb-case-head"><span class="cb-date">Posted {fmt_date(c["posted"])}</span>'
                        f'<strong>{esc(c["id"])}</strong><span>{esc(PRACTICE_AREAS[c["case_type"]])}</span>'
                        f'<span>{esc(c["client_side"].capitalize())}</span>'
                        f'<span>{esc(c.get("county") or "?")} County</span>'
                        f'<span>Speaks {esc(", ".join(c.get("languages", [])))}</span>'
                        f'{"" if shared else "<span class=cb-redact>Anonymized</span>"}</div>')
                if shared:
                    state_note("<b>Connected.</b> The client shared their identity and full brief with you.")
                    lead(shared["summary"])
                    show_facts("Parties", shared["parties"])
                else:
                    lead(c["summary"])
                    if c.get("timeline"):
                        show_facts("Timeline", c["timeline"], dated=True)
                meta("Missing: " + ", ".join(c.get("missing_evidence", [])))
                if connected:
                    pass
                elif me["id"] in c["connect_requests"]:
                    st.button("Request sent", disabled=True, key=f"req_{c['id']}", icon=":material/schedule:")
                elif st.button("Request to connect", key=f"req_{c['id']}", icon=":material/person_add:"):
                    request_connect(c, me["id"])
                    st.rerun()
    with tab_inbox:
        if me["id"] in ss.sent_to and ss.brief:
            state_note("<b>A client chose to send you their brief.</b> Their identity is included, because they "
                       "chose you.")
            b = ss.brief
            lead(b.summary)
            for section, title in (("timeline", "Timeline"), ("parties", "Parties"),
                                   ("injuries", "Injuries"), ("damages", "Costs and losses")):
                show_facts(title, getattr(b, section), dated=section == "timeline")
            meta("Missing: " + ", ".join(b.missing_evidence))
        else:
            st.html('<p class="cb-empty">No briefs sent to you yet. When a client chooses you, their full brief '
                    'appears here.</p>')
