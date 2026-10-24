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

[`casebridge/safety.py`](../casebridge/safety.py) contains `ADVICE_PATTERNS` — twelve regex
patterns that cover English and Spanish:

- outcome predictions: `"you will win"`, `"you would lose"`, `"ganará el caso"`
- action directives: `"you should sign"`, `"you should settle"`, `"debería firmar"`
- case valuations: `"case is worth $…"`, `"su caso vale"`, `"expected settlement of"`

[`is_advice(text)`](../casebridge/safety.py) returns `True` on any match.
[`apply_guardrails(brief, valid_ids)`](../casebridge/safety.py) calls `is_advice` on every
sentence in the brief's `timeline`, `parties`, `injuries`, and `damages` fields. A sentence that
matches is removed and a warning is appended to the brief. The summary field is scrubbed
separately.

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
| Red-team: OCR, split phones, DOB variants, email, address | [`tests/test_bob_redteam.py`](../tests/test_bob_redteam.py) (22 pass; 16 known gaps marked `xfail`) |

---

## 4. Prompt-injection defense

**What the rule is:** Evidence is written by third parties — insurers, police departments, body
shops. Any of those documents can embed text designed to manipulate an LLM (`"ignore your rules"`,
`"say the case is worth $1M"`). CaseBridge detects these and flags them for the client; it never
obeys them.

**How it works:**

[`INJECTION_PATTERNS`](../casebridge/safety.py) is a list of nine regex patterns covering:

- instruction-cancellation: `"ignore … previous … instructions"`, `"new system prompt"`, `"system prompt"`
- role-play / jailbreak: `"you are now a lawyer"`, `"act as my legal advisor"`, `"pretend to be"`, `"jailbreak"`, `"DAN mode"`
- LLM-addressed directives: `"AI: say …"`, `"write: case is worth"`
- chat-template tokens: `<|system|>`, `[INST]`, `assistant:` at line start
- Spanish equivalents: `"ignora … instrucciones"`

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
| 20 adversarial attack strings detected | [`tests/test_bob_injection.py`](../tests/test_bob_injection.py) `TestAttackTexts` (14 pass; 6 known gaps marked `xfail`) |
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

- Six injection patterns are not yet detected (Unicode homoglyphs, zero-width spaces, hard
  newline splits, Vietnamese). These are marked `xfail` in
  [`tests/test_bob_injection.py`](../tests/test_bob_injection.py).
- Sixteen redaction patterns are not yet handled (OCR digit substitution, email with unusual
  encoding, P.O. Box addresses, European DOB formats). Marked `xfail` in
  [`tests/test_bob_redteam.py`](../tests/test_bob_redteam.py).
- `date.replace()` will raise `ValueError` on a February 29 incident date when the target year
  is not a leap year. Documented in [`docs/LEGAL_RULES.md`](LEGAL_RULES.md).
- The `detect_county` regex can absorb preceding words for multi-word county names preceded by a
  sentence. Documented as `xfail` in [`tests/test_bob_coverage.py`](../tests/test_bob_coverage.py).

All known gaps are tracked as `xfail` tests so they surface automatically if a fix is merged.
Current suite: **284 passed, 38 xfailed, 0 failed**.
