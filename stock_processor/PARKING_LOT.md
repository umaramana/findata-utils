# Parking Lot - Future Features

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

## QC `_verify_or_search_col` — Review and Cleanup
- The keyword search fallback in `_verify_or_search_col` (pdf_qc.py) was disabled — now trusts BROKER_CONFIG when header verify fails
- Search was unreliable: returned wrong columns for Morgan Stanley (Cost=col 0), JP Morgan (DA=col 17, Cost=col 20), Schwab (DA=col 5 on 10-col sheets)
- All three brokers had 0 QC fixes with wrong anchors — broker modules handle positions independently
- **Action**: Review with additional test data or documentation to confirm search is dead code, then remove entirely
