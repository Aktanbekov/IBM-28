# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: people who were hurt in an accident in California.** They sit down at a laptop at home with a
scattered pile of evidence: photos, voice memos, police reports, insurer letters, ER paperwork. They are
stressed, possibly still injured, and often facing an insurer pushing a quick release. Their job: get that
pile into an order a lawyer can understand in a couple of minutes, and find a lawyer who actually handles
their kind of case for their side.

**Secondary: lawyers in the portal.** Injury and defense lawyers browse anonymized cases filtered to their
practice areas, sides and counties, request to connect, and read full briefs that clients chose to send them.

## Product Purpose

CaseBridge turns scattered accident evidence into a cited case brief (timeline, people involved, injuries,
costs and losses, deadlines, missing evidence), then matches the person with lawyers who handle that case
type for their side. Success means hours of confused intake become about two minutes of reading for the
lawyer, and the person reaches a lawyer who takes their kind of case, without the AI giving legal advice.

## Positioning

- The client owns the brief and decides who sees it. Lawyers see an anonymized version until the client
  accepts them. There are no referral fees.
- Every statement in the brief cites the evidence it came from (`E1`, `E2`, …). Uncited AI output is
  dropped, and the brief says how many statements were removed.
- Matching is side-aware and explainable: lawyers are filtered by practice area and by which side they
  represent, and every match shows why.
- No case-value score exists anywhere. The lawyer board is sorted by date posted, so small cases are not skipped.

## Operating Context

- Laptop only. Phone layouts are not a target.
- Client flow, in order: **1 · Tell us what happened** (add evidence) → **2 · Your case brief** (confirm
  case type, side and county) → **3 · Find a lawyer** (send the brief, or post an anonymized case) →
  accept a lawyer's connect request. Lawyers use a separate **Lawyer portal** with a case board and an inbox.
- The brief is built by IBM Granite (watsonx.ai or local Ollama) or by an offline rule-based engine.
  Deadlines and missing-evidence checklists always come from deterministic rules with statute citations.
- Hackathon prototype for SpartHill Hacks 2026, IBM AI Challenge. The full demo (Maria's case) must run
  offline with no network or API keys.

## Capabilities and Constraints

- Built in Streamlit (`app.py`), Python 3.12+. Design work happens within what Streamlit can render and theme.
- Case types: car / auto accident, slip & fall / premises liability, dog bite, workplace injury, medical
  malpractice.
- Both sides are supported: "I was harmed (making a claim)" and "Someone is claiming against me".
- Interface language: English only for now. Evidence can be in any language; detected language feeds matching.
- Rules the interface must never break (full list in `AGENTS.md` §2):
  - No legal advice: no outcome predictions, no "you should sign / settle / sue", no case valuations.
  - Every brief statement shows its evidence ids.
  - Deadlines are always labeled "confirm with a lawyer".
  - No sorting or ranking of cases by expected payout.
  - Anything on the lawyer board goes through redaction until the client accepts.
  - The client confirms case type, side and county, and chooses who sees their brief.
- Voice memos are transcribed on the laptop (faster-whisper). Photos rely on the client's caption; optional
  automatic photo reading uses a third-party model and is off by default. Not built yet: Granite Vision.
- Undecided: translating the interface beyond English.

## Brand Commitments

- Name: **CaseBridge**.
- Line: "From a stressful pile of evidence to the right lawyer, without legal advice from a bot." (README and
  the app's sidebar.)
- Voice: plain and calm. The people reading it are stressed accident victims. CaseBridge organizes
  information and says so; it never sounds like it is advising.

## Evidence on Hand

- `data/demo_case/`: Maria's fictional case, six items (voice memo, two photo descriptions, police
  report, insurer letter, ER discharge).
- `data/lawyers.json`: 12 fictional lawyer profiles, including fictional ratings, review counts and review snippets.
- `SEED_BOARD` in `app.py`: three fictional anonymized cases for the lawyer board.
- Absent, and not to be fabricated: real users, real lawyers or firms, testimonials, case outcomes,
  partnerships (including State Bar–certified referral services), press, usage numbers, and a logo.
  Fictional ratings and reviews must never be presented as real.

## Product Principles

1. **Organize, never advise.** CaseBridge arranges facts and points to sources; decisions belong to the
   person and their lawyer.
2. **Show the source.** Any statement the person or a lawyer reads can be traced back to a piece of evidence.
3. **The client is in control.** Nothing about them reaches a lawyer without their choice, and they
   confirm what the AI inferred.
4. **No case is too small.** Visibility never depends on estimated value.
5. **Calm over clever.** Someone stressed and hurt should always know where they are and what happens next.
