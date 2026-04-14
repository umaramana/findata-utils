# Parking Lot - Future Features

---

## Interest & TDS Finder — Bank Account Tagging

**Tool**: `bankdetails_dataextraction/find_interest_tds.py`

### Feature: Tag transactions by bank account

When a client has multiple bank accounts, the output needs to show totals broken down per account — not just a combined total.

**Requirements:**
- Input file should carry a **Bank Account** identifier column (account number, bank name, or alias like "HDFC SB", "Kotak FD")
- Output sheets (Interest Income, Tax Deducted) should show totals **per bank account**
- Support mixed-currency files: INR accounts and USD accounts in the same input
- Summary section at the bottom of each sheet:

| Bank Account | Currency | Total |
|---|---|---|
| HDFC SB ××××1234 | INR | +12,500.00 |
| Kotak FD ××××5678 | INR | +8,200.00 |
| Chase ××××9012 | USD | +340.50 |

**Design notes:**
- Currency detection: from a `Currency` column if present, else infer from locale config default
- If no account column present → skip grouping, output as today (single total)
- YAML `column_hints` should add `account` hints for detection
- Locale YAML should carry `default_currency` (INR for india, USD for us)

**Priority**: Medium — needed when client has multiple accounts in a single merged file

---

## Merrill CD — Currency formatting
- Proceeds/Cost for whole-dollar CD transactions output as `50000.0` instead of `50000.00`
- Root cause: pandas reads integer Excel cells as `int`; drake_mapper outputs them as float without formatting
- Fix in next session: ensure Drake output formats numeric columns consistently

## Issue Log
- Start a persistent issue log for the tool (deferred 2026-03-22 session)
- Fields agreed: Issue #, Date, Component, Issue, Root Cause, Fix, Git Commit
- ID format: `ISS-001` style; commit messages to carry issue ID for cross-reference
- Location: repo-level markdown file, committed alongside code
- First entry to document: Schwab 1f/1g wash sale fix (commit `acf028e`)

## Collate Excel — Multi-file upload support
- Allow uploading multiple Excel files and collating them into one Master
- No column validation — add a UI note: "Ensure all files have the same column structure"
- Use case: combine bank transactions + CC transactions before tagging

## Chase CC — Add summary tab to Excel output
- Similar to Chase bank script's summary tab — one row per month, totals + net
- Chase CC equivalent: total purchases, total payments, net balance change

## Chase CC — Add reconciliation summary row to Excel output
- After all transactions, write a summary row showing "TRANSACTIONS THIS CYCLE: $X.XX"
- Green text if reconciled, red text if gap detected
- Makes it easy to visually confirm all is good without hunting through console output

## Tagger — Vendor Merge (Step 3 inline)

### Feature
Preparer can select multiple near-duplicate vendor rows in Step 3 and merge them into one canonical name before tagging. Reduces vendor count, improves lookup CSV consistency, and saves Claude API calls on subsequent runs.

### UI design (Option B — inline in Step 3)
- Add "Select" checkbox column to vendor table (st.data_editor)
- "Merge Selected" button above table → input pre-filled with highest-count vendor name → confirm → rows collapse, counts combine
- Table sorted alphabetically by default so similar names cluster
- **Fuzzy similarity hint**: highlight pairs above similarity threshold as "Did you mean to merge?" — without this, the feature requires too much manual scanning to be practical

### Alternatives considered
- **Option A (separate Step 2.5)**: Dedicated merge step before tagging. More control, more friction. Rejected as too many steps already.
- **Fuzzy auto-merge without preparer confirmation**: Risky — false merges corrupt lookup CSV. Always require preparer confirmation.

### Cost benefit
Genuine but modest in dollar terms ($0.00x per run). Data quality benefit is larger — eliminates orphaned near-duplicate keys in lookup CSV that accumulate over time.

### Implementation notes
- Merge history stored in lookup CSV as alias mapping (e.g. `APNA BAZAR CASH CARR` → canonical `APNA BAZAR CASH CARRY`)
- On subsequent runs, known aliases collapsed automatically before preparer sees table
- Fuzzy matching: `difflib.SequenceMatcher` or `rapidfuzz` — no new dependency if using difflib

---

## [Sprint 3] Tagger — Two-level taxonomy (generic tag + subcategory)
- Claude outputs two columns: generic tag (maps to tax form line) + subcategory (preparer working label)
- Subcategory vocabulary seeded from client's lookup CSV — grows organically from preparer tagging
- First run for new client: Claude freely synthesizes subcategories guided by client persona
- Subsequent runs: Claude sees prior subcategories from lookup and stays consistent
- Client persona (entity type, primary/secondary activity) shapes classification at both levels
- No manual example curation needed — lookup CSV is the growing knowledge base

## [TOP PRIORITY] OCR Extractor — Refactor + Streamlit Integration
- Extract shared logic (image loading, natural sort, Tesseract OCR, text cleaning, reconciliation, output) into `ocr_utils.py`
- Current scripts (`extract_bank_txns.py`, `extract_chase_txns.py`) are duplicated — refactor to use shared utils
- Build `extract_chase_cc_txns.py` using shared utils (Chase credit card: Date | Merchant | Amount format)
- Wrap all OCR extractors as a new page in the Streamlit app (upload images, pick bank/statement type, download CSV)
- Also investigate: direct PDF text extraction (pdfplumber) for digitally-generated PDFs — could eliminate PDF24 image conversion step for non-scanned statements

## Subtotal Aggregation per Stock
- Instead of processing all individual transactions for a stock, use the broker's subtotal row for that stock
- Could reduce processing errors and simplify output (e.g., 10 transactions → 1 subtotal row)
- Challenge: each broker has a different format for subtotal rows
- Needs broker-specific detection logic (Schwab, Fidelity, Robinhood)

## PDF vs Excel QC (Quality Check & Auto-Correct) — IMPLEMENTED (Step 2B)
Implemented in `pdf_qc.py` and `app.py`. PDF page 1 is a summary, page 2+ are data pages.
PDF page N maps to Excel sheet N-2 (page 2 → sheet 0).

## PDF Summary Page QC (Page 1)
- PDF page 1 contains a summary/totals page
- Future feature: compare summary totals against the sum of all processed transactions
- Could catch errors that per-page QC misses (e.g., missing pages, double-counted rows)

## Data File & Folder Cleanup (Security / Organisation)
- Audit all folders for orphaned client data files (xlsx, csv, images) outside proper data directories
- Establish a clear folder convention: code in `VibeCoding/ClaudeCode/`, data in `dataforrasrichtools/` — never mixed
- Review `.gitignore` to ensure all client data patterns are covered (especially any new file types added)
- Delete or archive any client data files sitting in the repo working directory
- Related: consider whether `bankdetails_dataextraction/` output files need a dedicated subfolder vs landing in root

## [HOT-FIX DONE / FOLLOW-UP NEEDED] QC Per-Sheet Anchor Detection

### What was fixed (hot-fix, March 2026)
Schwab file `Schwab 2025 EOY VER 2.xlsx` had 5 sheets with varying column counts:
Sheet1-3 = 9-col, Sheet4 = 8-col, Sheet5 = 7-col. The broker module (`schwab.py`)
hardcoded date at col 4 and proceeds at col 5, so Sheet4 and Sheet5 returned 0 rows.

**Hot-fix applied in `schwab.py`**: Added `_date_col_idx(num_cols)` which computes the
date column as `min(max(num_cols - 5, 2), 4)`. Financial block always occupies the last
5 columns — the only variation is how many description columns precede it.
- 7-col → date at col 2, 8-col → col 3, 9-col → col 4 (unchanged), post-QC 10-col → capped at 4

Regression: 9/9 green after fix. New file produces 18 rows across all 5 sheets.

### Why QC didn't save us
`pdf_qc.py::_init_qc_context` reads **only the first sheet** to establish anchor columns,
then applies those same anchors to all sheets in `_correct_all_sheets`. For this file,
Sheet1 (9-col) set `expected_date_col = 4`. When QC processed Sheet4/Sheet5, it checked
col 4 for a date, found Proceeds/Cost instead, detected no right-shift, and moved on.
QC Pass 2 (empty-cell collapse) also did nothing — it only moves anchors one position
within the financial zone, not entire layout shifts.

### The proper fix: per-sheet anchor detection in QC
`_correct_all_sheets` should call `_find_anchor_cols(df)` per sheet, not once globally.
This would make QC self-correcting for any broker whose sheets have varying column counts.

**Why this wasn't done as the fix**: `_find_anchor_cols` calls `_verify_or_search_col`,
which tries to verify the config position in the header, then **falls back to the config
when it fails** (search disabled). So per-sheet detection would still return col 4 from
config for Sheet5 — no improvement without also fixing the search.

### Why the search in `_verify_or_search_col` was disabled
The keyword search was previously enabled but disabled after it returned wrong anchors:
- **Morgan Stanley**: Cost → col 0 (hit a description cell containing "cost")
- **JP Morgan**: Date Acquired → col 17, Cost → col 20 (hit description/CUSIP text)
- **Schwab 10-col**: Date Acquired → col 5 (correct for raw 10-col, but QC normalises
  to col 4 via Pass 1 — search and normalisation were fighting each other)

Root cause: Schwab/MS/JP Morgan have **multi-row headers** (labels spread across 3 rows).
`_find_header_row` picks the single row with the most keyword hits (usually the bottom
header row), but Date Acquired lives in a different header row. Single-row scanning
therefore misses it and hits a random cell elsewhere.

### What a proper implementation would need
1. Move `_find_anchor_cols(df)` call inside the per-sheet loop in `_correct_all_sheets`
2. Fix `_verify_or_search_col` to scan **all header rows** (first 15 rows), not just the
   single best-match row — so multi-row headers (Schwab, MS, JPM) are handled correctly
3. Narrow search keywords to avoid false positives (e.g. require "1b" not just "date")
4. Test against all 9 brokers — especially Morgan Stanley, JP Morgan, Schwab 10-col

### Brokers that would benefit
- **Schwab**: sheets with varying col counts (confirmed with this file)
- **Apex Clearing**: Sheet1=9col, Sheet2=8col — currently broker module handles both,
  but per-sheet QC would be cleaner
- All others: single uniform layout — no impact either way

### Related
- Old entry "QC `_verify_or_search_col` — Review and Cleanup" merged into this entry
