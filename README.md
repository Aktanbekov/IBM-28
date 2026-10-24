# CaseBridge

**From a stressful pile of evidence to the right lawyer, without legal advice from a bot.**

Built for the **SpartHill Hacks 2026 IBM AI Challenge** (Responsible AI for Business & Society).

<!-- AUTO:STATUS:START -->
| | |
|---|---|
| Last updated | 2026-10-23 21:09 (commit `f2680f1`) |
| Tests | passing (398 passed) |
| Commits | 63 |
| Contributors | Aktai Aktanbekov, Aktanbekov, Claude, Shahzod Bakhriev |
<!-- AUTO:STATUS:END -->

## The problem
People hurt in accidents usually arrive at a lawyer overwhelmed. They bring a scattered pile of photos,
voice notes and letters, and tell the story out of order. The first meeting goes to untangling it.

- **Lawyers lose unpaid hours.** Injury lawyers mostly work on contingency (about 33–40% of the payout)
  and offer free consultations, so every confusing intake is time they don't get paid for.
- **People find the wrong lawyer.** Some lawyers only represent injured people, some only defend the
  person being sued, and some only take car accidents.
- **The deadlines are real.** California generally allows 2 years to file an injury claim, and insurers
  push quick releases with short deadlines.

## Our goal
Turn hours of confused intake into **two minutes of reading**, and get people to a lawyer who
actually handles their kind of case, while keeping the AI honest, private and free of legal advice.

## What it does
1. **Intake:** the person uploads anything (notes, photos with captions, PDFs, voice-memo transcripts).
   Each item gets an evidence id (`E1`, `E2`, …).
2. **Case brief:** an AI agent builds a timeline, the people involved, injuries, losses, key deadlines
   and a list of missing evidence. **Every statement cites the evidence it came from.**
3. **Client confirms** the case type, which side they're on, and the county.
4. **Matching:** lawyers are filtered by practice area and by which side they represent, then ranked,
   and every match shows why.
5. **Lawyer portal:** lawyers browse **anonymized** cases and request to connect. The client's
   identity is shared only after the client accepts.

## Responsible AI by design
| Risk | What we built |
|---|---|
| AI invents facts | Every fact must cite evidence; uncited ones are removed. Numbers must appear in the cited evidence. Granite Guardian checks each fact against its sources. |
| A bot giving legal advice | A guardrail blocks outcome predictions, "you should sign or settle", and case valuations |
| Sensitive data exposure | Names, phones, emails, date of birth, plates and report numbers are redacted until the client accepts a lawyer |
| Lawyers skip "small" cases | No case-value score exists. The lawyer board is sorted by date only. |
| Wrong legal deadlines | Deadlines come from fixed rules with statute citations, labeled "confirm with a lawyer" |
| Language barriers | Detected language is used in matching |

## How to run
Requires Python 3.12 or newer.

```bash
git clone git@github.com:Aktanbekov/IBM-28.git
cd IBM-28
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501, click **Load demo case (Maria)**, then **Build my case brief**, then
**Open my case brief**, and go through the steps in the sidebar.

Run the tests:

```bash
pytest -q
```

### AI engine (optional)
The app works fully offline with a rule-based engine. To use IBM Granite:

| Option | Setup |
|---|---|
| IBM watsonx.ai | Copy `.env.example` to `.env` and fill in `WATSONX_APIKEY` and `WATSONX_PROJECT_ID`. The app picks the newest Granite chat model your region offers (today `ibm/granite-4-h-small`); `WATSONX_MODEL` overrides it. |
| Granite Guardian (fact check) | `brew install ollama && ollama serve`, then `ollama pull granite3-guardian:2b`. Runs on your laptop. |
| Local Granite via Ollama | `ollama pull granite3.3` |
| Force a backend | `LLM_BACKEND=watsonx`, `ollama` or `rules` |

Check your setup in one command: `python -m casebridge.llm`. It shows the backend and model, makes
one real chat call, and runs the fact check on a supported and a made-up statement.

The rule-based engine always computes the case type, side, county, deadlines and missing evidence.
When Granite is connected, it writes the narrative sections. Then every statement is checked:

1. **Citations:** a statement with no evidence id is removed (all modes).
2. **Numbers:** every number in a statement must appear in the evidence it cites (all modes).
3. **Fact check by a second model:** Granite Guardian checks each reworded statement against its cited
   evidence (groundedness). Legal advice stays with the rules guardrail: in testing, Guardian 2B flagged quoted
   insurer letters as advice. IBM withdrew Guardian from watsonx on
   2026-09-30, so it runs locally through Ollama; without it, Granite on watsonx answers the same
   Yes/No check. The brief always names which checker ran.
4. **Legal-advice guardrail:** outcome predictions, "you should sign", and valuations are blocked (all modes).

On the brief page, **How this brief was checked** lists each check and its result, and **Try to fool it**
runs three made-up statements (an invented speed, legal advice, an uncited claim) through the same checks live.
A statement copied word for word from its cited evidence is grounded by definition, so the model checks the
statements Granite rewrote.

## Project structure
```
app.py                  Streamlit UI: client flow and lawyer portal
casebridge/models.py    Shared data types (Evidence, Fact, CaseBrief)
casebridge/ingest.py    Files -> Evidence (E1..En)
casebridge/rules.py     Deterministic extraction, California deadlines, missing-evidence checklists
casebridge/llm.py       watsonx.ai / Ollama client (standard library only)
casebridge/brief.py     The agent pipeline: rules -> Granite -> guardrails
casebridge/safety.py    Citation enforcement, advice guardrail, PII redaction
casebridge/matching.py  Explainable lawyer matching
data/                   Fictional demo case and fictional lawyer profiles
.streamlit/config.toml  App theme (colours, font); serves static/ so the font works offline
static/fonts/           Atkinson Hyperlegible font files (SIL Open Font License)
PRODUCT.md              Product context used by the Impeccable design skill
tests/                  Automated tests
scripts/                README auto-update script
AGENTS.md               Rules for the team and for AI coding agents
```

## Team
| Role | Area |
|---|---|
| AI engineer | Granite setup, brief generation, citations, Granite Guardian |
| Data & safety engineer | Evidence intake, speech-to-text, redaction, legal rules, matching, tests |
| Product & pitch lead | App UI, demo, README, deck, video, Devpost |

How we work together is in [AGENTS.md](AGENTS.md). How we used IBM Bob is in [BOB_USAGE.md](BOB_USAGE.md).

## Limitations and next steps
- **Legal model:** California Business & Professions Code §6155 regulates lawyer referral services
  (*Jackson v. LegalMatch*, 2019). CaseBridge is designed so the client owns their brief and chooses
  who sees it, with no referral fees. The production path is partnering with State Bar–certified
  referral services, or licensing the brief tool to law firms for intake.
- Photos and audio rely on captions or transcripts for now. Next: speech-to-text and a vision model.
- Redaction is pattern-based. Next: a named-entity model plus Granite Guardian checks on output.
- Deadlines cover general California rules only.
- All people, lawyers and cases in `data/` are fictional.

<!-- AUTO:CHANGELOG:START -->
## Recent changes

| Date | Author | Change |
|---|---|---|
| 2026-10-24 | Claude | docs: log all 10 Bob sessions in BOB_USAGE.md |
| 2026-10-24 | Claude | ui: add "Which language will you speak?" pills for voice memos |
| 2026-10-24 | Claude | ingest: let the client choose the spoken language for Whisper |
| 2026-10-24 | Claude | rules: stop deadlines crashing on month-end and Feb 29 incidents |
| 2026-10-24 | Claude | rules: read the county from the list of California counties |
| 2026-10-23 | Shahzod Bakhriev | safety_checks_ADD |
| 2026-10-23 | Shahzod Bakhriev | responsible_ai_ADD |
| 2026-10-24 | Claude | ui: add Bao demo button and fix "1 lawyers" wording |
| 2026-10-23 | Shahzod Bakhriev | legal_rules_update |
| 2026-10-23 | Shahzod Bakhriev | test_bob_coverage |
<!-- AUTO:CHANGELOG:END -->
