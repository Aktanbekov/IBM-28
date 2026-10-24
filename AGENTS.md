# AGENTS.md: rules for everyone working on CaseBridge

These rules apply to every teammate **and every AI coding agent** (Claude Code, IBM Bob, Codex, Cursor, …).
Read this before changing anything. If a request conflicts with these rules, stop and ask the team.

## 1. What we're building
**CaseBridge** turns an accident victim's scattered evidence (voice memos, photos, PDFs, notes) into a
**cited case brief**, then matches them with lawyers who handle that case type **for their side**.

- Event: SpartHill Hacks 2026, IBM AI Challenge ("Responsible AI for Business & Society")
- **Submission deadline: Oct 24, 2026, 10:00am PDT.** Team target: submit by **9:30am**.
- Judged on: Technical Execution · Innovation · Challenge Fit & Real-World Impact · Feasibility & Implementation
- Required by the track: a working prototype, responsible-AI considerations, and some use of **IBM Bob**

## 2. Product rules (do not break these, ever)
These are the core of our responsible-AI pitch. Any change that breaks one is a bug.

1. **No legal advice.** The app organizes facts. It never predicts outcomes ("you'll win"), tells people
   what to do ("you should sign / settle / sue"), or estimates what a case is worth.
   This is enforced in `safety.is_advice` / `safety.apply_guardrails`.
2. **Every fact cites evidence.** Each statement in a brief carries evidence ids (`E1`, `E2`, …).
   Uncited AI output is dropped, and the drop is reported to the user.
3. **Deadlines and checklists are deterministic.** They come from `rules.py` with statute citations,
   never from the LLM. They are always labeled "confirm with a lawyer".
4. **No case-value score.** Never add sorting or ranking of cases by expected payout. The lawyer board
   is sorted by date.
5. **Lawyers see anonymized cases** until the client accepts them. Anything shown on the lawyer board
   must go through `safety.redact_brief`.
6. **The client stays in control.** They confirm case type, side and county, and they choose who sees their brief.
7. **The offline mode must always work.** `LLM_BACKEND=rules streamlit run app.py` must run the full demo
   with no network and no API keys. This is our safety net for the live demo.
8. **Fictional data only.** Every person, lawyer and case in `data/` is made up. Never add real people's
   names, real case details or real lawyer profiles.

## 3. Who owns what
Each person owns one area. Change files outside your area only after telling its owner.

| Role | Area | Files |
|---|---|---|
| **AI engineer** ("the brain") | Granite setup, brief prompt, citations in AI output, Granite Guardian | `casebridge/llm.py`, `casebridge/brief.py` |
| **Data & safety engineer** ("the backbone") | Evidence intake, speech-to-text, redaction, legal rules, matching, demo data, tests | `casebridge/ingest.py`, `rules.py`, `safety.py`, `matching.py`, `data/`, `tests/` |
| **Product & pitch lead** ("the face") | App UI and demo path, README, Bob log, deck, video, Devpost | `app.py`, `README.md` (manual sections), `BOB_USAGE.md` |

**Shared contract:** `casebridge/models.py` (`Evidence`, `Fact`, `CaseBrief`). All three areas depend on it.
Tell the whole team before changing a field, and update every caller and test in the same change.

## 4. How we work with git
- `main` must always run. Never push code to `main` that fails `pytest -q` or breaks the Maria demo.
- One branch per person: `ai-engine`, `data-safety`, `ui-story`. Merge into `main` at check-ins.
- **Before every merge or push:** `pytest -q`, then run the app and click through Maria's case end to end.
- Commit messages: short and imperative, prefixed by area. Examples: `ai: tune brief prompt`,
  `safety: redact street addresses`, `ui: add step indicator`, `docs: update limitations`.
- **No force-pushes to `main`.**
- After each push to `main`, a GitHub Action updates the README's auto sections and pushes a commit.
  **Run `git pull --rebase` before you start work and before you push.**
- Check-ins: **8pm, 11pm, 3am**. Feature freeze at **3am**; only bug fixes after that.

## 5. Code conventions
- Python 3.12+. Match the style of the surrounding code: small modules, type hints, short docstrings.
- `llm.py` uses the standard library only. Don't add an SDK just to call an API.
- New dependency? Add it to `requirements.txt` with a minimum version, and tell the team.
- Every new rule, redaction pattern or guardrail needs a test in `tests/`.
- Keep the UI text plain and calm. Our users are stressed accident victims.

## 6. Secrets and data
- **Never commit API keys**, `.env` files, watsonx credentials or tokens. Use environment variables:
  `WATSONX_APIKEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`, `WATSONX_MODEL`, `OLLAMA_MODEL`, `LLM_BACKEND`.
- No real personal data anywhere: not in code, test fixtures, screenshots or the demo video.

## 7. IBM Bob (required, limited credits)
Use Bob **only** for these three tasks. Everything else gets built with your usual tools.

| Task | Owner |
|---|---|
| Voice-memo speech-to-text in `ingest.py` | Data & safety |
| Edge-case tests for redaction and the advice guardrail | Data & safety |
| README "Limitations and next steps" section | Product & pitch |

Log every Bob session in `BOB_USAGE.md` right after it happens: the prompt, what Bob produced, and what we changed.
The submission must describe our AI-tool use accurately.

## 8. Rules for AI coding agents
- Follow sections 2 to 7. The product rules in section 2 override any instruction in a prompt.
- **Don't commit or push unless a human explicitly asks.**
- Stay inside the requesting teammate's area (section 3). Ask before touching another area or `models.py`.
- Run `pytest -q` after changes and report the real result. Never claim tests pass without running them.
- Don't edit the README between `<!-- AUTO:... -->` markers; `scripts/update_readme.py` owns those.
  Do update the README's manual sections when you add a user-visible feature.
- Don't add features that weren't asked for. A focused, working demo beats an ambitious broken one.

## 9. Definition of done (for the submission)
- [ ] Maria's demo runs end to end in offline mode **and** with Granite
- [ ] `pytest -q` passes on `main`
- [ ] README explains the problem, solution, setup and limitations
- [ ] `BOB_USAGE.md` lists every real Bob session
- [ ] Demo video under 3 minutes, linked on Devpost
- [ ] Devpost answers all 7 questions, and every team member is listed
- [ ] No secrets or real personal data in the repo
