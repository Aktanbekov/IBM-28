# Legal Rules Reference — CaseBridge

> **General information only. Every deadline and rule on this page is a starting point.
> Confirm every date and exception with a licensed California attorney before relying on it.**

This document maps each statute cited in `casebridge/rules.py` to a plain-language explanation,
explains how the code computes the date, and lists the exceptions CaseBridge does **not** handle.
It is maintained by the data-safety engineer and reviewed before every major milestone.

---

## 1. Cal. Code Civ. Proc. § 335.1 — Personal-injury statute of limitations (2 years)

### What the statute says
CCP § 335.1 sets a two-year period to bring a lawsuit for personal injury in California. The clock
normally starts on the date of the injury (the incident date). If the plaintiff does not file a
civil lawsuit within that window, the court will generally dismiss the claim as time-barred.

### How CaseBridge computes it
`deadlines()` in `rules.py` calls `plus(years=2)`, which replaces the incident year with
`start.year + 2` while keeping the same month and day:

```python
out.append({"label": "General personal-injury filing deadline (CA, 2 years)",
            "date": plus(years=2), "basis": "Cal. Code Civ. Proc. § 335.1"})
```

**Assessment:** The calendar arithmetic is correct for the common case (e.g., October 14, 2026 →
October 14, 2028). No adjustment is made if the computed date falls on a weekend or court holiday;
a February 29 incident used to crash the calculation. *Fixed Oct 24: the date moves to the last
day of the month (February 28), the earlier of the two possible dates.*

### Exceptions CaseBridge does NOT handle
| Exception | Statute | Effect |
|-----------|---------|--------|
| **Minor plaintiffs** | CCP § 352(a) | SOL is tolled until the minor turns 18, giving up to 2 years after the 18th birthday. |
| **Delayed discovery** | CCP § 335.1 (as interpreted) | If the injury is latent (e.g. internal trauma not discovered until later), the clock may start when the plaintiff knew or reasonably should have known of the injury. |
| **Mental incapacity** | CCP § 352(a) | SOL is tolled while the plaintiff is legally incapacitated. |
| **Government defendant** | Gov. Code § 911.2 | A 6-month claim-presentation deadline applies *before* any lawsuit (see §3 below). |
| **Felony assault/battery** | CCP § 340.3 | 10 years from the date of the crime if the defendant was convicted of a felony. |
| **Childhood sexual abuse** | CCP § 340.1 | Special extended deadlines; not applicable to the cases CaseBridge handles. |

---

## 2. Cal. Code Civ. Proc. § 338 — Property-damage statute of limitations (3 years)

### What the statute says
CCP § 338 provides a three-year limitation period for damage to property. For auto accidents
this covers the vehicle and other physical property (not personal injury, which is § 335.1).
CaseBridge applies this only when `case_type == "auto_accident"`.

### How CaseBridge computes it
```python
if case_type == "auto_accident":
    out.append({"label": "Property-damage filing deadline (CA, 3 years)",
                "date": plus(years=3), "basis": "Cal. Code Civ. Proc. § 338"})
```

`plus(years=3)` adds three to the incident year, same calendar caveats as above.

**Assessment:** The label and the arithmetic match the general rule. CaseBridge only cites
`§ 338` for auto accidents; it does not attempt to distinguish the many sub-sections of § 338
(fraud, trespass to real property, etc.), which is appropriate for its narrow scope.

### Exceptions CaseBridge does NOT handle
| Exception | Note |
|-----------|------|
| **Hidden / latent damage** | The delayed-discovery rule can extend the clock if damage was not discoverable at the time of the incident. |
| **Statute applies to real and personal property** | For property other than a vehicle (e.g. cargo), the same 3-year rule applies but CaseBridge does not surface this for other case types. |

---

## 3. Cal. Gov. Code § 911.2 — Government-entity claim presentation deadline (6 months)

### What the statute says
Before suing a California public entity (a city, county, school district, transit agency, etc.)
for personal injury or property damage, the claimant must first file a Government Tort Claim with
that entity. § 911.2 requires this presentation within **six months** of the date the cause of
action accrued. This is an *administrative* deadline — it is a prerequisite to any lawsuit, not
the lawsuit filing deadline itself.

After the entity denies the claim (or after 45 days if it does not respond), the plaintiff
typically has **six months** to file the actual lawsuit (Gov. Code § 945.6).

CaseBridge shows this deadline whenever evidence contains a keyword from `GOVERNMENT_CUES`:

```python
GOVERNMENT_CUES = ["city bus", "vta", "bart", "muni", "caltrans", "city of", "county vehicle",
                   "police car", "school bus", "pothole"]
```

### How CaseBridge computes it
```python
if any(c in text for c in GOVERNMENT_CUES):
    out.append({"label": "Claim against a government entity (CA, 6 months)",
                "date": plus(months=6), "basis": "Cal. Gov. Code § 911.2"})
```

`plus(months=6)` adds 6 to the incident month and carries the year if needed:

```python
def plus(years=0, months=0):
    m = start.month - 1 + months
    y = start.year + years + m // 12
    return start.replace(year=y, month=m % 12 + 1).isoformat()
```

**Assessment:** The arithmetic is correct for the 12 common cases (January + 6 = July, etc.).
An incident on August 31 used to crash, because February has no 31st. *Fixed Oct 24: the day is
clipped to the last day of the target month (February 28), so the date shown is never later
than the real one.* The 6-month calculation also does not follow any "next-business-day" rule.

**Important framing gap:** The label says "6 months" but does not distinguish the
*claim-presentation* deadline from the *lawsuit-filing* deadline after rejection (§ 945.6).
The current display is conservative (it highlights the earlier, harder deadline) and the label
explicitly says "confirm with a lawyer", but future versions should mention the two-step process.

### Exceptions CaseBridge does NOT handle
| Exception | Statute / Note |
|-----------|---------------|
| **Suit deadline after claim rejection** | Gov. Code § 945.6: 6 months after written rejection, or 2 years if the entity never responds. |
| **Late-claim petition** | Gov. Code § 911.4/§ 946.6: a claimant who missed the 6 months may petition for leave to present a late claim, with strict requirements. |
| **Minor claimants** | Gov. Code § 911.4: a minor has until 6 months after turning 18 to present a late claim. |
| **Federal entities** | Federal Tort Claims Act deadlines apply to federal agencies (e.g., postal vehicles); Gov. Code § 911.2 does not. |
| **Keyword gaps** | `GOVERNMENT_CUES` uses keyword matching. A government vehicle not in the list (e.g. "state highway patrol", "SFMTA") will not trigger the alert. |

---

## 4. `INSURER_TACTICS` — tactic explanations and "ask" prompts

Each entry in `INSURER_TACTICS` has a `meaning` (plain-language explanation of the term) and an
`ask` (a question to bring to a lawyer). These are informational, not directives.

| Title | Assessment |
|-------|------------|
| Recorded statement requested | Accurate: insurers can use recordings to find inconsistencies. The `ask` correctly frames it as a question, not a prohibition. |
| "Full and final" settlement language | Accurate: explains the finality risk. Does not advise rejection. |
| Medical records authorization | Accurate: flags the scope risk. Does not advise refusal. |
| Suggestion that you share the blame | Accurate: explains California comparative fault without quantifying it. |
| Pressure to decide quickly | Accurate: distinguishes insurer deadlines from legal filing deadlines. |
| Suggestion that a lawyer isn't needed | Accurate: notes free consultations without telling the client to hire anyone. |

**None of the `ask` fields cross into legal advice** — each ends with a question for a lawyer,
not a recommendation. This satisfies product rule §2.1.

---

## 5. `CHECKLIST` and `EVIDENCE_TIPS` — items with legal significance

Most checklist items are practical (photograph, call the police, get records). A few have
legal significance worth noting:

| Item | Note |
|------|------|
| **Request to keep the security camera footage** | Under California law, a business has no automatic duty to preserve evidence before a litigation hold is placed. Requesting preservation in writing creates a paper trail. Failure to preserve after notice can be relevant in litigation. This tip is time-sensitive (systems often overwrite within 24–72 hours). CaseBridge does not generate the written request for the client; it only reminds them to make one. |
| **Animal control or bite report** | Clinics are required to report animal bites under California Health & Safety Code § 121695. The report exists even if the client did not file one. |
| **Other driver's insurance details** | Under California Vehicle Code § 16025, drivers must exchange insurance information at the scene. CaseBridge lists this as a checklist item but does not note the legal obligation on the other driver. |
| **Proof of lost wages** | Lost-wage damages require documentation. CaseBridge's tip (pay stubs or employer letter) aligns with what California courts require as proof of economic damage. |

---

## 6. General limitations — rules CaseBridge cannot apply

The following situations require attorney analysis. CaseBridge will surface the standard
deadlines but cannot detect these cases automatically.

- **MICRA — Medical Injury Compensation Reform Act (CCP § 340.5):** Medical malpractice claims have a 3-year SOL from the date of injury **or** 1 year from the date the plaintiff discovered (or should have discovered) the injury, whichever is earlier. CaseBridge uses § 335.1 (2 years) for all injury claims.
- **Workers' compensation exclusivity:** An employee injured on the job is generally limited to workers' comp and cannot sue the employer in civil court (Labor Code § 3602). CaseBridge may surface a personal-injury SOL for a workplace case even though the correct channel is the Workers' Compensation Appeals Board.
- **Dog-bite strict liability scope (Civil Code § 3342):** Strict liability applies only to bites. Other dog-caused injuries (e.g. knocked down by a jumping dog) may require proving negligence. CaseBridge does not distinguish bite from non-bite dog-injury cases.
- **UM/UIM claim deadlines:** Uninsured and underinsured motorist claims are governed by the insurance policy contract, not solely by CCP § 335.1. Policy deadlines can be shorter and must be read case by case.
- **Wrongful death:** A separate SOL (CCP § 335.1, 2 years from date of death) applies; the decedent's personal injury claim may have a different clock. CaseBridge has no wrongful-death case type.
- **February 29 and month-end edge cases:** fixed Oct 24. `rules.deadlines` clips the day to the end of the month instead of raising `ValueError` (tested in `tests/test_bao_fixes.py`).
- **Weekend / holiday adjustment:** CaseBridge does not roll SOL dates forward to the next court day. Clients should confirm exact dates.

---

*This file is general information only. Confirm all deadlines with a licensed California attorney.*
