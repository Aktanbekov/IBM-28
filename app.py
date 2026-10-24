"""CaseBridge MVP: messy evidence in -> cited case brief -> matched lawyers -> anonymized lawyer board.

Run: streamlit run app.py
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime

import streamlit as st

from casebridge import brief as brief_agent
from casebridge import ingest, llm, matching, rules, safety
from casebridge.models import Evidence, PRACTICE_AREAS

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
.cb-tag-warn{display:inline-block;margin-left:.4rem;padding:0 .55rem;border-radius:2px;font-size:.75rem;font-weight:700;
  line-height:1.4rem;background:#FF9F2E;color:#1E2230;white-space:nowrap}
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


def guardian_tags(flags: list) -> str:
    """Amber chips for Guardian flags; empty string when flags is empty."""
    return "".join(f'<span class="cb-tag-warn">{esc(str(flag))}</span>' for flag in flags)


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
        gflags = guardian_tags(f.get("guardian_flags") or [])
        if dated:
            rows.append(f'<li><span class="cb-date">{esc(short_date(f.get("when") or ""))}</span>'
                        f'<span>{rich(f["text"])} {tags}{gflags}</span></li>')
        else:
            when = f'<b>{esc(f["when"])}</b> · ' if f.get("when") else ""
            rows.append(f'<li><span>{when}{rich(f["text"])} {tags}{gflags}</span></li>')
    st.html(f'<ul class="cb-list{" cb-dated" if dated else ""}">{"".join(rows)}</ul>')


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
    if text.startswith(("Removed", "Blocked")):
        kind, title, extra = "cb-safety", "Safety check", ""
    elif text.startswith("LLM unavailable"):
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


def engine_status(engine: str) -> tuple[str, str]:
    if engine == "rules":
        return "Built offline with rules.", "No AI model connected."
    return "Built with IBM Granite.", f"Connected through {engine}."


def go(target: str):
    ss.nav = target


def my_case() -> dict | None:
    return next((c for c in ss.board if c["id"] == ss.my_case_id), None)


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
        if st.button("Clear", icon=":material/restart_alt:", type="tertiary"):
            ss.evidence, ss.brief = [], None

    with st.expander("Add your own evidence", expanded=not ss.evidence, icon=":material/add_circle:"):
        note = st.text_area("In your own words (any language, any order)", height=120)

        # --- In-browser mic recording -------------------------------------------
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
                    ev = ingest.voice_evidence(recording["bytes"], "mic_recording.webm")
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
                        ev = ingest.voice_evidence(data, up.name)
                    if captions.get(up.name):      # the client typed or corrected the transcript
                        ev.text = captions[up.name]
                        # Update the title whenever the client provided their own text,
                        # regardless of whether whisper succeeded, failed, or was unclear.
                        if not ev.title.endswith("(transcribed)") and \
                                "originally in" not in ev.title:
                            ev.title = f"Voice memo {up.name} (transcript typed by client)"
                    new.append(ev)
                    continue
                elif kind == "photo":
                    text = captions.get(up.name) or f"[{kind} uploaded, no description yet]"
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
        for e in ss.evidence:
            with st.expander(e.title, icon=f":material/{KIND_ICONS.get(e.kind, 'attach_file')}:", key=f"ev_{e.id}"):
                st.html(f'<p class="cb-source">{esc(e.text)}</p>')
        built_now = False
        if st.button("Rebuild my case brief" if ss.brief else "Build my case brief",
                     type="secondary" if ss.brief else "primary",
                     icon=":material/refresh:" if ss.brief else ":material/arrow_forward:"):
            with st.spinner("Organizing your evidence..."):
                ss.brief = brief_agent.build(ss.evidence)
                ss.hidden = set()
                for k in [k for k in ss if str(k).startswith("hide_")]:
                    del ss[k]          # a new brief starts with nothing hidden
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

    lead(b.summary)
    if b.summary_guardian_flags:
        st.html(guardian_tags(b.summary_guardian_flags))
    status, _ = engine_status(b.engine)
    meta(f"{status} Every statement shows the evidence it came from. Statements without a source are removed "
         "automatically.")

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

    for w in b.warnings:
        notice(w, b.deadlines)

    # Insurer tactics: what each one means, and a question to bring to a lawyer. Never advice.
    for a in b.alerts:
        tags = "".join(tag(s) for s in a["sources"])
        st.html(f'<div class="cb-notice cb-time"><b>{esc(a["title"])}</b> {tags}<br>{esc(a["meaning"])}'
                f'<br><i>A question to ask a lawyer:</i> {esc(a["ask"])}</div>')
    # Details that disagree between documents, with the evidence on each side.
    for c in b.contradictions:
        st.html(f'<div class="cb-notice cb-note"><b>Details that don\'t match: {esc(c["topic"])}</b>'
                f'{rich(c["text"])} A lawyer will want to clear this up early. It is common and doesn\'t mean '
                'anyone did something wrong.</div>')

    left, right = st.columns([3, 2], gap="large")
    with left:
        show_facts("Timeline", b.timeline, dated=True)
        show_facts("People and organizations involved", b.parties)
        show_facts("Injuries and treatment", b.injuries)
        show_facts("Costs and losses reported", b.damages)
    with right:
        heading("Check a source")
        sid = st.selectbox("Evidence", list(ev_by_id), format_func=lambda i: f"{i} · {ev_by_id[i].title}",
                           label_visibility="collapsed")
        all_facts = b.timeline + b.parties + b.injuries + b.damages
        with st.container(border=True):
            st.html(f'<div class="cb-source-head">{tag(sid)}<span>Cited sentences are highlighted</span></div>'
                    f'<p class="cb-source">{marked_source(ev_by_id[sid], all_facts)}</p>')
        heading("Deadlines to confirm with a lawyer")
        show_deadlines(b.deadlines, stacked=True)
        meta("General California rules. Exceptions apply. A lawyer must confirm every date.")
        heading("What a lawyer will likely ask for")
        if b.missing_evidence:
            st.html('<ul class="cb-list cb-checklist">'
                    + "".join(f"<li><span>{esc(m)}" + (f'<br><small>How to get it: {esc(rules.how_to_get(m))}</small>'
                                                       if rules.how_to_get(m) else "") + "</span></li>"
                              for m in b.missing_evidence) + "</ul>")
        else:
            st.html('<p class="cb-empty">No common items are missing.</p>')

    with st.expander("Preview what a lawyer sees before you accept them", icon=":material/visibility_off:"):
        meta("Names, phone numbers, emails, plates and report numbers stay hidden until you accept a lawyer.")
        red = safety.redact_brief(b, evidence_names())
        receipt = st.container()       # filled after the checkboxes, so it reflects this click
        lead(red["summary"])
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


# --- 3. Matches ------------------------------------------------------------------------

elif page.startswith("3"):
    st.title("Lawyers who handle cases like yours", anchor=False)
    b = ss.brief
    if not b:
        state_note("Build your case brief first, so we know which lawyers handle your kind of case.")
        st.button("Go to Tell us what happened", type="primary", on_click=go, args=(PAGES[0],))
        st.stop()

    results, excluded = matching.match(b.case_type, b.client_side, b.county or None, b.languages)
    lead(f"Showing {len(results)} lawyer{'' if len(results) == 1 else 's'} who handle{'s' if len(results) == 1 else ''} {PRACTICE_AREAS[b.case_type].lower()} cases for "
         f"{SIDE_PLAIN[b.client_side]}.")
    meta(f"Hidden: {excluded['practice_area']} with a different practice area, {excluded['side']} who only "
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
                red.update(id=f"C-{1040 + len(ss.board)}", posted=datetime.now().date().isoformat(),
                           connect_requests=[], connected=[], mine=True)
                ss.board.insert(0, red)
                ss.my_case_id = red["id"]
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
                    case["connect_requests"].remove(lid)
                    case["connected"].append(lid)
                    st.rerun()
            for lid in case["connected"]:
                lw = lawyers_by_id[lid]
                state_note(f"You accepted <b>{esc(lw['name'])}</b> ({esc(lw['firm'])}). They can now see your name "
                           "and full brief.")

    for lw in results:
        with st.container(border=True, key=f"lawyer_{lw['id']}"):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.subheader(lw["name"], anchor=False)
                st.html(f'<p class="cb-meta">{esc(lw["firm"])} · {lw["years"]} years in practice · '
                        f'{esc(lw["fee_model"])} · Speaks {esc(", ".join(lw["languages"]))}</p>')
                label("Why this match")
                st.html('<ul class="cb-why">' + "".join(f"<li>{esc(w)}</li>" for w in lw["why"]) + "</ul>")
                st.html(f'<p class="cb-meta">Rated {lw["rating"]} from {lw["reviews"]} reviews (sample data): '
                        f'<i>“{esc(lw["review_snippets"][0])}”</i></p>')
            with c2:
                if lw["id"] in ss.sent_to:
                    st.html('<span class="cb-chip">Brief sent</span>')
                elif st.button("Send my brief", key=f"send_{lw['id']}", icon=":material/send:", width="stretch"):
                    ss.sent_to.append(lw["id"])
                    st.rerun()


# --- Lawyer portal ---------------------------------------------------------------------

else:
    st.title("Lawyer portal", anchor=False)
    lawyers = matching.load_lawyers()
    by_id = {l["id"]: l for l in lawyers}
    me = by_id[st.selectbox("Signed in as (demo)", list(by_id),
                            format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['firm']}")]
    st.html(f'<div class="cb-strip"><span>You handle <b>{esc(", ".join(PRACTICE_AREAS[p] for p in me["practice_areas"]))}'
            f'</b></span><span>Side <b>{esc(", ".join(me["sides"]))}</b></span>'
            f'<span>Counties <b>{esc(", ".join(me["counties"]))}</b></span>'
            f'<span><b>Sorted by date posted, never by estimated value</b></span></div>')

    tab_board, tab_inbox = st.tabs([":material/view_list: Case board", ":material/inbox: Briefs sent to me"])
    with tab_board:
        meta("Only cases in your practice areas and sides are shown, newest first, so no one gets skipped for "
             "being a 'small' case. Cases stay anonymized until the client accepts you.")
        county_only = st.toggle("Only my counties", value=True)
        visible = [c for c in ss.board if c["case_type"] in me["practice_areas"]
                   and c["client_side"] in me["sides"]
                   and (not county_only or c.get("county") in me["counties"])]
        if not visible:
            st.html('<p class="cb-empty">No matching cases right now. Turn off "Only my counties" to see cases '
                    'from nearby counties.</p>')
        for c in visible:
            with st.container(border=True, key=f"case_{c['id']}"):
                connected = me["id"] in c["connected"]
                shared = connected and c.get("mine") and ss.brief
                st.html(f'<div class="cb-case-head"><span class="cb-date">Posted {fmt_date(c["posted"])}</span>'
                        f'<strong>{esc(c["id"])}</strong><span>{esc(PRACTICE_AREAS[c["case_type"]])}</span>'
                        f'<span>{esc(c["client_side"].capitalize())}</span>'
                        f'<span>{esc(c.get("county") or "?")} County</span>'
                        f'<span>Speaks {esc(", ".join(c.get("languages", [])))}</span>'
                        f'{"" if shared else "<span class=cb-redact>Anonymized</span>"}</div>')
                if shared:
                    state_note("<b>Connected.</b> The client shared their identity and full brief with you.")
                    lead(ss.brief.summary)
                    show_facts("Parties", ss.brief.parties)
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
                    c["connect_requests"].append(me["id"])
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
