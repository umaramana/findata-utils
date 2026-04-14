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

## What Works Well (keep doing)
- Pointing to actual data/files instead of describing them
- Quick decisions on presented options — keeps momentum
- Catching real issues during verification (not just accepting output)
- Scoping sessions with time/effort limits

---

---

## Token Efficiency Log
Target: 75% per session. Measured as useful turns / total turns.
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

## Session Startup Checklist
For debugging sessions, lead with:
1. Which file/page has the issue
2. What you expected vs what you got (exact values)
3. The exact text from the problematic row

For build sessions, lead with:
1. What you want built (one sentence)
2. Any constraints (time, complexity, dependencies)
3. Where the input data lives
