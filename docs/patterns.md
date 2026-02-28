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

**Metric**: Efficiency % = useful tokens / total tokens × 100
(Useful = tokens that produced kept code, decisions, or valid analysis. Wasted = corrections, thrown-away iterations, wrong assumptions.)

**Previous session**: 50% efficiency — considered LOW
**Target**: 70–75% efficiency
**Morgan Stanley**: Estimated high efficiency (session described as smooth, few corrections) — likely at or above target

**How to run**: At end of a session, scan the conversation for correction turns, thrown-away code, and wrong-assumption rounds. Estimate token weight of each wasted block vs. total.

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
