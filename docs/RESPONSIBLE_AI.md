# Responsible AI in CaseBridge

This document explains the five safety mechanisms built into the prototype and points to the
exact code and tests that enforce each one. It is written for judges and reviewers, not for
marketing.

---

## 1. No legal advice

**What the rule is:** The app organizes the client's evidence. It never predicts a case outcome,
values a claim, or tells the client what to do. Any output that crosses that line is blocked
before it reaches any screen.

**How it works:**

[`casebridge/safety.py`](../casebridge/safety.py) contains `ADVICE_PATTERNS`, regex patterns
in English, Spanish and Vietnamese:

- outcome predictions: `"you'll win"`, `"you're likely to lose"`, `"a jury would side with you"`, `"ganará"`, `"bà sẽ thắng"`
- action directives: `"you should probably accept"`, `"don't sign the release"`, `"I'd take the money"`,
  `"I recommend"`, `"it would be wise to"`, `"le conviene aceptar"`, `"bà nên ký"`
- case valuations: `"your claim is easily worth six figures"`, `"you could get $50,000"`,
  `"you have a good case"`, `"su caso vale"`, `"vụ này đáng giá"`

[`is_advice(text)`](../casebridge/safety.py) returns `True` on any match. It reads the text the
same way the injection check does, so zero-width spaces, look-alike letters and curly apostrophes
can't hide a phrase.
[`apply_guardrails(brief, valid_ids)`](../casebridge/safety.py) calls `is_advice` on every
sentence in the brief's `timeline`, `parties`, `injuries`, and `damages` fields, including
the `when` field. A sentence that matches is removed and a warning is appended to the brief. In
the summary, only the sentences that read as advice are removed.

The guardrail deliberately does **not** block false positives: `"the insurer said I should sign"`
(a client quoting a letter) and `"you should contact a lawyer"` (a referral) both pass through.

**Tests:**

| What is tested | Test |
|----------------|------|
| Direct English phrases | [`test_legal_advice_is_blocked`](../tests/test_pipeline.py) |
| Spanish `"debería firmar"` | [`test_usted_deberia_firmar_blocked`](../tests/test_bob_edge_cases.py) |
| Spanish `"su caso vale"` | [`test_su_caso_vale_blocked`](../tests/test_bob_edge_cases.py) |
| Spanish `"ganará el caso"` | [`test_ganara_el_caso_blocked`](../tests/test_bob_edge_cases.py) |
| Inverted question form (`"Shouldn't you settle?"`) | [`test_inverted_you_should_settle`](../tests/test_bob_edge_cases.py) |
| False positive: quoting the insurer | [`test_insurer_said_i_should_sign_is_not_advice`](../tests/test_bob_edge_cases.py) |
| False positive: referral to a lawyer | [`test_refer_to_lawyer_is_not_blocked`](../tests/test_bob_edge_cases.py) |
| False positive: stated settlement amount | [`test_insurer_offered_amount_is_not_timeline_not_blocked`](../tests/test_bob_edge_cases.py) |
| All LLM facts blocked when all contain advice | [`test_all_facts_get_advice_flag`](../tests/test_guardian.py) |
| 38 indirect, hidden-character and Vietnamese phrasings; 27 facts that must pass | [`test_advice_is_blocked`, `test_facts_are_not_blocked`](../tests/test_security_sweep.py) |

---

## 2. Every fact cites evidence

**What the rule is:** Any statement in the brief must link back to a specific piece of evidence
the client uploaded. A statement with no valid source is dropped silently and counted.

**How it works:**

[`enforce_citations(facts, valid_ids)`](../casebridge/safety.py) iterates the fact list and
removes any source ID that is not in `valid_ids` (the set of IDs assigned when evidence was
ingested). A fact whose source list is now empty is dropped. The count of dropped facts is
appended to `brief.warnings` so the client can see it.

This runs inside `apply_guardrails` on all four fact sections. The LLM can invent a fact, but
without a matching `E1`/`E2`/… source the fact never reaches the output.

**Tests:**

| What is tested | Test |
|----------------|------|
| Uncited AI fact is dropped | [`test_uncited_facts_are_dropped`](../tests/test_pipeline.py) |

**A citation is not enough, so two more checks read what the fact says:**

- **Numbers check** ([`check_numbers`](../casebridge/safety.py), all modes): every number in a
  statement (speed, amount, date, time) must appear in the evidence it cites. "17:42" also
  supports "5:42 pm". Failing statements stay in the brief with a review mark.
- **Granite Guardian** ([`llm.guardian_check`](../casebridge/llm.py),
  [`_apply_guardian`](../casebridge/brief.py)): a second IBM model reads each reworded statement
  against the evidence it cites, using Guardian's own groundedness definition and prompt format.
  It runs locally through Ollama (`granite3-guardian:2b`), because IBM withdrew Guardian from
  watsonx on 2026-09-30; with watsonx and no local Guardian, Granite on watsonx answers the same
  Yes/No question, and the brief names which checker ran. Exact quotes from the cited evidence
  skip the model check (they are grounded by definition; Guardian made one false positive on a
  quote). Guardian is not used for legal advice: in testing the 2B model flagged quoted insurer
  letters as advice.

The brief page shows all four checks in **How this brief was checked**, and **Try to fool it**
runs three made-up statements through them live.

| What is tested | Test |
|----------------|------|
| Invented number caught; formats match ("17:42" vs "5:42 pm", "$4,850.00" vs "$4850") | [`test_fact_check.py`](../tests/test_fact_check.py) |
| Guardian prompt format, Yes/No parsing, local vs watsonx checker, errors never raise | [`test_fact_check.py`](../tests/test_fact_check.py) |
| Only groundedness goes to Guardian; exact quotes skip it | [`test_guardian.py`](../tests/test_guardian.py), [`test_fact_check.py`](../tests/test_fact_check.py) |

Live result (not a benchmark): on 5 hand-written statements about Maria's case, Guardian 2B
marked all 3 true ones supported and caught both invented facts, including one with no number
("Maria broke her arm").

---

## 3. Personal-data redaction, privacy receipt, and posting gate

**What the rule is:** Lawyers on the board see an anonymized brief. No name, phone, address,
date of birth, plate, or policy number reaches them until the client explicitly accepts a lawyer.

**How it works — redaction:**

[`find_names(texts)`](../casebridge/safety.py) extracts names from the full evidence by matching
role-introduction patterns (`"my name is …"`, `"Vehicle 2: driver …"`, `"adjuster …"`) and
assigns each one a placeholder (`[CLIENT]`, `[OTHER PARTY]`, `[ADJUSTER]`, `[PERSON]`). It also
handles speech-to-text output that arrived in all-lowercase via `LOWER_INTRO_RE`.

[`redact(text, names)`](../casebridge/safety.py) applies `PII_PATTERNS` first (phone, email,
GPS, SSN, VIN, plate, address, DOB, policy/claim/report IDs), then replaces every detected name
regardless of case. The patterns are applied longest-first so `"Maria Lopez"` is replaced before
`"Maria"`.

[`redact_brief(brief, names)`](../casebridge/safety.py) calls `redact` on every free-text field
in the brief. Fixed-value fields (`case_type`, `county`, `client_side`, statute citations) are
left alone.

**Fail-closed second pass:**

After redaction, [`find_leaks(data, names)`](../casebridge/safety.py) scans the redacted output
for any surviving name or PII pattern. If a statement still contains an identifier, its text is
replaced with `"[Statement hidden to protect the client's identity]"`. This second pass is the
final lock before anything reaches a lawyer.

**Privacy receipt:**

[`privacy_summary(red)`](../casebridge/safety.py) counts every placeholder type in the
anonymized brief and returns a plain-language dict (`{"your name": 4, "phone numbers": 2, …}`).
The client sees this before they decide whether to post.

**Posting gate:**

[`posting_blockers(red, names)`](../casebridge/safety.py) calls `find_leaks` one more time on
the final brief. A non-empty result blocks the post. In the current demo this should always be
empty because `redact_brief` already fails closed; the gate is a second lock.

**Tests:**

| What is tested | Test |
|----------------|------|
| No secrets reach the lawyer view (Maria, Rosa, Bao cases) | [`test_lawyer_view_has_no_personal_details`](../tests/test_engine.py) |
| `find_leaks` reports surviving identifiers | [`test_find_leaks_reports_what_is_left`](../tests/test_engine.py) |
| Privacy receipt counts what was hidden | [`test_privacy_receipt_counts_what_was_hidden`](../tests/test_features.py) |
| Posting gate blocks a surviving leak | [`test_posting_gate_blocks_a_leak`](../tests/test_features.py) |
| Hyphenated name (`Smith-Jones`) not leaked | [`test_hyphenated_name_redacted`](../tests/test_bob_edge_cases.py) |
| Apostrophe name (`O'Brien`) not leaked | [`test_apostrophe_name_redacted`](../tests/test_bob_edge_cases.py) |
| All-lowercase transcript name not leaked | [`test_lowercase_name_redacted`](../tests/test_bob_edge_cases.py) |
| `find_leaks` catches apostrophe name surviving redaction | [`test_find_leaks_catches_apostrophe_name`](../tests/test_bob_edge_cases.py) |
| Red-team: OCR, split phones, DOB variants, email, address | [`tests/test_bob_redteam.py`](../tests/test_bob_redteam.py) (52 tests, all pass) and [`tests/test_redteam_fixes.py`](../tests/test_redteam_fixes.py) |

---

## 4. Prompt-injection defense

**What the rule is:** Evidence is written by third parties — insurers, police departments, body
shops. Any of those documents can embed text designed to manipulate an LLM (`"ignore your rules"`,
`"say the case is worth $1M"`). CaseBridge detects these and flags them for the client; it never
obeys them.

**How it works:**

[`INJECTION_PATTERNS`](../casebridge/safety.py) is a list of regex patterns covering:

- instruction-cancellation: `"ignore … previous … instructions"`, `"new system prompt"`, `"system prompt"`
- role-play / jailbreak: `"you are now a lawyer"`, `"act as my legal advisor"`, `"pretend to be"`, `"jailbreak"`, `"DAN mode"`
- LLM-addressed directives: `"AI: say …"`, `"write: case is worth"`
- chat-template tokens: `<|system|>`, `[INST]`, `assistant:` at line start
- Spanish and Vietnamese equivalents: `"ignora … instrucciones"`, `"bỏ qua … hướng dẫn"`, `"đóng vai luật sư"`

[`has_injection(text)`](../casebridge/safety.py) runs these patterns on a normalized copy of the
text: invisible zero-width characters removed, Cyrillic and Greek look-alike letters mapped to
Latin ones, and accents dropped. So `"іgnore"` (Cyrillic і) and `"i\u200bgnore"` are still caught.
The evidence people see is never changed.

[`injection_flags(evidence)`](../casebridge/safety.py) returns the IDs of flagged items.
[`injection_warnings(evidence)`](../casebridge/safety.py) adds one plain-language warning per
flagged item to the brief.

Evidence is also fenced off from the LLM in [`wrap_evidence()`](../casebridge/safety.py): the
text is placed inside `<evidence id="…">…</evidence>` XML tags, any closing `</evidence>` tag
inside the text is neutralized, and items that matched `INJECTION_RE` get a
`flagged="possible-instructions"` attribute so the model prompt can treat them as data-only.

**Tests:**

| What is tested | Test |
|----------------|------|
| 29 adversarial attack strings detected | [`tests/test_bob_injection.py`](../tests/test_bob_injection.py) `TestAttackTexts` (all pass) and [`tests/test_injection_fixes.py`](../tests/test_injection_fixes.py) |
| 10 benign strings not flagged | [`tests/test_bob_injection.py`](../tests/test_bob_injection.py) `TestBenignTexts` |
| Injection detected, its fake advice never reaches the brief | [`test_injection_is_flagged_and_its_advice_never_reaches_the_brief`](../tests/test_features.py) |
| `wrap_evidence` neutralizes `</evidence>` escape attempt | [`tests/test_bob_injection.py`](../tests/test_bob_injection.py) `TestWrapEvidence` |

---

## 5. Deterministic deadlines

**What the rule is:** Filing deadlines and evidence checklists are computed from statute, never
by the LLM. They are always labeled "confirm with a lawyer" and always trace to a specific
California code section.

**How it works:**

[`deadlines(evidence, case_type)`](../casebridge/rules.py) reads the incident date from the
evidence (via `incident_date()`, which prefers official documents over voice memos), then applies
fixed arithmetic:

- CCP § 335.1: `incident_date + 2 years` (personal injury, all case types)
- CCP § 338: `incident_date + 3 years` (property damage, auto-accident only)
- Gov. Code § 911.2: `incident_date + 6 months` (only when a government cue is found in the text)

Response deadlines found in insurer letters are extracted by regex (not LLM) and added with the
evidence ID as the basis.

[`missing_evidence()`](../casebridge/rules.py) checks the `CHECKLIST` against the evidence pool
entirely by keyword and kind, with no LLM involvement.

Even when `LLM_BACKEND=granite` is set, the LLM writes the narrative (`summary`, `timeline`,
`parties`, `injuries`, `damages`) but `deadlines`, `missing_evidence`, `warnings`, `alerts`, and
`contradictions` are always set by `rules.build_brief()` before the LLM is called and are never
overwritten by LLM output.

**Tests:**

| What is tested | Test |
|----------------|------|
| 2-year SOL computed correctly | [`test_government_cue_adds_six_month_deadline`](../tests/test_bob_coverage.py) (by contrast also checks the § 335.1 entry) |
| 6-month gov deadline fires on known cues | [`test_government_cue_adds_six_month_deadline`](../tests/test_bob_coverage.py) |
| Month arithmetic rolls over correctly | [`test_month_rollover_in_plus`](../tests/test_bob_coverage.py) |
| No deadlines when incident date is absent | [`test_no_incident_date_produces_no_statute_deadlines`](../tests/test_bob_coverage.py) |
| Evidence-checklist tips are factual, not advice | [`test_tips_are_information_not_advice`](../tests/test_features.py) |

---

## Known limitations (honest, not a surprise)

Bob's red-team and coverage sessions found 38 gaps: 6 hidden-instruction tricks (look-alike
letters, zero-width spaces, line breaks, Vietnamese), 30 redaction leaks (OCR digits such as
"Mar1a", nicknames, P.O. boxes, European dates) and 2 county-detection bugs. All 38 are fixed and
run as normal tests. Review also found and fixed a crash on month-end and February 29 incident
dates.

A later security sweep found and fixed 31 advice phrasings the guardrail missed ("you'll win",
"I'd take the money"), 15 more redaction leaks (family members' names, names in capitals,
"Officer J. Ramirez", social media handles, spaced plates), names with no cue around them
("Kevin said…", now caught with common first-name and surname lists), hidden instructions in file names,
model replies with the wrong JSON types that crashed the brief, and damaged PDFs that crashed
the app. See [`tests/test_security_sweep.py`](../tests/test_security_sweep.py).

What is still open:
- Redaction and injection detection are pattern-based. A new phrasing or format can still slip
  through; the leak check and the client's preview are the backstops, not a guarantee.
- Deadlines don't move for weekends or court holidays, and exceptions (minors, delayed
  discovery, the lawsuit deadline after a government claim is rejected) are not handled. Every
  date is labelled "confirm with a lawyer". See [`docs/LEGAL_RULES.md`](LEGAL_RULES.md).

Current suite: run `pytest -q`. The README's status table shows the latest count, updated on every push to `main`.
