---
name: CaseBridge
description: From a stressful pile of evidence to the right lawyer, without legal advice from a bot.
colors:
  pen-blue: "#2A4BB8"
  pen-blue-deep: "#2341A3"
  rail-rule: "#4D68C6"
  rail-ring: "#C3CDF5"
  rail-text: "#E4E9FB"
  rail-text-soft: "#DCE3FA"
  paper: "#FFFFFF"
  paper-grey: "#F3F4F8"
  blue-wash: "#F0F3FC"
  red-wash: "#FDF3F1"
  graphite-ink: "#1E2230"
  graphite-muted: "#4A5068"
  source-ink: "#2C3142"
  pencil-grey: "#8A90A6"
  widget-border: "#DADDE6"
  row-rule: "#E3E5EC"
  deadline-red: "#B42318"
  highlighter-yellow: "#FFE45C"
  highlighter-pink: "#FF9FD0"
  highlighter-green: "#9AF0B3"
  highlighter-blue: "#9ADCFF"
  highlighter-lilac: "#D4C2FF"
  highlighter-peach: "#FFC9A3"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 700
  headline:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
  title:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 700
    lineHeight: 1.3
  brand:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    letterSpacing: "-0.01em"
  lead:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.5
  source:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.92rem"
    fontWeight: 400
    lineHeight: 1.65
  meta:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 700
  date:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 700
    fontFeature: "tnum"
  tag:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: "1.4rem"
    fontFeature: "tnum"
  redaction:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 700
    lineHeight: "1.35rem"
    letterSpacing: "0.03em"
rounded:
  hairline: "2px"
  chip: "3px"
  nav: "4px"
  base: "6px"
  round: "50%"
spacing:
  tag-inset: "0.4rem"
  row: "0.6rem"
  notice-y: "0.75rem"
  notice-x: "1rem"
  strip-gap: "1.5rem"
  page-top: "2.5rem"
  date-column: "7.25rem"
components:
  button-primary:
    backgroundColor: "{colors.pen-blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.base}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.base}"
  button-tertiary:
    textColor: "{colors.graphite-ink}"
  evidence-tag-e1:
    backgroundColor: "{colors.highlighter-yellow}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  evidence-tag-e2:
    backgroundColor: "{colors.highlighter-pink}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  evidence-tag-e3:
    backgroundColor: "{colors.highlighter-green}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  evidence-tag-e4:
    backgroundColor: "{colors.highlighter-blue}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  evidence-tag-e5:
    backgroundColor: "{colors.highlighter-lilac}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  evidence-tag-e6:
    backgroundColor: "{colors.highlighter-peach}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  redaction-mark:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.paper}"
    typography: "{typography.redaction}"
    rounded: "{rounded.hairline}"
    padding: "0 0.4rem"
  sent-chip:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.pen-blue}"
    rounded: "{rounded.chip}"
    padding: "0.15rem 0.55rem"
  notice-state:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.body}"
    padding: "0.75rem 1rem"
  notice-time:
    backgroundColor: "{colors.red-wash}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.body}"
    padding: "0.75rem 1rem"
  notice-safety:
    backgroundColor: "{colors.paper-grey}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.body}"
    padding: "0.75rem 1rem"
  notice-note:
    backgroundColor: "{colors.paper-grey}"
    textColor: "{colors.graphite-ink}"
    typography: "{typography.body}"
    padding: "0.75rem 1rem"
  container:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.base}"
  confirm-strip:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.base}"
  rail:
    backgroundColor: "{colors.pen-blue}"
    textColor: "{colors.paper}"
  nav-item:
    textColor: "{colors.rail-text}"
    typography: "{typography.body}"
    rounded: "{rounded.nav}"
    padding: "0.5rem 0.55rem"
  nav-item-hover:
    backgroundColor: "{colors.pen-blue-deep}"
    textColor: "{colors.rail-text}"
    rounded: "{rounded.nav}"
  nav-item-current:
    backgroundColor: "{colors.highlighter-yellow}"
    textColor: "{colors.graphite-ink}"
---

# Design System: CaseBridge

## Overview

**Creative North Star: "Marked-up Paperwork"**

CaseBridge looks like the person's own pile of paper after someone careful has gone through it with a pen and a set of highlighters. The ground is white office paper, the text is graphite ink, and a ballpoint-blue rail on the left holds the three client steps and a separated Lawyer portal. Every fact in the brief carries a small highlighter tag in the colour of the document it came from, and the same colour marks the cited sentence inside that document. That shared colour is the system's signature: the eye can travel from a claim to its source without reading an id.

The density is that of a well-kept file: ruled list rows, a fixed date column, short notices with a coloured top rule over a pale wash, and bordered containers only where something must be confirmed or compared. There is no ornament beyond the marks a person would make on paper: a highlighter swipe, a black marker bar over hidden details, a red rule on what is due soon. Native Streamlit widgets supply every control; the theme and one scoped CSS layer supply the world.

The world rejects the default dashboard look of grey cards with blue pills and emoji headings, and it never draws anything that reads as a score, a ranking by value, or a verdict.

**Key Characteristics:**
- White paper, graphite ink, one ballpoint-blue for the rail and primary actions.
- Six highlighter colours that only ever identify an evidence source (E1 to E6, cycling).
- Black marker chips only for what stays hidden until the client accepts a lawyer.
- One red, only for time-sensitive dates and findings.
- One typeface, Atkinson Hyperlegible, self-hosted; hierarchy from size and weight.
- Flat throughout: rules, washes and 1px borders, no shadows.

**Where tokens live.** Theme tokens are in `.streamlit/config.toml`: `primaryColor`/`linkColor` (pen-blue), `backgroundColor` (paper), `secondaryBackgroundColor` (paper-grey), `textColor` (graphite-ink), `borderColor` (widget-border), `redColor` (deadline-red), `baseRadius`/`buttonRadius` (base), `headingFontSizes` (display, headline, title), `paddingTop` (page-top), the three `fontFaces`, and the `[theme.sidebar]` block (pen-blue ground, pen-blue-deep secondary, rail-rule border, paper text, highlighter-yellow primary). Everything else lives in the `CSS` string at the top of `app.py` (the `cb-*` classes and the `st-key-*` selectors), and the highlighter list lives in `HIGHLIGHTERS` in `app.py`. Change a theme token in config.toml; change a world mark in the CSS layer; when a value appears in both (pen-blue, graphite-ink, paper-grey, deadline-red, highlighter-yellow), change both.

## Colors

A cool paper-and-ink palette with one ballpoint blue, one red, and six fluorescent highlighters that carry meaning, not mood.

### Primary
- **Ballpoint Blue** (pen-blue): the rail's ground, primary buttons, links, the "Brief sent" chip, the top rule of status notices, and the tick in "Why this match" lists and done steps.
- **Deep Ballpoint** (pen-blue-deep): the rail's hover and secondary ground only.

### Secondary: the highlighters
- **Highlighter Yellow, Pink, Green, Blue, Lilac, Peach** (highlighter-yellow, -pink, -green, -blue, -lilac, -peach): assigned in that order to E1 through E6 and cycling after that. They fill evidence tags, the id chip on each evidence expander, and the `mark` over each cited sentence in the source panel. Ink text on top, always.

### Tertiary
- **Deadline Red** (deadline-red): deadline dates within 30 days (with "in N days" beneath), and the top rule, title and due date of the "Found in your evidence" notice. Sits on **Red Wash** (red-wash) inside that notice.

### Neutral
- **Office Paper** (paper): page ground and container fill.
- **Paper Grey** (paper-grey): Streamlit's secondary background (inputs, selects), and the wash behind safety-check and engine notes.
- **Blue Wash** (blue-wash): the wash behind status notices and the "Brief sent" chip.
- **Graphite Ink** (graphite-ink): all primary text, the redaction marker, the confirm strip's border, the safety notice's rule.
- **Graphite Muted** (graphite-muted): meta lines, dates, legal bases, checklist boxes. Still body-legible; this is text that must be read.
- **Source Ink** (source-ink): the body of quoted source documents, a half-step softer than the brief's own text.
- **Pencil Grey** (pencil-grey): the top rule of the engine note only.
- **Widget Border** (widget-border): Streamlit's widget and container borders.
- **Row Rule** (row-rule): the hairline between list rows.
- **Rail tints** (rail-text, rail-text-soft, rail-ring, rail-rule): nav labels, tagline and foot text, the step-number rings, and the divider above the Lawyer portal, all on the blue rail.

### Named Rules
**The Source-Colour Rule.** In the content area, a highlighter colour means exactly one thing: "this came from that source." Never use one for status, category, emphasis, decoration or charts. The rail's current-step swipe and text selection use highlighter yellow; those are the only two non-evidence uses and no new ones are added.

**The Black Marker Rule.** A graphite-ink bar with white uppercase text means "hidden until the client accepts." It marks redacted tokens ([CLIENT], [OTHER PARTY]) and the "Anonymized" state on the lawyer board, and nothing else.

**The One Red Rule.** Deadline red is reserved for what is time-sensitive: dates within 30 days and the evidence finding that carries a response date. Errors, safety checks and engine notes never use it.

## Typography

**Display Font:** Atkinson Hyperlegible (with system-ui, sans-serif)
**Body Font:** Atkinson Hyperlegible (with system-ui, sans-serif)

**Character:** One family, built for low-vision legibility, with distinct letterforms and a slashed zero that keeps dates and ids unambiguous. Calm, plain and readable for someone tired and stressed. Self-hosted from `static/fonts/` (Regular 400, Bold 700, Italic 400) so offline mode never needs the network.

### Hierarchy
- **Display** (700, 2.125rem): the page title, one per page (`st.title`).
- **Headline** (700, 1.5rem): `st.subheader`: "Your evidence (N items)", lawyer names on match cards.
- **Title** (700, 1.3rem, 1.3): section headings inside a page (Timeline, Check a source, Deadlines to confirm with a lawyer).
- **Brand** (700, 1.5rem, -0.01em): the CaseBridge wordmark in the rail, set as type; no logo exists.
- **Lead** (400, 1.0625rem, 1.55, max 48rem): the one-line lead under each title and case summaries.
- **Body** (400, 0.95rem, 1.5): list rows, notices, nav labels.
- **Source** (400, 0.92rem, 1.65, pre-wrap): quoted source documents.
- **Meta** (400, 0.9rem, 1.5): secondary lines that still must be read: sources, rules, what is hidden, lawyer details.
- **Label** (700, 0.95rem): sentence-case labels above a group ("Please confirm. You know your situation best.", "Why this match").
- **Date** (700, 0.85rem, tabular): the date column and "Posted" dates.
- **Tag** (700, 0.75rem, 1.4rem line box, tabular): evidence ids.
- **Redaction** (700, 0.72rem, 0.03em, uppercase from the token itself): marker chips.

### Named Rules
**The One Family Rule.** Atkinson Hyperlegible at 400 and 700 (plus italic 400 for quoted reviews) is the only face. Hierarchy comes from size and weight, never from a second family or a light weight.

**The Readable Meta Rule.** Secondary text is graphite-muted at 0.9rem or larger, never a faint caption. If it has to be read to stay safe (what is hidden, which rule a date comes from), it is meta, not fine print.

## Layout

Wide layout with the blue rail on the left (Streamlit sidebar) and the page in the main column, 2.5rem from the top. Laptop only, 1280 to 1600 px; there is no phone layout. The rail stacks brand and tagline, the three numbered steps, a ruled divider, the Lawyer portal entry, and a foot pinned to the bottom with the engine status and "not legal advice".

Each page opens with title, lead, then its single primary action. The brief page follows the person's story: the summary, a one-line trust strip (statements cited, advice found, details hidden, hidden instructions), the full-width confirm strip (case type, side, county, Find lawyers), then only what needs attention now (time-sensitive notices, and one collapsed line per insurer document). Everything else sits in four tabs, one question each: **What happened** (facts 3:2 beside the source panel, each sentence shown once), **Deadlines and next steps** (deadlines beside the checklist), **How it was checked** (the check report), **Privacy** (the lawyer's view beside Where your data goes). Find a lawyer says once what every match shares, and each card shows only what else fits; five cards show, the rest open on request.

Lists are ruled rows (0.6rem vertical padding, row-rule hairline, no rule after the last). Dated lists use a fixed date column (date-column) with a 1rem gap, so the eye scans dates in one vertical line; in the narrow right column deadlines stack date over label instead. Inline facts strips (the lawyer's practice summary, case heads) wrap with 0.35rem by 1.5rem (strip-gap) gaps.

**The Date Column Rule.** Wherever facts are dated and there is room, the date sits in its own fixed column in tabular figures, never inline in the sentence.

## Elevation & Depth

Flat. The CSS layer declares no shadows and the theme adds none. Depth comes from three paper devices: a 1px widget-border outline at the base radius around containers that group something to compare or act on, a coloured 2px top rule over a pale wash for notices, and a blue rail that sits beside the page rather than above it.

**The Flat Paper Rule.** Nothing floats. Emphasis is a heavier rule or border (the confirm strip's 1.5px graphite-ink outline), never a shadow or a lift on hover.

## Shapes

Small, office-supply corners. Marks made on paper (evidence tags, redaction markers, highlighted sentences, checklist boxes) are near-square at 2px (hairline). The "Brief sent" chip is 3px, rail nav items 4px, and Streamlit buttons, inputs and containers 6px (base). The only round forms are the rail's step circles (round), which hold a step number, a tick when done, or an ink fill when current. Notices are square-cornered bands. The highlighter swipe on the current step is a flat band inset 8% top and bottom, like a real marker stroke.

## Components

### Buttons
Native Streamlit buttons with Material icons, quiet and plain.
- **Shape:** 6px corners (base).
- **Primary:** pen-blue fill, paper text. One per view: the step's next action (Build my case brief, Open my case brief, Find lawyers, Accept).
- **Secondary:** paper fill, widget-border outline, ink text (Load demo case, Send my brief, Request to connect, Rebuild).
- **Tertiary:** text only (Clear).
- **Disabled:** Streamlit's disabled secondary, used for "Request sent".

### Chips
- **Evidence tag:** highlighter fill by id, ink text, 2px corners, 0 0.4rem padding, tag type. Placed after the statement it supports, several in a row with 0.4rem between.
- **Redaction marker:** graphite-ink fill, paper text, 2px corners, redaction type. Inline wherever a hidden token appears.
- **Brief sent chip:** blue-wash fill, 1px pen-blue border, pen-blue bold text, 3px corners. A state, not a button.

### Cards / Containers
- **Corner Style:** 6px (base).
- **Background:** paper.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px widget-border via Streamlit's bordered container. Used for lawyer match cards, lawyer-board cases, the post-your-case box and the source panel.
- **Confirm strip:** the same container with a 1.5px graphite-ink border, because it asks the person to check what the AI inferred.

### Inputs / Fields
Native Streamlit selects, text inputs, text areas, file uploader and toggle, themed: paper-grey fill, 6px corners, pen-blue focus and toggle-on. Labels above, in sentence case.

### Navigation
- **Rail:** pen-blue ground, no border. Radio dots hidden; each option is a full-width row (0.5rem by 0.55rem padding, 4px corners) with a 1.5rem step circle before the label.
- **Default:** rail-text label, rail-ring outlined circle with the step number.
- **Hover:** pen-blue-deep row.
- **Done:** paper-filled circle with a pen-blue tick.
- **Current:** graphite-ink circle with a highlighter-yellow number, and the label set bold in ink over a yellow highlighter swipe.
- **Lawyer portal:** separated by 1rem space and a rail-rule hairline, with a briefcase mark instead of a number.

### Notices
A square band: 0.75rem by 1rem padding, body type, 2px top rule over a wash, bold title on its own line.
- **State** (pen-blue rule, blue-wash): ready, empty and connected states; the title runs inline.
- **Time-sensitive finding** (deadline-red rule, red-wash): "Found in your evidence", with the response date in red.
- **Safety check** (graphite-ink rule, paper-grey): statements removed or blocked by the guardrails.
- **Engine note** (pencil-grey rule, paper-grey): the model was unavailable.

### Check report and review marks
How the brief was checked, shown on the brief page between the notices and the facts. This is where the hallucination defenses become visible.
- **Check report:** a bordered container titled "How this brief was checked". One ruled row per check (Sources, Numbers, Granite Guardian, Legal advice) in a three-column grid: a 1.1rem status mark, the check name in label weight, and the result in meta. Status marks: a pen-blue tick (passed), a graphite-ink square with a paper "!" (flagged), a pencil-grey dash (did not run). A foot line under a row rule names who wrote the brief and who checked it.
- **Try to fool it:** a secondary button inside the report runs three made-up statements through the same checks and lists them beneath, each with a meta line saying which check caught it. Nothing is added to the brief.
- **Review marks (the reviewer's pen):** a flagged statement gets a 1px graphite-ink wavy underline, and an ink-outlined note after its evidence tags ("45 not in E1", "Not supported by E1"): paper fill, 1.5px graphite-ink border, 2px corners, tag type. A removed or blocked statement is struck through in graphite-muted. "Not checked" is a dashed pencil-grey outline in graphite-muted.

**The Reviewer's Pen Rule.** Fact-check results are drawn in ink, like a careful reader's margin notes: never in a highlighter colour (those mean "this came from that source") and never in deadline red (that means "due soon"). A flagged statement stays visible and marked; only uncited or advice statements are removed.

### Source panel (signature)
The brief's right column: pick an evidence item, see its tag and "Cited sentences are highlighted", then the original text in source type with each cited sentence marked in that item's highlighter colour (`mark`, 2px corners, ink text). It is the payoff of the Source-Colour Rule.

### Ruled lists
Timeline and fact lists (ruled rows, optional date column), deadlines (date in muted or red, legal basis in meta beneath), the "likely ask for" checklist (an empty 1rem square box, 1.5px graphite-muted outline, 2px corners), and "Why this match" (pen-blue tick before each reason).

## Do's and Don'ts

### Do:
- **Do** give every brief statement its evidence tags, coloured by `HIGHLIGHTERS` in E1 to E6 order.
- **Do** mark a cited sentence in its source with the same highlighter as its tag.
- **Do** use the graphite-ink marker chip for anything hidden until the client accepts a lawyer.
- **Do** keep deadline red to dates within 30 days and findings that carry a response date.
- **Do** put dated facts in a fixed 7.25rem date column in tabular figures.
- **Do** set secondary text as meta (graphite-muted, 0.9rem), readable rather than faint.
- **Do** use one primary button per view, for the step's next action.
- **Do** draw fact-check results as ink review marks (wavy underline, outlined note, strike-through), per the Reviewer's Pen Rule.
- **Do** change theme tokens in `.streamlit/config.toml` and world marks in the `CSS` string in `app.py`, updating both when a value lives in both.

### Don't:
- **Don't** use a highlighter colour for status, category, emphasis, charts or decoration.
- **Don't** add a new non-evidence use of highlighter yellow beyond the rail's current step and text selection.
- **Don't** use deadline red for errors, safety checks or engine notes.
- **Don't** draw any score, meter, rank or badge that suggests a case's value or likely outcome; the lawyer board is ordered by date.
- **Don't** add shadows, lifts or a second typeface.
- **Don't** use grey cards with blue pills or emoji headings.
- **Don't** load fonts or assets from the network; offline mode must look the same.
