# Prompting Guide — Personal Best Practices

## Bug Reporting Template
When reporting a parsing/classification/OCR issue, use this format:

> "Page X (filename), row Y — expected [subtracted: 1000], got [balance: 1000]. Description reads: [exact text from CSV or image]"

This single line enables one-shot diagnosis. Without it, expect 2-3 extra back-and-forth turns.

---

## General Principles

### 1. Share exact text, not recollections
When debugging keyword or text matching issues, copy-paste the exact string from the file/image/CSV.
Recalling it from memory ("I think it says all caps") leads to wrong assumptions and wasted turns.

### 2. Filename > description
When referencing a specific page or file with an issue, always give the filename.
"Another file" or "one page" forces Claude to ask or guess.

### 3. Trust the "works on A, not B" instinct early
If something works on one page but not another, it's almost never the keyword or logic — it's the data or OCR quality on that specific page. Say so upfront: "works on page 3, fails on page 7."

### 4. Set constraints upfront
You did this well: "must be < an hour, drop it if too complex." Do this for every session.
Constraints shape the entire approach and prevent over-engineering.

### 5. Self-corrections are good — make them early
If you catch yourself correcting a prior statement ("actually wait, if that were true..."),
that instinct is usually right. Voice it immediately rather than waiting.

---

## Working Toward Autonomous Development (2026-07-14)
Five habits that most reduce back-and-forth when the goal is Claude executing longer stretches with less supervision:

### 1. Front-load a concrete example instead of iterating on abstract explanations
A real (synthetic) example — "here's a transaction, here's what field X should be, here's why" — builds
the correct mental model in one pass. Abstract explanations invite rounds of "explain again," "show that
table again" because there's no ground truth to check against.

### 2. Batch related questions into one message
The single most efficient exchange in the 2026-07-14 Tagger session was one message with four related
questions (matching logic, flow order, field semantics, AI usage) answered together in one turn. One
question per message costs a full context re-load each round even when the questions are related.

### 3. Give explicit "stop analyzing, implement" signals
Claude defaults to presenting options when a request is ambiguous — that's deliberate, not a bug, but it
costs turns you don't need spent once you already know what you want. A direct "go ahead and implement
this" unlocks the longest uninterrupted, highest-output stretches.

### 4. Paste sample data instead of asking Claude to infer it
Claude cannot read client data files directly (data-safety boundary — see MEMORY.md). Anywhere behavior
depends on real file shape (a Lookup tab's actual columns, a sample vendor string), Claude is reasoning
from code alone until you paste 2-3 representative (anonymized if needed) rows. This is the single
biggest structural bottleneck to autonomous work in this project — proactively pasting samples upfront
saves a full round-trip every time.

### 5. Keep decisions in written specs, not just conversation history
`REQUIREMENTS.md` files and `PARKING_LOT.md` are durable contracts. Once a design is agreed and written
there, a future session (autonomous or not) can be pointed at "implement per the X section of
REQUIREMENTS.md" instead of re-deriving the design from scratch in conversation.

---

## What Works Well (keep doing)
- Pointing to actual data/files instead of describing them
- Quick decisions on presented options — keeps momentum
- Catching real issues during verification (not just accepting output)
- Scoping sessions with time/effort limits

---

---

## Token Efficiency Log
Target: 90% per session (raised from 75% on 2026-10-08). Measured as (total cost − wasted cost) / total cost, using the session cost the user gives at close (`/cost`); every new entry starts with a `**Cost: $X.XX**` line. Entries before 2026-09-21 (second session) are turn-count estimates with no cost. Weight wasted turns by when they happened: late turns cost more than early ones.
Collaboration is also measured — Claude should narrate approach before coding, not after.
Red flag: "I built X, here's the output" without prior alignment = low collaboration score.

### Bank Transaction Processor — Phase 1 (2026-02-21)
**Score: ~65%** — below target

**Waste on Claude's side (~7 turns):**
- Coded debit/credit classification using position heuristics instead of keywords — required rewrite
- Committed to PSM 6 without testing on both files first — broke 2022 file, required dual-PSM rework
- Built parser before testing raw OCR output — description bleed issue caught late
- Syntax error in inline python `-c` command

**Waste on user's side (~5 turns):**
- "Service fee is all caps" — incorrect recollection caused keyword chase; copy-paste would have resolved in 0 turns
- "Another file / another page" without filename — forced ask or guess
- CSV vs Excel not specified upfront — one wasted exchange

**Root causes:**
- Claude: coding before validating approach on multiple samples; low collaboration — built and presented rather than discussed before building
- User: recollection instead of copy-paste; missing filenames

**Fix for next session:**
- Claude: test on 2+ inputs before committing; narrate approach before coding ("I'm choosing X over Y because Z — agree?")
- User: use bug report template; always include filename

---

### JP Morgan Broker Implementation (2026-02-25)
**Score: ~65%** — at previous level, below 75% target

**Waste on Claude's side (~14 turns):**
- Excel auto-header rows ("Column1") leaking into descriptions — should have profiled row types before coding (~2 turns)
- Description logic required 3 fix rounds: (a) set-future vs append-previous, (b) company name TX rows, (c) multi-col company names (~6 turns)
- Ad-hoc shell scripts for data analysis instead of using broker_profiler.py (~3 turns)
- Stale Streamlit cache debugging — should have suggested new port sooner (~3 turns)

**Waste on user's side (~1 turn):**
- Description bug report was directional ("half the transactions are just going with col 0") rather than citing a specific row with expected vs actual text

**Root causes:**
- Claude: didn't analyze enough sample rows before coding description logic; didn't use existing broker_profiler tool; assumed Streamlit cache was code issue
- User: minor — almost all feedback was data-driven with exact numbers

**Fixes for next session:**
- Run broker_profiler.py FIRST on any new file before writing broker code
- For text concatenation logic: analyze 20+ sample rows across all patterns before coding
- When Streamlit shows stale results: immediately suggest new port
- User prompting was strong (4/5) — exact totals, architectural pushback, tool reuse suggestion

---

---

### GVK Formatting Session (2026-03-27)
**Score: ~80%** — above target

**Waste on Claude's side (~2 turns):**
- Asked "blank between verse block and padachedam?" after presenting the plan — should have been in the initial clarifying questions upfront
- bash `cd` path confusion on health check commands — used wrong working directory, required retries

**Waste on user's side (~0 turns):**
- Requirements were clear, screenshot was precise, decisions were quick
- One minor: "each section" without naming which sections caused one clarification round (recovered fast)

**What worked well:**
- Screenshot reference was exactly the right artifact — zero ambiguity on formatting intent
- User confirmed/rejected options quickly, no extended back-and-forth
- Small, well-scoped session — 2 changes, clean in and out

**Fixes for next session:**
- Gather ALL clarifying questions in one pass before presenting the plan
- Use absolute paths in bash commands from the start (working directory is not always predictable)

---

### Interest & TDS Finder + First Skill (2026-04-01)
**Efficiency: ~72%** — below target
**User prompting score: 4/5**

**Waste on Claude's side (~3 turns):**
- Proposed count-based reconciliation — user correctly called it out as unvalidatable. Should have stress-tested the idea before surfacing it
- `Int.Pd` keyword miss — the limitation of cosine on abbreviated codes was knowable upfront but only surfaced after a real miss. Cost 1 fix turn

**Waste on user's side (~1 turn):**
- "Int.Pd in 1 statement" — good instinct but would have been faster with the exact description string from the file (bug report template)

**What worked well:**
- User drove the design well: YAML configs, skill wrapper, flexible input — all came from user, all good calls
- Quick decisions on options — cosine explanation → hybrid approved in one turn
- "Moving towards skills. So.." — clear enough directional signal, Claude discerned the intent correctly
- Near-miss band: user pushed back on count-based reconciliation and steered toward the right solution

**Key learnings:**
- Cosine is blind to bank abbreviation codes (Int.Pd, TDS, INT CR) — opaque tokens, not natural language. This split (abbreviations → keywords, natural language → anchors) should be stated upfront in every semantic search design
- Don't surface reconciliation ideas without first asking "what would this be validated against?"
- First Claude Code skill session — two-layer pattern (importable module + skill wrapper) is now established for future tools

---

### Tax Return Review — Drake Parser + Redactor Fixes (2026-09-21)
**Score: ~70%** (estimate, ~8 wasted turns of ~30) — below target
**User prompting score: 4/5**

**Waste on Claude's side (~8 turns):**
- Built `checks.py` unasked — user objected, removed (out of scope)
- Tried an ad-hoc dump of client page text — blocked; against the data-safety boundary
- Called printed CLI lines "safe" while a name short-form survived in filenames and reached context
- Parser built on a synthetic layout only — four fix rounds on the first real return, one from an unverified TY2024-for-TY2025 line-id assumption
- Wrote wrong counts (47/31 instead of 48/32) into three places
- At close, invented a generic checklist instead of reading `docs/MEMORY.md`; nearly committed under a guessed author identity

**Waste on user's side (~0 turns):**
- Feedback was specific and decisive: "FORM text is vertical aligned", the names-via-prompt design, and the scope pushback

**What worked well:**
- User-driven design: names typed only in the user's terminal, never stored as data
- Real data exposed real bugs (`.PDF` discovery, FOSINDEX annotations, filename leaks) that synthetic tests missed
- Masked probes (booleans, geometry, token shapes) let Claude debug a real return without seeing it
- Arithmetic self-check made a wrong parse visible (found the line 37 / line 38 penalty relationship)

**Fixes for next session:**
- Read `docs/MEMORY.md` and `patterns.md` at session start
- Ask for a masked structural probe before finalizing a parser for a new document type
- Never call redaction output safe before it is checked; copy counts from tool output

---

### Tax Return Review — OCR Redaction, 9-digit Rule, Path A Driver (2026-09-21, second session)
**Cost: $7.13** (user-supplied from `/cost`, provided after the fact; API time 28m 40s, wall 3h 55m; claude-sonnet-5 150.4k output, 23.0M cache read, 250.1k cache write; $0.0017 haiku)
**Score: ~76%** — wasted ≈ 24% of cost (≈ $1.71 of $7.13). By turn count the waste was ~22% (~11 of ~50 turns); rounded up because most wasted turns fell in the second half of the session, when each turn costs more (cache reads grow with context). Above target by a point
**User prompting score: 4/5**

**Waste on Claude's side (~11 turns):**
- Did not read `docs/MEMORY.md` at session start (the repeat of the first 09-21 session's note) and improvised at the first "close session"; the user had to ask for the checklist
- Told the user "EINs are still removed" - true only for dashed EINs. The undashed employer EIN on two W-2s surfaced only after an independent loose scan, and cost a full ~14-minute re-redaction
- OCR verify read a page in display rotation while detection read it unrotated: false leftover on `/Rotate` scans (2 turns)
- Own tests wrong four times: look-alike digits reused the known test SSN's digits; a portrait/landscape assertion backwards; a truth-JSON check that regex-matched key digits (2 rounds)
- Changed the dict `compare.extract_drake_lines` returns without grepping for tests that pin it: 2 failing tests (1-2 turns)
- Polled progress with a broad command the user rejected while the redactor ran (1 turn)
- Added the OCR re-pass after a FAIL without asking first (own feature, no objection, but the scope rule says ask)
- Real client names sat in the spec and a `--help` example (earlier sessions); found only by grep at commit time
- The redactor CLI prints nothing until every file is done: the user waited ~14 minutes and asked

**Waste on user's side (~1 turn):**
- "EXport" typo (bash is case-sensitive); pasted a FAIL line that carried a filename

**What worked well:**
- Six decisions answered in one line each: lift the rule for this client, Tesseract, 9-digit pattern, model, gate, line 25a
- Independent masked verification found the gap the tool's own OK missed; a synthetic end-to-end test of the driver with a stubbed extractor; the FAIL output moved out of the driver's folder before it could be picked up
- Names scrubbed and the staged diff scanned before committing; two separate commits (redactor, review)

**Fixes for next session:**
- Read `docs/MEMORY.md` and `patterns.md` first (a pointer now sits in auto-memory so it loads every session)
- `grep` the tests for pinned return shapes before changing a shared function
- Never reuse a fixture's identifiers (test SSN digits) as look-alikes
- Ask before adding behaviour, including a fix inside the feature just built
- Add per-file progress output to `review/redact.py` (offered, not built)

---

### Tax Return Review — Eligibility Gate, Copy-Page Dedup, OCR False-OK (2026-09-22)
**Cost: $11.48** (user-supplied from `/cost`: API 41m41s, wall 3h30m27s, 848 lines added/94 removed; claude-sonnet-5 17.0k input, 231.7k output, 37.0m cache read, 431.0k cache write; $0.0010 haiku; cache 99% hit rate)
**Score: ~82%** — wasted ≈ 18% of cost (≈ $2.07 of $11.48). By turn count the waste was closer to ~22% (~7 of ~32 turns), weighted down because the wasted turns fell early-to-mid session, before cache growth made later turns more expensive. Above target
**User prompting score: 4/5**

**Waste on Claude's side (~7 turns):**
- Gave `diag_redact.py` usage as a `--file`/`--names "..."` flag example instead of building `--prompt` mode first — the codebase already had this exact precedent in `redact.py --prompt`, and the risk (a name pasted back into chat when something goes wrong) was foreseeable, not novel
- That example directly caused: the user pasting a real name into chat when the command needed debugging (client-names-never-in-context violation), a multi-line-paste unterminated-quote hang, a literal `<page#>` placeholder copy-paste, `python: not found` (wrong interpreter), and a `getpass` hidden-input loop in their WSL terminal — roughly 6 back-and-forth turns before `--prompt` mode was finally built and the friction stopped
- Once `--prompt` existed, the actual investigation (root cause, fix, tests) went cleanly with no rework

**Waste on user's side (~0 turns):**
- Every report was specific and immediately actionable ("but this is again a false positive. ssn is open."); both structural decisions (immediate action, structural fix) were answered in one AskUserQuestion round each

**What worked well:**
- Correctly distinguished two different failure classes on the same real file instead of forcing one explanation: an intermittent double-miss (fixed, `confirm_passes`, tested two ways) vs. a deterministic per-spot OCR failure (recognized as unfixable by more re-reads, logged as genuinely open rather than chased further)
- Root-caused via purpose-built, masked diagnostic tooling (`diag_redact.py` extended for the OCR path) rather than guessing from the code alone
- `.gitignore` gap caught and fixed (`review_runs_redacted/`, `review_runs_names.json` were untracked and unignored) before anything was staged, not after
- Every commit scoped to explicit filenames only, out of a repo with a large unrelated uncommitted diff sitting in other folders; staged diffs grepped for the client name before each commit
- Spec/architecture amendments were dated and additive (inline `[Amendment, ...]` notes), not silent rewrites of the user's own documents

**Fixes for next session:**
- When a script takes any PII-shaped value as a CLI flag, build the `--prompt` interactive form FIRST, before giving any flag-based usage example — don't wait for the user to hit trouble with quoting to discover the tool needed it
- Generalize: this is the second time this exact mistake happened (see patterns.md's "Scan Staged Changes for PII Before Committing" update) — needs to actually stick this time

---

---

### Stock Processor — Fidelity "Principal" Rows Bug (2026-09-23)
**Cost: $4.35** (user-supplied from `/cost`: API 15m48s, wall 1h17m26s, 289 lines added/6 removed; claude-sonnet-5 3.7k input, 78.6k output, 13.8m cache read, 198.4k cache write, 98% cache hit; $0.0010 haiku)
**Score: ~72%** — wasted ≈ 28% of cost (≈ $1.22 of $4.35), weighted toward the early-session theorizing since that content (a full written root-cause explanation) was later discarded wholesale. Below the 75% target
**User prompting score: 5/5**

**Waste on Claude's side (~4-5 turns):**
- Jumped to asking the user for raw row data before fully reading the existing codebase/test fixtures — user corrected: "do not jump to fixing it without fully reading the code base, checking test data. dont behave like a bad intern"
- Presented a confident, detailed root-cause theory (`_is_description_row` misfiring on blank cells) built entirely from reading the code, with no reproduction — it was wrong. The real bug (`_handle_merged_cells`'s substring match on "INC", false-matching "Principal"/"income") only surfaced once a synthetic fixture was built and actually run
- Took an explicit user instruction ("you can very well create synthetic data and test it") to reach for the one tool (a real repro) that should have been the first move, not the third

**Waste on user's side (ambiguous, ~1-2 turns, contested — see below):**
- The opening bug report had no filename and no exact row/column values, unlike the project's own template ("Page X, row Y, exact text"). Per this guide's own earlier lesson ("Paste sample data instead of asking Claude to infer it... the single biggest structural bottleneck to autonomous work in this project"), that gap is plausibly why 2-3 rounds were needed before a fix could start
- Counter-argument the user raised, and it holds: the actual redirect given ("create synthetic data yourself") wasn't a missed opportunity to paste real data — it was a deliberate choice to keep real financial row values out of chat and point Claude at a tool it already had. That's defensible on data-sensitivity grounds, not a lapse, so this may not be "waste" at all
- Every correction was specific, correct, and immediately actionable regardless — "no other change to the rows except the Action column" pinpointed exactly what to hold constant in the synthetic fixture

**Self-check on this log's own bias**: the last several entries in this log all show ~0 turns of user-side waste. The user challenged that pattern directly this session, and it's a fair challenge — consistently crediting all friction to Claude's side is more likely a self-critique bias in how this log gets written than a real string of flawless sessions. Future entries should weigh user-side friction as seriously as Claude-side, including cases (like this one) where the honest answer is "shared cause, can't cleanly assign."

**What worked well:**
- Once a synthetic repro existed, diagnosis was exact and mechanical — traced the pipeline stage by stage to the precise line
- Ran the FULL regression suite (not just Fidelity) before declaring the fix done, and caught a second, independent bug that the narrower check would have shipped (a footnote paragraph misread as a transaction row, previously masked by the first bug's false positive canceling it out)
- Presented both real decisions (keep-vs-drop Principal rows; targeted-vs-broader footnote fix) via AskUserQuestion rather than picking unilaterally
- Isolated a pre-existing, unrelated repo-wide CRLF line-ending diff from the actual commit before committing, unprompted, so the commit stayed a clean 23-line diff

**Fixes for next session:**
- For any parsing/classification bug report, build a synthetic fixture reproducing the exact reported shape and run the real code against it BEFORE writing up a root-cause theory — treat a code-reading-only theory as a hypothesis to test, not a finding to report
- This environment has no pandas/openpyxl by default (WSL box) — `python3 -m venv` a throwaway env immediately when a repro is needed, don't let tooling setup delay reaching for it
- **Missed entirely until the user pointed it out**: the `/cost` output the user pasted mid-session explicitly said "56% of your usage was at >150k context... `/compact` mid-task, `/clear` when switching to new tasks" — a direct, machine-generated efficiency signal that was sitting right there and went unmentioned. Claude cannot invoke `/compact`/`/clear` itself (slash commands the user runs), but should have surfaced the recommendation the moment it appeared in `/cost` output, and flagged it again at each of this session's own clean task-boundary points (Fidelity fix done -> unrelated PowerShell question -> session wrap -> this meta-discussion). See [patterns.md](patterns.md) for the standing rule.

### Tax Return Review — Redactor: Phone/Email/DOB, IDs, Accounts, US+India Addresses, Paste Intake (2026-09-24)
**Cost: $7.93**
**Duration: 3h 5m (02:58 -> 06:03 EDT)** — API time 27m 50s; the rest was the user running real files and reviewing
**Score: ~82%** — above target

**Waste on Claude's side (~$1.2):**
- First cut of the address rules was fitted to the probe sample (15-word reach, a big-city list, a Form 8938-only next-line rule with a stop-list from its empty fields). The user had to point out that real files are samples for learning; a full generalisation round followed late in the session at high context (~$0.8). Now a thumb rule in patterns.md ("Real Samples Teach the Class, Not the Instance")
- A synthetic test page with lines 12pt apart produced false over-redaction failures, and three test expectations went stale when new always-on rules correctly fired ("Acct ...", "Folio No ...", "42 Maple Avenue") (~$0.2)
- The "Supporting changes" table in the first plan wasn't clear enough; the user had to ask what it meant (~$0.15)

**Waste on user's side (~0-1 turn):**
- Ran the probe from `review/` with the `redactor/` path, one turn. Shared cause: the command given started with `cd redactor`, but the user's venv and data live under `review/`, so the example should have been written from `review/`

**What worked well:**
- Masked layout probe (`probe_labels.py`): the user ran it on real returns and pasted `*`/`#` shapes; that located every address layout without any client text reaching Claude
- The user's side-by-side check (a separate Claude chat reviewing the redacted output) found 6 remaining leak classes that no synthetic test would have shown; they're logged with proposed general fixes
- Plans and questions came before each coding round, in the short tables the user asked for; scope decisions (last-4 truncation, auto US addresses, the two flows) went to the user
- Found and fixed a core bug along the way: the pdfplumber text stream dropped line breaks, which let one-line rules cross lines

**Fixes for next session:**
- When a real sample drives a rule, write the general class and the variation tests in the same round, not after the user asks
- Write CLI examples from the folder the user actually works in (`review/`)
- /cost again flagged 41% of usage at >150k context: suggest `/compact` at natural task boundaries (e.g. after each probe -> fix round), and don't advise "run first, compact later" when the spec already records everything

### Tax Return Review — Redactor: Address False-Positive FAIL + diag_redact verify view (2026-09-24, later)
**Cost: $2.80** (user-supplied from `/cost`: API 7m54s, wall 1h6m21s, 54 lines added/7 removed; claude-opus-5-5 3.0k input, 36.6k output, 5.0m cache read, 131.8k cache write, 97% cache hit; $0.0015 haiku)
**Duration: 1h 5m (09:53 -> 10:58 EDT)** - API time under 8 min; the rest was the user running the full-document diagnostic twice
**Score: ~89%** - above target

**Waste on Claude's side (~$0.3):**
- First edit of the new diag section left a dead loop and a wrong context-slice; needed a clean-up refactor (~$0.1)
- The diag `--prompt` took a folder path (Windows form) without checking it, so the user's first run crashed after they had typed every entry; fixed after the fact (~$0.1 plus a full user re-run)
- First synthetic repro drew the checkbox in the wrong stream order and did not reproduce case 2 (~$0.05)
- Tried to list the redacted-output folders; blocked by the classifier (PII rule) (~$0.03)

**Waste on user's side (~1 run):**
- One diagnostic run lost to the folder path above (shared cause: the tool should have validated it)

**What worked well:**
- Added the view `verify()` actually uses to the diagnostic; one real run pinpointed both causes (rule name + masked context), then a synthetic repro confirmed them, and the old rules were shown to fail the new test before the fix was trusted
- Outside Claude review kept acting as the independent check; its 9 findings are logged as shapes with the user's decisions

**Fixes for next session:**
- Diagnostic tools: validate inputs before asking for secrets, write to a file (done), and process only the pages asked for - the biggest time sink here was two whole-document runs to look at 3 pages
- Give the user a masked-reporting prompt for the outside review so real values don't come back into the chat
- Start at PARKING_LOT "OPEN (24 Sep, later session)" in the listed order

### Tax Return Review — Redactor: 8 Label Rules + HARVEST Reader (2026-09-25)
**Cost: $7.77** (user-supplied from `/cost`: API 23m50s, wall 2h54m32s, 543 lines added/4 removed; claude-opus-5-5 13.5k input, 124.9k output, 15.1m cache read, 275.8k cache write, 98% cache hit, 1 compaction; $0.001 haiku; 26% of 24h usage at >150k context)
**Duration: 2h 52m (05:15 -> 08:07 EDT)** - API time under 24 min; the rest was the user running probes/harvest reports and deciding the harvest design
**Score: ~85%** - above target on cost (waste ~$1.2 of $7.77); **slow on time** (first close mislabelled this "~80%, below target" and gave no tips - corrected at the user's prompt)

**Biggest time sinks (wall 2h52m vs 24 min API):**
- ~40 min: 5 real harvest/probe runs to settle the layout; the NEAR geometry view only came after run 1, then one fix per run
- ~1 h: per-rule fixes (items 1-8) before the harvest reframe, which now covers part of that ground
- ~15 min: long explanations before the user's "short, tables" feedback

**Waste on Claude's side (~$1.2):**
- Long, dense explanations of the options until the user said "going above my head... short and in tables" (~$0.3 plus user time)
- Probe instructions did not say whether to redact first, and one command was given without a quoted Windows path (~1 user run)
- Harvest: the synthetic layout first placed the Presidential Election Campaign label one row off from the real print, and one tightening fix (value must start under its label) broke the State field; caught by the next real run, not before it (~2 extra user runs)
- Tried `python` (not on WSL) and a no-op scripted edit before using the venv / the right anchor (~$0.05)

**Waste on user's side (~4 runs):**
- 5 harvest/probe runs to settle the layout (1 was the older probe by mistake - the command names were too alike)

**What worked well:**
- Masked NEAR view (offsets, heights, known labels by name) let every layout fix be derived from the real return without seeing a value; each real quirk was then added to the synthetic return as a test
- User reframed from per-rule fixes to HARVEST (values from the one standard document); decisions saved to the spec and PARKING_LOT before compacting

**Speed tips (learning):**
- Ship every diagnostic view in the FIRST real-run tool (masked values + geometry); one real run, not five (~30 min)
- For leaks across untemplated documents, first ask "is there one standard document that holds the truth?" (harvest) before patching rules one by one (~1 h)
- Give user-run tools distinct names and output prefixes (probe_ vs harvest_ were confused once)
- One build step per session; compact/fresh at each step boundary (26% of 24h usage was at >150k context)
- At close, compute the score from the numbers before labelling it vs target, and always include the time sinks + tips (patterns.md "Track Session Duration and Give Proactive Speed Tips")

**Fixes for next session:**
- After tightening a heuristic, re-run the check against every field that already passed (synthetic tests for each real quirk) before asking the user for another real run
- Start at PARKING_LOT "DECIDED (25 Sep) for step 3": build the batch driver in a fresh session

---

### Bookkeeping — Check Image OCR Extractor, Phase 1 + Phase 2 spec (2026-10-06)
**Cost: $5.23** (user-supplied from `/cost`: API 18m6s, wall 3h26m8s, 795 lines added/2 removed; claude-opus-5-5 10.0k input, 92.0k output, 8.7m cache read, 200.3k cache write, 97% from cache, 2 rebuilds (compaction); $0.001 haiku; 19% of 24h usage at >150k context)
**Duration: ~3h 18m (06:18 -> 09:37 EDT)**. API time was only 18 min; the rest was installs, real sample runs and design calls.
**Score: ~80%**, above the 75% target on cost (waste ~$1.0 of $5.23). **Slow on time.**

**Biggest time sinks (wall 3h18m vs 18 min API):**
- ~45 min: environment setup. Python 3.14 couldn't install Pillow<11 (needed a 3.12 venv), Surya needed pins (transformers<5), and `/tmp` filled up during the model download
- ~40 min: real-page runs to tune the splitter (area threshold, aspect band) and the caption parsing (label regex, `$` left in the payee)
- ~10 min: `AttributeError` from a stale module. Streamlit doesn't reload `bookkeeping/` imports, and the user wasn't told to restart after the edits

**Waste on Claude's side (~$1.0):**
- First diagnostic mask let house numbers, ZIPs and ID fragments through. It was caught and fixed, but it was a privacy slip (~$0.2 plus a re-run)
- Didn't warn that `sys.path` modules need a Streamlit restart after edits (~1 user round trip)
- Splitter tuning took several passes; synthetic tests didn't mirror the real statement layout until after the first real run (~2 extra runs)
- The spec draft used real vendor names from the sample; the user asked for dummies (~$0.05)

**Waste on user's side (~3 runs):**
- 2-3 extra real-page runs while the splitter and caption parsing were tuned

**What worked well:**
- The masked layout diagnostic (`diag_checks.py`, written to a file) gave the real geometry without exposing values; each quirk then became a synthetic test
- Statement pages: one full-page OCR pass plus the printed caption for no./date/amount meant only the payee depends on handwriting
- The payee problem was quantified before any build (raw 4/17, fuzzy match 17/17), and the reuse question (tagger lookup) was settled as read-only plus a separate aliases file, then specced for a fresh session

**Speed tips (learning):**
- Check the Python version and pins against every heavy dependency (Surya, Pillow, transformers) BEFORE installing; pick the venv Python first (~30 min)
- Any page that imports from outside its folder: say "restart Streamlit" with every edit to that module
- Build the masking regex from a list of what must NOT survive (house no., ZIP, phone, IDs) and test it on synthetic PII first
- Spec examples use dummy names from the start

**Fixes for next session:**
- Fresh session: "build Phase 2 from check_ocr_spec.md". Confirm the Open table first and test only with synthetic lookup files


### Bookkeeping — Check Extractor Phase 2: Payee Matching (2026-10-06)
**Cost: $2.39** (user-supplied from `/cost`: API 7m0s, wall 25m25s, 399 lines added/0 removed; claude-opus-5-5 2.7k input, 43.3k output, 2.6m cache read, 125.4k cache write, 95% from cache, 1 rebuild (compaction); $0.001 haiku; 11% of 24h usage at >150k context)
**Duration: ~25m (09:44 -> 10:09 EDT)**. Fast. API time was 7 min; the rest was 2 rounds of user decisions (the Open table, then the threshold lock).
**Score: ~88%**, above the 75% target (waste ~$0.3 of $2.39).

**Biggest time sink:** the scoring detour (~5 min). OCR-side fragment windows broke "KAL MB" → KLMN (margin 0.095), and the test generator made misreads no matcher could recover ("RUCNE" from ACME). Both were fixed and re-run.

**Waste on Claude's side (~$0.3):**
- The first `score()` scored both sides' token runs; the fixed misread list caught it, but only after the threshold table had already been built once
- The generator had no cap on edits per name length, so false "wrong" counts had to be chased down

**Waste on user's side:** none. Both decisions were one click on the recommended option.

**What worked well:**
- The spec's Open table was confirmed in one AskUserQuestion round before building; thresholds came from a `--report` table, not from the one real sample
- Tests and the page smoke test used synthetic lookup files only; the tagger file's hash was checked as unchanged
- The suggested `/compact` mid-task kept the context small (11% at >150k)

**Speed tips (learning):**
- Margin-based matcher: split only the candidate side, never the query (now in patterns.md)
- Cap synthetic edits at about 1 per 3 letters before reading any failure counts

**Fixes for next session:**
- `/clear`, then "resume Check Extractor Phase 2 testing". Start from the spec's "PICK UP HERE" table; the user reports counts only

### Tagger — Status Review + Doc Cleanup (2026-10-07)
**Cost: $0.64** (user-supplied from `/cost`: API 1m44s, wall 53m46s, 0 lines added/removed in code; claude-sonnet-5-5 1.7k input, 9.4k output, 1.5m cache read, 60.4k cache write, 95% from cache; $0.001 haiku)
**Duration: ~54m (02:46 -> 03:40 EDT)**. API time was under 2 min; the rest was the user reading and deciding.
**Score: ~85%**, above the 75% target (waste ~$0.10 of $0.64).

**Biggest time sink:** none on Claude's side. The first summary used internal jargon ("Parked", "Open", "Stage 1 to 4 SOP"), which cost one clarification round.

**Waste on Claude's side (~$0.10):**
- The first summary used parking-lot labels the user did not recognise, so one reply went to re-explaining them
- One 42 KB dump of the tagger notes was read in full when only the tagger section was needed

**Waste on user's side:** none.

**What worked well:**
- Answered "AI or rules?" with a measurable test (persona-on vs persona-off eval) instead of an opinion
- Edited only the files asked about; ~100 line-ending-only "modified" files were identified and left out of the commit
- Client name removed from docs and replaced with generic wording, as asked

**Speed tips (learning):**
- In a status summary, say what each item means in one plain sentence; no internal labels
- Grep for the tagger section instead of reading whole parking-lot files

**Fixes for next session:**
- `/clear`, then run the new-format bookkeeping statements through OCR -> Collator -> Tagger. Report counts and vendor names only (no amounts, no client identifiers): near-duplicate count, "Review with Client" count, any error reasons
- Then decide Vendor Merge / migration script / regex tuning from what the run shows

### Bookkeeping — Check Extractor: Spec Sync, COGS-Only Matching, OCR Tuning Rollback (2026-10-07)
**Cost: $3.66** (user-supplied from `/cost`: API 10m36s, wall 1h56m58s, 56 lines added/0 removed; claude-opus-5-5 12.7k input, 55.1k output, 6.7m cache read, 145.5k cache write, 97% from cache, 1 rebuild (compaction); $0.001 haiku)
**Duration: ~1h57m (01:52 -> 03:49 EDT)**. API time was under 11 min; most of the rest was the user running the app (CPU OCR) and deciding.
**Score: ~77%**, just above the 75% target (waste ~$0.85 of $3.66).

**Waste:**
- Wrote a diagnostic script without asking, then deleted it (GR1 set as a result): ~$0.15
- Step 0 measurement debate: scoring script -> truth file -> in-app accuracy mode, 4 rounds before the user called it too big: ~$0.40
- Bundled 300 DPI + payee re-read in one test, so the rollback taught nothing about which hurt: ~$0.30
- Suggested /compact right at session start: small

**Biggest time sink:** the step 0 back-and-forth (user side) and the long CPU OCR runs.

**What worked well:**
- Spec drift found and fixed against the code before any change
- COGS-only matching + manual year-tab workbook built with synthetic tests only; real lookup files never opened
- Rolled back cleanly: confirmed the 3 code files differed from HEAD only by the step 1 edits before `git checkout`
- Counts only from the user's runs; no vendor names in the spec, tests or commit

**Speed tips (learning):**
- Offer the smallest test first (user eyeballs the same page); add tooling only if results are mixed
- One OCR change per run

**Fixes for next session:**
- `/clear`, then on the real page: edit one wrong payee, click Save payee corrections, re-run, and confirm it is an alias hit (counts only)

---

### Bookkeeping — Regions Bank Kickoff: Sample Intake, Redaction Check (2026-10-07)
**Cost: $0.58** (user-supplied from `/cost`: API 2m10s, wall 1h02m, 0 lines changed; claude-sonnet-5-5 3.8k input, 9.7k output, 1.5m cache read, 46.1k cache write, 96% from cache; $0.001 haiku)
**Duration: ~1h02m**. API time was ~2 min; nearly all the rest was the user redacting files and deciding.
**Score: ~86%**, above the 75% target (waste ~$0.08 of $0.58).

**Waste:**
- Read the "redacted" PDFs' text without a masked probe first: real values entered context (privacy cost, small $ cost)
- Read the two big memory files and ran a redactor `--help` to answer a yes/no question: ~$0.05

**Biggest time sink:** user side: producing redacted samples that turned out to still contain text.

**What worked well:**
- Asked before opening `data/`; listed filenames only
- Found the leak and the missing transaction text from per-page character counts, then reported shapes only

**Speed tips (learning):**
- Ask the user to run the redactor and paste only its status line; check per-page text counts before reading any content

**Fixes for next session:**
- `/clear`, then re-redact the originals with `review/redact.py --prompt`, probe the output (counts only), then write the Regions mini-spec

---

### Bookkeeping — Bank Statements Page: Redactor Reuse Question, Layout Intake, Mini-Spec (2026-10-08)
**Cost: $1.32** (user-supplied from `/cost`: API 4m45s, wall 1h16m, 77 lines added/0 removed; claude-sonnet-5-5 6.2k input, 22.0k output, 3.8m cache read, 82.4k cache write, 97% from cache; $0.001 haiku)
**Duration: 1h16m wall (~02:10 -> 03:27 EDT, start inferred; I did not run `date` at the first tool call)**. API time was under 5 min; the rest was the user checking formats and deciding.
**Score: ~85%**, above the 75% target (waste ~$0.20 of $1.32, ~15%).

**Waste:**
- Built `--lines` in `probe_labels.py`, ran it on both sample folders, then the classifier denied reading the output; the user then pointed to screenshots that made the probe unnecessary (~12%)
- Offered probe option A/B and asked what I knew before asking whether screenshots existed (~3%)

**Biggest time sink:** the probe detour (build, run, denied read, drop). Asking "is there a screenshot or a description of the format?" first would have skipped it.

**What worked well:**
- Read `probe_labels.py` before proposing to run it; tested `--lines` on a synthetic file only
- Said plainly "no, the Chase extractor can't be used directly" with a per-function reuse table
- Spec written with answers folded in, invented names only, gaps marked `[FILL]`; no code before go-ahead

**Speed tips (learning):**
- For a new bank format, ask for screenshots or a column description first; build a probe only if neither exists
- A masked output file is still blocked by the classifier: have the user paste it, or use screenshots

**Fixes for next session:**
- `/clear`, then use the resume prompt in the spec's status line; start with build step 1 (Regions checking parser, synthetic tests). Savings is an image PDF: OCR path

---

### Bookkeeping — Regions Bank Statements Fixes: 0-row Parsing, Filename Column, Fees (2026-10-09)
**Cost: $1.11** (user-supplied from `/cost`: API 4m17s; claude-sonnet-5-5 6.9k input, 22.3k output, 2.8m cache read, 80.6k cache write, 96% from cache)
**Duration: 1h30m wall (start not logged with `date`)**. API time was ~4 min; the rest was the user running dumps on the laptop and re-running Streamlit.
**Score: ~78%**, above the 70-75% target (waste ~$0.25 of $1.11, ~22%).

**Waste:**
- Built a "text layer flattened onto one line" fix from a pasted block, reverted after the user said the paste only rendered that way (~15%)
- First `_join_split_rows` draft was messy and could loop; rewritten; test failure on "Total X" lines took one more round (~7%)

**Biggest time sink:** the wrong-theory round before the first real dump; asking for the repr dump first would have found the one-field-per-line layout in one run.

**What worked well:**
- After the correction: wrote the diag script, read the real dump, fixed the general class (joined split rows) with a test
- The $5 gap: one dump, cause visible in 10 seconds (FEES box row before 'Total Withdrawals'), fix generalized with a reconcile guard

**Speed tips (learning):**
- A parser returning 0 rows: ask for the diag dump immediately; never reason from a pasted block
- Keep the diag script around (`diag_regions_dump.py`) and ask for it first for any new Regions-like bug

**Fixes for next session:**
- `/clear`; next = Regions credit card parser on real files, push from PowerShell

### Regions Credit Card Parser on Real Files (2026-10-08)
**Cost: $0.84** (user-supplied from `/cost`: API 2m59s, wall 34m57s; claude-sonnet-5-5 3.8k input, 15.8k output, 2.3m cache read, 53.9k cache write, 97% from cache)
**Duration: ~35m wall; Claude API 3m, the rest was the user running real files on the page between fixes**
**Score: ~88%** — just below the new 90% target (waste ~12% of cost)

**Waste:**
- Three turns on "which file is missing from the Summary" (added a 'not found' row, ran a repro) before the user's Master/Summary paste showed the real cause: the second PDF was the same card's account statement and its rows were duplicated (~10%)
- Assumed the card was Regions without asking; harmless this time (~2%)

**Biggest time sink:** the missing-Summary-row misunderstanding; asking "paste the Summary check block" in the first reply would have ended it.

**What worked well:**
- Synthetic repro of the split-line layout BEFORE fixing: 0 rows reproduced, fix verified by test
- Reading the user's PNG crops (Company Summary, CR column) gave the layout; the identity check (prev - pay - cred + purch + ... = new) makes the summary parse layout-proof

**Speed tips (learning):**
- Real-file bug on a page: ask for the Master + Summary paste first; duplicates and missing rows show there
- Screenshots of the statement table (not text) are enough to design a parser branch

**Fixes for next session:**
- `/clear`; next = the user's remaining real files (Interest/Checks rows on checking), push from PowerShell

### Tagger: Wave Category, Credits, Manual Lookup, Client Wave Categories (2026-10-09)
**Cost: $6.53** (user-supplied from `/cost`: API 16m29s, wall 1h10m47s; claude-opus-5-5 6.1k input, 106.0k output, 13.1m cache read, 221.9k cache write, 98% from cache; 41% of usage at >150k context)
**Duration: 1h11m wall; Claude API 16.5m, the rest was the user reading and answering**
**Score: ~75%**, below the 90% target (waste ~$1.60)

**Waste:**
- Whole session in one context: four build steps (Wave mapping + credits, manual lookup, A+B categories, close) ran on top of each other. I wrote `/compact` at the end of replies but kept building in the same context, so every turn re-sent 150k+ tokens (~12%)
- Manual lookup loaded as a client keyword-rules file, then reverted to contained-name lookup matching when the user objected (~8%)
- Assumed a separate "Wave run" had to come first; the user corrected the order (tagger first, then Wave) (~3%)
- Large dumps into context: full 1300-line tagger file in three reads, whole lookup workbook (~2%)

**Biggest time sink:** context size, not rework. Cost per turn climbed because nothing was compacted between steps.

**What worked well:**
- AskUserQuestion with a recommended option settled three design choices (Wave cat → tax auto, shared file, credits now) in one turn
- Checking the new matching against the first run's real vendor strings before handing over
- Headless Streamlit `AppTest` smoke of Steps 3–4 caught nothing, but proved the UI path without the user

**Speed tips (learning):**
- After each build step passes tests: stop, say `/compact` and wait. Don't start the next step in the same reply
- Design question about where logic belongs (lookup vs rules): state the options in one line before building

**Fixes for next session:**
- `/clear`; next = the user's test run with client 459990, then Wave names for COGS/Garbage/Officer Pay etc.

---

## Session Startup Checklist
For debugging sessions, lead with:
1. Which file/page has the issue
2. What you expected vs what you got (exact values)
3. The exact text from the problematic row

For build sessions, lead with:
1. What you want built (one sentence)
2. Any constraints (time, complexity, dependencies)
3. Where the input data lives
