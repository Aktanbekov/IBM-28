---
version: 1
slug: "app-py"
primary_target: "app.py"
related_targets: []
---

# CaseBridge app (app.py)

Scope: the whole Streamlit app: client flow (1 Tell us what happened, 2 Your case brief, 3 Find a lawyer) and the Lawyer portal. Visitor mode: Operate. Laptop only (1280-1600 wide). Build path: code-led.

Audience and job: a stressed accident victim at home turning a pile of evidence into a cited brief and reaching the right lawyer; lawyers scanning anonymized cases. Constraints: AGENTS.md section 2, offline mode, Streamlit only, widget keys and routing unchanged. Design prompt: docs/frontend-design-prompt.md.

Memorable moment: a fact's evidence tag and the highlighted sentence in its source share one highlighter colour.

## Direction contract

THESIS: Your own paperwork, marked up: every fact carries the highlighter colour of the document it came from. Refuses the default of grey cards with blue pills and emoji headings.

OWN-WORLD: White office paper ground, graphite ink text, ballpoint-blue rail and primary actions, six fluorescent highlighter colours used only for evidence identity (E1 yellow, E2 pink, E3 green, E4 blue, E5 lilac, E6 peach, cycling), black-marker chips for redactions, one red rule reserved for time-sensitive notices. Atkinson Hyperlegible, self-hosted, one family.

STORY: The person sees their pile become an ordered, sourced brief, checks any fact against the original, confirms what the AI inferred, and chooses which lawyer sees it.

FIRST VIEWPORT: Blue rail left with the three steps (done ticks, current step swiped in yellow) and a separated Lawyer portal; engine status and "not legal advice" at its foot. Main: page title, one-line lead, then the page's single primary action. On the brief: labeled confirm strip, time-sensitive notice, then a timeline with a fixed date column beside the highlighted source panel.

FORM: Marked-up paperwork, candidate 3 of 7. seed:168a381b2a0087ea

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
