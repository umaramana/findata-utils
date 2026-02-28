# Project Memory

## Prompting Guide
- **Full guide**: [prompting_guide.md](prompting_guide.md)
- **Bug report format**: "Page X (filename), row Y — expected [subtracted: 1000], got [balance: 1000]. Description reads: [exact text]"
- **Key rule**: Share exact text, not recollections. Filename, not "another file".
- **Efficiency log**: also in prompting_guide.md — target 75%, Phase 1 scored 65%

## Working Principles
- **Evaluate before planning**: Before diving into solution design, do a quick upfront check — what does the feature actually warrant? Ask: (1) What's the simplest version that solves the problem? (2) What assumptions are we making? (3) What are the data/environment constraints? See [patterns.md](patterns.md) for details.
- **Explain logic before coding**: Always explain the approach and get user approval before writing code. Don't run code first and explain after.
- **Collaborate, don't just execute**: Before committing to an approach, narrate it — "I'm choosing X over Y because Z — agree?" This is especially critical for architectural decisions. "Built it, here's the output" without prior alignment = low collaboration and often wasted turns.
- **Don't backtrack on approved decisions**: Once the user approves an approach (e.g., "Option C"), stick with it. Don't silently revert to a different approach in implementation.
- **Present options for non-trivial decisions**: Give 2-3 clear options with pros/cons. Let the user choose. Don't assume.
- **End-of-session memory update**: At the end of every significant build session, run efficiency analysis (see patterns.md) and save any new learnings to memory files. Never let valuable methodology or decisions go unsaved. Then sync `docs/` in the repo: copy updated memory files into `docs/`, commit, and push — so git history backs up the context.
- **Understand the data first**: Before solutioning, verify assumptions about the actual data (column counts, layouts, edge cases) rather than guessing from code logic alone.

## Project: Stock Transaction Processor
- **Location**: `stock_processor/` — Streamlit app converting broker 1099-B Excel files to Drake tax import format
- **Brokers supported**: Fidelity ✅, Merrill Lynch ✅, Morgan Stanley ✅, Betterment (CSV) ✅, Apex Clearing ✅, Robinhood ✅, JP Morgan ✅, Charles Schwab (parked — bug)
- **Key files**: `app.py` (Streamlit UI), `pdf_qc.py` (column QC), `drake_mapper.py`, `brokers/fidelity.py`, `brokers/schwab.py`, `brokers/robinhood.py`, `brokers/merrill.py`, `brokers/morgan_stanley.py`, `brokers/betterment.py`, `brokers/apex_clearing.py`, `brokers/jpmorgan.py`, `utils.py`, `broker_profiler.py`
- **Requirements doc**: `stock_processor/REQUIREMENTS.md`
- **Broker Profiler**: `python broker_profiler.py <file.xlsx|file.csv> [sheet_name]` — run on new broker files FIRST. Outputs column profiles, anchor detection, similarity ranking vs existing brokers. Use before building any new broker module.
- **pdf_qc.py**: Column QC — universal. Pass 1: RIGHT-shifts (date found right of expected → shift left). Pass 2: LEFT-shifts / empty-cell-collapse (Date Acquired and Gain/Loss shifted left when spacer/optional cols empty → move back right). See [stock_processor_qc.md](stock_processor_qc.md).
- **Three numeric anchors**: Proceeds | Cost | [Accrued?] | [Wash Sale?] | Gain/Loss. First 2 = always Proceeds/Cost. Last = always Gain/Loss (NEVER empty). Optionals between Cost and Gain/Loss. See [stock_processor_architecture.md](stock_processor_architecture.md).
- **Empty cell collapse**: PDF24 artifact — when optionals are absent, Gain/Loss slides left into optional positions. Fix: detect via Gain/Loss being empty at expected col, scan backward, move to correct position. Implemented as `_fix_empty_cell_collapse(df, cost_col_idx, gain_loss_col_idx)` in fidelity.py (standalone reusable fn).
- **Gain/Loss**: NEVER empty for real transaction rows. NOT in Drake output. Marks end of optional zone. Key rule: if Gain/Loss col is empty → collapse detected.
- **Parking lot**: Subtotal aggregation per stock; **Summary Page QC + Pass 3** (see below); Proceeds gap (~$4,640 / ~4 missing txns in Merrill test); Schwab test files in `testdata/` (parked); Robinhood 2024 test file in `testdata/` (secondary test data); Remove Fidelity `_fix_empty_cell_collapse()` (QC Pass 2 handles it)

## Regression Suite
- **Location**: `stock_processor/test_regression.py`
- **Run**: `python test_regression.py` — 8/8 green (Fidelity ×2, Merrill, Morgan Stanley, Betterment, Apex Clearing, Robinhood, JP Morgan)
- **Filter**: `python test_regression.py Merrill` — run only matching tests
- **Verbose**: `python test_regression.py -v` — confirm cell counts on pass
- **Update baselines**: `python test_regression.py --update` (or `Fidelity --update`) — regenerates expected output files
- **Baselines location**: `testdata/passedtestcases/` — input + expected output per broker. **Baselines are manually verified by user against original PDF totals** (one-time human QA). Original PDFs not stored for security. NEVER regenerate baselines (`--update`) without user approval — a failing test means the code broke, not the baseline.
- **Workflow**: run `python test_regression.py` after EVERY broker change before committing
- **Betterment date fix**: Added `MM-DD-YYYY` and `MM-DD-YY` dash patterns to `_format_date()` in `drake_mapper.py`

## Parked / Known Bugs
- **Schwab wash sale bug**: `_standardize_columns` in `schwab.py` blindly maps `Proceeds+3` to "Wash Sale" regardless of actual column count — Gain/Loss values bleed into Wash Sale slot. Fix: detect actual column count before mapping. Schwab is commented out in TEST_CASES in `test_regression.py`.
- **Schwab test files**: input = `testdata/charlesschwab-1099 test.xlsx`, correct row count = 13, Proceeds = $58,507.12, Cost = $37,505.76, Wash Sale = $0 (no wash sales in this file)

## Apex Clearing Notes
- **Layout**: Alternating desc/data rows. Col 0=Date Sold, 1=Qty, 2=Proceeds, 3=(spacer, collapses), 4=Date Acquired, 5=Cost, 6=Wash Sale, 7=Gain/Loss
- **Sheet1**: 9 cols (has "Additional Notes" col 8), Sheet2: 8 cols — broker module handles both
- **Date format**: YYYY-MM-DD (ISO) — added to `_format_date()` in drake_mapper.py
- **Left-shift**: Col 3 spacer collapses, Date Acquired slides left to col 3 → fixed by Pass 2 in pdf_qc.py
- **Parking lot**: `_parse_accrued_wash_sale()` treats all values as Wash Sale; "(M)"/"(D)" markers need handling when non-zero test data available
- **Test**: 11 txns, Proceeds=$3,192.70, Cost=$5,189.38

## JP Morgan Notes
- **Status**: Complete. Manually verified, regression baseline created. 8/8 tests pass.
- **Source**: PDF converted via Excel's built-in import (not PDF24). Single sheet `Append1`, 912 raw rows.
- **Layout**: Cols 0-3 = description/CUSIP, col 4 = qty, col 5 = Date Acquired, col 6 = Date Sold, col 7 = Proceeds, col 8 = Cost, col 9 = Accrued, col 10 = Wash Sale, col 11 = Gain/Loss, col 12 = Additional Info, cols 13-35 = empty padding
- **Options row shift**: On 91/518 rows (PUT/CALL with expiry/strike in cols 2-3), Accrued and Wash Sale shift from cols 9-10 to cols 13-14. Currently handled with fallback in `jpmorgan.py`. **To be replaced by QC Pass 3** (see parking lot).
- **Description pattern**: Transaction rows carry description in cols 0+1. Description-only rows (cols 0-3 text, no dates) appear AFTER the first transaction for a stock and append to the previous transaction's description. Subsequent empty-description rows inherit `current_description`.
- **Repeating headers**: CUSIP / (Box 1a) markers repeat ~34 times through the file — skipped via keyword matching.
- **Regression**: 518 rows × 15 cols = 7,770 cells verified. Baseline at `testdata/passedtestcases/`.
- **Use broker_profiler.py**: Always run on new broker files before building modules — don't write ad-hoc analysis scripts.

## Project: Bank Statement OCR Extractor
- **Location**: `bankdetails_dataextraction/` — standalone Python script (no Streamlit) to extract Citibank checking transactions from scanned image files
- **Script**: `extract_bank_txns.py` — run as `python extract_bank_txns.py "path/to/images/folder" --output result.csv`
- **Dependencies**: `pytesseract==0.3.13`, `Pillow==11.1.0`, Tesseract OCR binary at `C:\Program Files\Tesseract-OCR\tesseract.exe`. Requirements in `requirements.txt`.
- **Input**: Folder of JPG/PNG images (one per page), extracted from PDF via PDF24
- **Output**: CSV with columns: `statement_period, date, description, subtracted, added, balance, flag, source_page`
- **Tested on**: `CCF_000020 images/` (2022, 24 pages, 79 txns) and `CCF_000023-8.jpg` (Zelle-heavy page, 47 txns, exact total match)
- **See detail file**: [bank_ocr.md](bank_ocr.md)
