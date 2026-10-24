# CaseBridge frontend design prompt (for the Impeccable design skill)

**Task.** Restyle the whole Streamlit app in `/Users/Macbook/Desktop/sparthack/app.py` so it looks finished, distinctive and trustworthy. Read `AGENTS.md` (section 2 product rules override this prompt) and `PRODUCT.md` first. Run your normal direction discovery with the user and choose the visual direction together. This prompt deliberately sets no palette, font or style.

## 1. Framing
CaseBridge turns an accident victim's scattered evidence into a cited case brief, then matches them with lawyers who handle that case type for their side. Primary user: a stressed, possibly injured Californian at a laptop at home, with an insurer pushing a release. Secondary: lawyers in the portal. Judges (SpartHill Hacks 2026, IBM AI Challenge, Responsible AI) score Technical Execution, Innovation, Challenge Fit and Real-World Impact, and Feasibility. The UI must calm and orient a real person, and make responsible AI visible in the layout within seconds on a screen recording.

## 2. Goals, in priority order
1. **Calm and orientation.** The user always knows where they are, what is done, and the one next action.
2. **Visible responsible AI.** Citations, safety notices, deadlines and anonymization are first-class visual objects, not footnotes.
3. **Hierarchy.** Dense briefs scan in seconds; one primary action per screen.
4. **Distinctive, finished craft.** Clearly not default Streamlit, with consistent components across screens.
5. **Robustness.** Offline, laptop widths, demo path.

Mode: app UI, so precision and restraint over spectacle. It must communicate calm, trustworthy, legal-grade but warm, never cold or bureaucratic. Avoid AI-gradient or purple-glow looks, glassmorphism, emoji as UI (replace the current emoji), gavel and scales clichés, metric-dashboard filler, decorative badges.

## 3. Page-by-page direction
**Shell and sidebar.** Show the client flow (1, 2, 3) as a step indicator with done and current states, and set the Lawyer portal apart as a different place. Keep the leading digit in each page label, because routing uses `page.startswith`. Show the AI engine as a plain-words status ("Granite" or "offline rules"), and keep "organizes information, not legal advice" permanently visible. Use the README tagline ("pile", not "mess").

**1 Tell us what happened.** One job: add what you have. Reassuring intro, an obvious drop zone, the Maria loader styled as a demo shortcut. Evidence items use a shared **evidence chip** (`E1`, `E2`), defined once and reused wherever a citation appears. "Build my case brief" is the single primary action and says what happens next.

**2 Your case brief.** Order: summary, a distinct **"Please confirm"** block (type, side, county) that reads as the client's decision, safety notices, then facts. Style `b.warnings` as a "Safety checks" group. "Removed N statement(s) with no source" and "Blocked N statement(s)" get the strongest treatment, and the settlement-release warning reads as information, not advice. Never invent a "0 removed" message. Facts lead with the date and end with evidence chips. **Deadlines**: prominent date, label, statute basis in a secondary style, under a header that always says "confirm with a lawyer". **Missing evidence** is a static checklist (no new `st.checkbox`). "Check a source" stays clearly the way to verify any chip. The **anonymized preview** is framed as an artifact ("What a lawyer sees before you accept"), with redaction tokens (`[CLIENT]`, `[PHONE]`, `[OTHER PARTY]`) visibly styled.

**3 Find a lawyer.** Lead with what was filtered and why (the existing counts). Cards: name and firm, then **"Why this match"** as the visual centerpiece, then fee model and languages. Ratings and reviews are secondary and labeled sample (fictional) data. No match percentages. "Send my brief" reads as the client's explicit choice. Posted, request received and accepted are distinct states.

**Lawyer portal.** Quieter and more professional. Scope line (areas, sides, counties) as a profile strip. The board visibly says **sorted by date posted, never by value**, and each card leads with its date. Anonymized cases carry an "Anonymized" tag. Connected cases show a clear state change (identity and full brief shared). Empty states are specific and calm.

## 4. The 3-minute demo path
Design must make these land on camera, each legible at a glance with minimal scrolling:
1. Load Maria; evidence list with chips (~20s).
2. Build brief; confirm block, cited timeline, settlement-release warning (~50s). Removed/Blocked notices appear only when Granite output is filtered, so style them without relying on them.
3. Deadlines with statute basis and "confirm with a lawyer", then the missing-evidence checklist (~30s).
4. Anonymized preview with visible redaction (~20s).
5. Lawyer matches, "Why this match", filtered-out counts; post the anonymized case (~30s).
6. Lawyer portal: request to connect, return, Accept, state change (~30s).

## 5. Copy guidance
Plain, calm, short sentences: what happened, what is next. No outcome language ("strong case"), no imperatives about legal decisions, no value language. Safety text states facts ("2 statements were removed because they had no source"). Empty states say what to do next. Engine status example: "Built with IBM Granite" or "Built offline with rules; no AI model connected". Label fictional lawyers, ratings and cases as sample data.

## 6. Hard constraints and do-not list
- Stay in Streamlit: `.streamlit/config.toml`, `st.html` or `st.markdown` with CSS, layout primitives, native widgets. `requirements.txt` says `streamlit>=1.40`; check the installed version before using newer theme options, and tell the team before raising the minimum.
- Offline must work (`LLM_BACKEND=rules streamlit run app.py`, no network). No CDN fonts, scripts or images; bundle fonts locally with a system fallback.
- Do not change widget keys (`cap_*`, `acc_*`, `send_*`, `req_*`), session state, routing, `casebridge/` or `models.py`. No new features or backend logic. Presentation helpers in `app.py` are fine.
- Never weaken AGENTS.md section 2: citations visible, "confirm with a lawyer" on deadlines, no case-value visuals or ranking, board sorted by date, anonymized until accepted, client confirms type, side and county.
- No fabricated stats, testimonials, logos, partners, press or "trusted by" claims. Fictional data stays fictional and labeled.
- No emoji-heavy UI, slow decorative animation, sideways scrolling, or phone layouts.

## 7. Definition of done
- [ ] All four screens screenshot-checked at 1440px and 1280px with Maria loaded, offline.
- [ ] Evidence chip, safety notice, deadline and anonymized-tag components consistent across screens.
- [ ] Every section 4 moment visible without hunting; text readable in a recording.
- [ ] No contrast, focus or truncation problems.
- [ ] `pytest -q` passes (report the real result).
- [ ] Maria's demo runs offline end to end: load, build, confirm, match, post, request, accept.
- [ ] Text sweep: no advice language, no emoji as UI, no unlabeled fictional claims.
- [ ] README manual sections updated if needed. Nothing committed unless a human asks.
