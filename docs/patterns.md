# Patterns & Lessons

## Evaluate Before Planning
**Context**: PDF QC feature went through ~10 iterations (pdfplumber, OCR, layout parsing, math formulas) before landing on a simple Excel-only solution (~200 lines).

**Checklist before diving in**:
1. What's the simplest version that solves the actual problem?
2. What assumptions am I making? (e.g., "we need the PDF" was wrong)
3. What are the data/environment constraints? (e.g., redacted PDFs = images, no text)
4. Can the problem be solved with data we already have? (Excel alone had enough signal)
5. Is the user's framing of the solution the only option, or is there a simpler path?

**Apply this**: Spend 5-10 minutes evaluating the approach *before* writing a detailed implementation plan.

## Explain Before Executing
**Context**: During Merrill broker implementation, repeatedly coded solutions before explaining the logic. User had to correct wrong assumptions multiple times after code was already written.

**Rule**: Always explain the approach and reasoning BEFORE writing code. Present options for non-trivial decisions. Once an option is approved, don't silently deviate from it during implementation.

## Session Efficiency Analysis
**What it measures**: % of tokens spent on wasted cycles vs. total tokens in a build session.

**Wasted cycles include**:
- Iterations on wrong assumptions that got thrown away
- Code written before logic was explained → required correction
- Clarification rounds that should have been resolved upfront
- Approaches abandoned mid-build (e.g., PDF QC: pdfplumber → OCR → Excel)

**Session cost (required input, from the user)**: Claude cannot see its own spend, so never estimate tokens or dollars. At the start of the closing analysis, ask the user for the session cost (they read it from `/cost` in Claude Code: the total, plus token counts if shown). Record it as the first line of the log entry: `**Cost: $X.XX**`. If the user does not give one, write "cost not provided; turn-count estimate only" in the entry and do not invent a figure.

**Metric**: Efficiency % = (total cost − wasted cost) / total cost × 100, where total cost is the figure the user supplied.
(Useful = work that produced kept code, decisions, or valid analysis. Wasted = corrections, thrown-away iterations, wrong assumptions. Wasted cost = the user's total × the share of the session judged wasted; state that share and the resulting dollar figure in the entry.)

**Previous session**: 50% efficiency — considered LOW
**Target**: 70–75% efficiency
**Morgan Stanley**: Estimated high efficiency (session described as smooth, few corrections) — likely at or above target

**How to run**: At end of a session, (1) ask the user for the session cost, (2) scan the conversation for correction turns, thrown-away code, and wrong-assumption rounds, (3) weight each wasted block by its share of the session (long tool output and rewrites weigh more than a one-line reply), (4) apply that share to the user's cost figure and log the score in `prompting_guide.md`.

**Standing rule**: Run this analysis + update memory at the END of every significant build session.

## Use Existing Tools Before Writing Ad-Hoc Scripts
**Context**: During JP Morgan session, wrote ad-hoc shell scripts to analyze column shifts and optional zone behavior when `broker_profiler.py` already existed and could have been enhanced.

**Rule**: Before writing throwaway analysis code, check if an existing tool (broker_profiler, test_regression, etc.) can be extended. Reusable > disposable. User caught this: "why haven't you been using the broker profiler for all your data analysis?"

## Analyze Enough Sample Rows Before Coding Text Logic
**Context**: JP Morgan description concatenation required 3 fix rounds because initial logic was based on too few sample rows. Patterns: option TX + description-only row, company name TX row appending to previous option TX, multi-column company names.

**Rule**: For any text parsing/concatenation logic, analyze 20+ sample rows covering all detected patterns BEFORE writing the first line of code. Use broker_profiler's row classification to enumerate patterns.

## Verify Data Assumptions
**Context**: Assumed Sheet4 had 10 columns based on pandas output, but user confirmed it had 9. Built wrong solutions on wrong assumptions.

**Rule**: When debugging data issues, verify actual data structure (open the file, check with openpyxl, etc.) rather than trusting derived values. Ask the user to confirm when uncertain — they know their data better.

## Redaction Output Is Not Safe Until Checked
**Context**: On the first real client folder, a short form of a client name survived in 7 of 10 output filenames and reached Claude's context through the user's paste — after Claude had called the CLI status lines safe.

**Rule**: Never label redaction or CLI output "safe to paste" until it has been checked. Treat printed filenames as sensitive. Make tool output masked by default (no filenames, no amounts) so pasting it is safe by construction.

## Parsers: Probe the Real Layout Before Trusting a Synthetic One
**Context**: `drake.py` was built against a synthetic 1040. The first real return needed four fixes: a rotated "FORM" heading (page 1 skipped), TY2025 line renumbering, empty boxes with no dot leaders, and rows split by font differences. One of them was an unverified assumption that TY2024 line ids applied to 2025.

**Rule**: For a new document type, get a masked structural probe (row shapes, token classes, geometry offsets) from a real file before finalizing the parser. Verify line ids per tax year. Ship an arithmetic self-check with the parser so a misread is flagged rather than trusted.

## Quote Counts From Tool Output
**Context**: Wrote "47/47 lines (31 value)" into three places while the CLI had printed 32 value + 16 blank = 48.

**Rule**: Copy figures from the tool output. Never recall them.

## Read the User's Docs at Session Start
**Context**: The user's session rules live in `docs/MEMORY.md`, `patterns.md` and `prompting_guide.md`. At session close Claude invented a generic checklist instead of reading them.

**Rule**: At session start read `docs/MEMORY.md`. At session end follow its end-of-session rule: efficiency analysis, memory update, sync `docs/`, commit and push.

## Scope: Ask Before Building
**Context**: Built `checks.py` (plausibility checks on the return alone) unasked; the user objected and it was removed.

**Rule**: On a spec [FILL] gap, ask. Don't add checks the user didn't request, and reuse the existing redactor rather than reworking it.

## Verify Independently of the Tool's Own Status
**Context**: The redactor reported 11/11 OK, but `verify()` re-checks with the same patterns, so it cannot see what the patterns miss. A looser independent scan of the output found employer EINs printed without dashes on two W-2s.

**Rule**: Before trusting an OK, run one check that does not share the tool's assumptions (a looser shape scan, a different reader). Report what each check can and cannot see. Don't tell the user a category is covered until the exact forms are (dashed vs undashed).

## OCR Is Not Repeatable
**Context**: A phone-photo W-2 passed detection, then failed verify: a second OCR read found EIN/9-digit strings the first read missed.

**Rule**: Never assume detection and verification see the same text. Re-pass from the output's own OCR a bounded number of times, and stay FAIL when it does not converge. Keep FAIL/REVIEW outputs out of any folder a later tool reads.

**Update (2026-09-22)**: built the re-pass rule above (`confirm_passes`: after verify() first comes back clean, one more independent OCR re-read must also come back clean). Confirmed it fixes the exact scenario it targets (a same-run double-miss). It did **not** fix a second, real occurrence on the same document: OCR consistently failed to read one specific spot on *every* pass, including both confirmation reads — not intermittent variance, a deterministic miss. More re-reads do not help a deterministic failure; that needs either better input to OCR (preprocess the photo — contrast/deskew) or a heuristic that forces manual review instead of trusting any read (e.g. very low per-word confidence near a "SSN"/"social security" label). Neither built. **Conclusion: an OCR'd page's `OK` cannot be trusted by itself, full stop — always requires a human visual check**, no matter how many automated re-reads back it up.

## Scan Staged Changes for PII Before Committing
**Context**: Real client names had been written into the spec and a `--help` example by earlier sessions; nothing flagged them until a grep just before the first commit of `review/`.

**Rule**: Before every commit in `review/`, `git add` explicit filenames (never the directory: it holds client folders) and grep the staged diff for known client names, emails, SSN-shaped strings and key-shaped strings. Replace names with placeholders before committing.

**Update (2026-09-22) — same mistake, different surface**: gave the user a `diag_redact.py --file ... --names "..."` command as a usage example. The user copy-pasted the whole line back into chat, including a real name, when something went wrong with it — the tool's own output was masked and safe, but the *invocation* the user was told to run was not. **Rule, generalized**: any CLI usage example that shows a name/SSN/PII value as a flag will eventually get pasted back verbatim when the user hits trouble running it. Lead every such example with an interactive/`--prompt` form instead (built into both `redact.py` and `diag_redact.py`) — never show `--names "..."` as the example, even for a tool whose *output* is provably safe.

## Build a Synthetic Repro Before Presenting a Root Cause
**Context**: Fidelity "Principal" rows bug (2026-09-23). Given only a terse bug report ("Action=Principal rows get skipped, description goes wrong"), Claude read the code and presented a confident root-cause theory (`_is_description_row` misfiring on blank cells) without running anything. The user pushed back twice — once to make Claude fully read the codebase and test data first, once to explicitly say "you can very well create synthetic data and test it." Only after building a synthetic fixture and tracing the actual pipeline did the real bug surface (`_handle_merged_cells`'s substring match on "INC", false-matching "Principal" and "income") — a completely different mechanism than the first theory.

**Rule**: When diagnosing a parsing/classification bug from a terse report and no sample data is available, build a synthetic fixture reproducing the reported shape and run the actual code against it BEFORE presenting a root-cause theory — don't reason from reading the code alone, even when the logic looks clear. A theory built by reading code is a hypothesis, not a diagnosis; only a reproduction confirms it. This project's WSL environment has no pandas/openpyxl by default — `python3 -m venv` + pip install a throwaway env, it's cheap and network access works.

**Also**: after implementing a fix, run the FULL regression suite (not just the directly-relevant broker) before declaring done — this session's fix, checked only against Fidelity at first, would have shipped a second bug (a footnote paragraph misread as a transaction row) that only the full 12-test suite caught, because two independent false positives in the old code had been silently canceling each other out.

## Act on /cost's Own Efficiency Signals
**Context**: The 2026-09-23 Fidelity session's `/cost` output (pasted by the user) explicitly said "56% of your usage was at >150k context... `/compact` mid-task, `/clear` when switching to new tasks." Claude read it, used the dollar figure for the efficiency score, and said nothing about the context-size warning at all — not when it first appeared, and not at any of the session's own later task-boundary points (bug fixed -> unrelated question -> session wrap -> this meta-discussion), any one of which was a natural moment to suggest it.

**Rule**: `/cost` output can carry more than the dollar total — read the whole thing, including any usage/context warnings, not just the number needed for the efficiency score. Claude cannot run `/compact` or `/clear` itself (they're user-run slash commands), but should proactively suggest them: (1) immediately when `/cost` output flags high-context usage, and (2) at any clean task-boundary within a session (a distinct sub-task finishing, a topic switch) even before the user asks for `/cost`.

## Long-Running Tools Need Progress Output
**Context**: `review/redact.py --ocr` printed nothing for ~14 minutes because it reports after the last file; the user could not tell working from stuck.

**Rule**: A tool that runs for minutes prints one line per file as it finishes (masked). Say the expected duration when handing over the command.
