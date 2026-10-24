"""CaseBridge MVP: messy evidence in -> cited case brief -> matched lawyers -> anonymized lawyer board.

Run: streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from casebridge import brief as brief_agent
from casebridge import ingest, llm, matching, safety
from casebridge.models import Evidence, PRACTICE_AREAS

st.set_page_config(page_title="CaseBridge", page_icon="⚖️", layout="wide")

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

ss = st.session_state
ss.setdefault("evidence", [])
ss.setdefault("brief", None)
ss.setdefault("board", [dict(c) for c in SEED_BOARD])
ss.setdefault("sent_to", [])
ss.setdefault("my_case_id", None)


# --- helpers ---------------------------------------------------------------------------

def cite(sources: list[str]) -> str:
    return " ".join(f"`{s}`" for s in sources)


def show_facts(title: str, facts: list, evidence_by_id: dict):
    st.markdown(f"**{title}**")
    if not facts:
        st.caption("Nothing found in the evidence.")
    for f in facts:
        f = f if isinstance(f, dict) else f.__dict__
        when = f"**{f['when']}** · " if f.get("when") else ""
        st.markdown(f"- {when}{f['text']} {cite(f['sources'])}")


def my_case() -> dict | None:
    return next((c for c in ss.board if c["id"] == ss.my_case_id), None)


def evidence_names():
    return safety.find_names([e.text for e in ss.evidence])


# --- sidebar ---------------------------------------------------------------------------

st.sidebar.title("⚖️ CaseBridge")
st.sidebar.caption("From a stressful mess of evidence to the right lawyer, without legal advice from a bot.")
page = st.sidebar.radio("Go to", ["1 · Tell us what happened", "2 · Your case brief",
                                  "3 · Find a lawyer", "Lawyer portal"])
st.sidebar.divider()
backend = llm.backend()
st.sidebar.markdown(f"**AI engine:** `{backend}`")
if backend == "rules":
    st.sidebar.caption("No Granite model connected. Using offline rule-based extraction. "
                       "Set WATSONX_APIKEY + WATSONX_PROJECT_ID, or run Ollama with granite3.3.")
st.sidebar.caption("Prototype. CaseBridge organizes information; it does not give legal advice.")


# --- 1. Intake -------------------------------------------------------------------------

if page.startswith("1"):
    st.header("Tell us what happened")
    st.write("You don't need to organize anything. Add whatever you have: a voice note, photos, "
             "letters, reports. We'll put it in order for a lawyer.")

    c1, c2 = st.columns([1, 3])
    if c1.button("Load demo case (Maria)", type="primary"):
        ss.evidence = ingest.load_demo_case()
        ss.brief = None
    if c2.button("Clear"):
        ss.evidence, ss.brief = [], None

    with st.expander("Add your own evidence", expanded=not ss.evidence):
        note = st.text_area("In your own words (any language, any order)", height=120)
        uploads = st.file_uploader("Photos, PDFs, voice memos, text files", accept_multiple_files=True)
        captions = {}
        for up in uploads or []:
            kind = ingest.kind_for(up.name)
            if kind == "photo":
                st.image(up, width=220)
                captions[up.name] = st.text_input(f"What does {up.name} show?", key=f"cap_{up.name}")
            elif kind == "voice":
                st.audio(up)
                captions[up.name] = st.text_area(f"Transcript of {up.name} (speech-to-text is a next step)",
                                                 key=f"cap_{up.name}")
        if st.button("Add to my case"):
            new = []
            if note.strip():
                new.append(Evidence("", "note", "Written note from client", note.strip()))
            for up in uploads or []:
                kind = ingest.kind_for(up.name)
                data = up.getvalue()
                if kind == "document" and up.name.lower().endswith(".pdf"):
                    text = ingest.pdf_text(data)
                elif kind == "photo":
                    with st.spinner(f"Analyzing {up.name}…"):
                        text, kind = ingest.photo_text(data, up.name)
                    if text.startswith("[photo uploaded, no description yet]"):
                        # No API key — fall back to manual caption
                        text = captions.get(up.name) or text
                elif kind == "voice":
                    text = captions.get(up.name) or "[voice uploaded, no description yet]"
                else:
                    text = data.decode("utf-8", errors="ignore")
                new.append(Evidence("", kind, up.name, text, up.name))
            ss.evidence = ingest.number(ss.evidence + new)
            ss.brief = None

    if ss.evidence:
        st.subheader(f"Your evidence ({len(ss.evidence)} items)")
        icons = {"voice": "🎙️", "photo": "📷", "document": "📄", "note": "📝"}
        for e in ss.evidence:
            with st.expander(f"{icons.get(e.kind, '📎')} `{e.id}` {e.title}"):
                st.write(e.text)
        if st.button("Build my case brief →", type="primary"):
            with st.spinner("Organizing your evidence..."):
                ss.brief = brief_agent.build(ss.evidence)
            st.success("Brief ready. Open **2 · Your case brief** in the sidebar.")


# --- 2. Brief --------------------------------------------------------------------------

elif page.startswith("2"):
    st.header("Your case brief")
    b = ss.brief
    if not b:
        st.info("Add evidence and click **Build my case brief** first.")
        st.stop()
    ev_by_id = {e.id: e for e in ss.evidence}

    st.caption(f"Generated by `{b.engine}` · every statement links to the evidence it came from · "
               "statements without a source are removed automatically")
    st.markdown(f"> {b.summary}")

    st.markdown("**Please confirm. You know your situation best.**")
    c1, c2, c3 = st.columns(3)
    keys = list(PRACTICE_AREAS)
    b.case_type = c1.selectbox("Type of case", keys, index=keys.index(b.case_type),
                               format_func=PRACTICE_AREAS.get)
    b.client_side = c2.selectbox("Your side", ["plaintiff", "defense"],
                                 index=["plaintiff", "defense"].index(b.client_side),
                                 format_func=lambda s: {"plaintiff": "I was harmed (making a claim)",
                                                        "defense": "Someone is claiming against me"}[s])
    b.county = c3.text_input("County", b.county or "")

    for w in b.warnings:
        st.warning(w)

    left, right = st.columns([3, 2])
    with left:
        show_facts("🕒 Timeline", b.timeline, ev_by_id)
        show_facts("👥 People & organizations involved", b.parties, ev_by_id)
        show_facts("🩹 Injuries & treatment", b.injuries, ev_by_id)
        show_facts("💵 Costs & losses reported", b.damages, ev_by_id)
    with right:
        st.markdown("**📅 Deadlines to confirm with a lawyer**")
        for d in b.deadlines:
            st.markdown(f"- **{d['date']}**: {d['label']} _({d['basis']})_")
        st.caption("General California rules. Exceptions apply. A lawyer must confirm.")
        st.markdown("**🧩 What a lawyer will likely ask for (missing)**")
        for m in b.missing_evidence:
            st.markdown(f"- ☐ {m}")
        st.markdown("**🔎 Check a source**")
        sid = st.selectbox("Evidence", list(ev_by_id), format_func=lambda i: f"{i}: {ev_by_id[i].title}")
        st.info(ev_by_id[sid].text)

    st.divider()
    with st.expander("👁️ Preview what a lawyer sees before you accept them (anonymized)"):
        red = safety.redact_brief(b, evidence_names())
        st.markdown(f"> {red['summary']}")
        show_facts("Timeline", red["timeline"], ev_by_id)
        show_facts("People involved", red["parties"], ev_by_id)


# --- 3. Matches ------------------------------------------------------------------------

elif page.startswith("3"):
    st.header("Lawyers who handle cases like yours")
    b = ss.brief
    if not b:
        st.info("Build your case brief first.")
        st.stop()

    results, excluded = matching.match(b.case_type, b.client_side, b.county or None, b.languages)
    st.caption(f"Showing {len(results)} lawyers who handle **{PRACTICE_AREAS[b.case_type]}** for the "
               f"**{b.client_side}** side. Hidden: {excluded['practice_area']} with a different practice "
               f"area, {excluded['side']} who only represent the other side.")

    case = my_case()
    if case is None:
        st.markdown("**Optional:** let matching lawyers find you. Only an anonymized version is posted.")
        if st.button("Post my anonymized case to the lawyer board"):
            red = safety.redact_brief(b, evidence_names())
            red.update(id=f"C-{1040 + len(ss.board)}", posted=datetime.now().date().isoformat(),
                       connect_requests=[], connected=[], mine=True)
            ss.board.insert(0, red)
            ss.my_case_id = red["id"]
            st.rerun()
    else:
        st.success(f"Your anonymized case **{case['id']}** is on the lawyer board.")
        for lid in case["connect_requests"]:
            lw = next(l for l in matching.load_lawyers() if l["id"] == lid)
            c1, c2 = st.columns([4, 1])
            c1.info(f"📩 **{lw['name']}** ({lw['firm']}) asked to connect about your case.")
            if c2.button("Accept", key=f"acc_{lid}"):
                case["connect_requests"].remove(lid)
                case["connected"].append(lid)
                st.rerun()

    for lw in results:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"### {lw['name']} · {lw['firm']}")
            c1.markdown(f"⭐ **{lw['rating']}** ({lw['reviews']} reviews) · {lw['years']} yrs · "
                        f"{lw['fee_model']} · {', '.join(lw['languages'])}")
            c1.markdown("Why this match: " + " · ".join(f"✅ {w}" for w in lw["why"]))
            c1.caption(f"“{lw['review_snippets'][0]}”")
            if lw["id"] in ss.sent_to:
                c2.success("Brief sent")
            elif c2.button("Send my brief", key=f"send_{lw['id']}"):
                ss.sent_to.append(lw["id"])
                st.rerun()


# --- Lawyer portal ---------------------------------------------------------------------

else:
    st.header("Lawyer portal")
    lawyers = matching.load_lawyers()
    by_id = {l["id"]: l for l in lawyers}
    me = by_id[st.selectbox("Signed in as (demo)", list(by_id),
                            format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['firm']}")]
    st.caption(f"You handle: {', '.join(PRACTICE_AREAS[p] for p in me['practice_areas'])} · "
               f"side: {', '.join(me['sides'])} · counties: {', '.join(me['counties'])}")

    tab_board, tab_inbox = st.tabs(["Case board", "Briefs sent to me"])
    with tab_board:
        st.caption("Only cases in your practice areas and sides are shown. Cases are sorted by date posted, "
                   "never by estimated value, so no one gets skipped for being a 'small' case.")
        county_only = st.checkbox("Only my counties", value=True)
        visible = [c for c in ss.board if c["case_type"] in me["practice_areas"]
                   and c["client_side"] in me["sides"]
                   and (not county_only or c.get("county") in me["counties"])]
        if not visible:
            st.info("No matching cases right now.")
        for c in visible:
            with st.container(border=True):
                connected = me["id"] in c["connected"]
                st.markdown(f"**{c['id']}** · {PRACTICE_AREAS[c['case_type']]} · {c['client_side']} · "
                            f"{c.get('county') or '?'} County · posted {c['posted']} · "
                            f"speaks {', '.join(c.get('languages', []))}")
                if connected and c.get("mine") and ss.brief:
                    st.success("Connected. The client shared their identity and full brief with you.")
                    st.markdown(f"> {ss.brief.summary}")
                    show_facts("Parties", ss.brief.parties, {})
                else:
                    st.markdown(f"> {c['summary']}")
                    if c.get("timeline"):
                        show_facts("Timeline", c["timeline"], {})
                st.caption("Missing: " + ", ".join(c.get("missing_evidence", [])))
                if connected:
                    pass
                elif me["id"] in c["connect_requests"]:
                    st.button("Request sent", disabled=True, key=f"req_{c['id']}")
                elif st.button("Request to connect", key=f"req_{c['id']}"):
                    c["connect_requests"].append(me["id"])
                    st.rerun()
    with tab_inbox:
        if me["id"] in ss.sent_to and ss.brief:
            st.success("A client chose to send you their brief (identity included, because they chose you).")
            b = ss.brief
            st.markdown(f"> {b.summary}")
            for section, title in (("timeline", "Timeline"), ("parties", "Parties"),
                                   ("injuries", "Injuries"), ("damages", "Costs & losses")):
                show_facts(title, getattr(b, section), {})
            st.markdown("**Missing:** " + ", ".join(b.missing_evidence))
        else:
            st.info("No briefs sent to you yet.")
