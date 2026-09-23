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
Target: 75% per session. Measured as (total cost − wasted cost) / total cost, using the session cost the user gives at close (`/cost`); every new entry starts with a `**Cost: $X.XX**` line. Entries before 2026-09-21 (second session) are turn-count estimates with no cost. Weight wasted turns by when they happened: late turns cost more than early ones.
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
