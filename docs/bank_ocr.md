# Bank Statement OCR Extractor — Detail Notes

## Overview
Standalone Python script to OCR Citibank checking account statements (image-only PDFs)
and output a structured CSV of transactions.

## Files
- `bankdetails_dataextraction/extract_bank_txns.py` — main script
- `bankdetails_dataextraction/requirements.txt` — pip dependencies
- `bankdetails_dataextraction/citibank_2022_transactions.csv` — 2022 test output

## Usage
```
python extract_bank_txns.py "path/to/images/folder" --output result.csv
```
Images must be JPG/PNG/TIF. Named with natural sort order (page-0, page-1 ... page-10 etc).

## Architecture

### OCR Strategy: Dual PSM
- Runs Tesseract twice per page: `--psm 6` (uniform block, better for tables) and `--psm 3` (default)
- Picks whichever mode finds more transaction lines with amounts on the same line
- Critical fix: PSM 3 reads Zelle/multi-transaction pages as two separate column blocks
  (descriptions left, amounts right) losing all mid-column amounts. PSM 6 keeps them together.

### Parsing Logic
1. Split OCR text by `\n`, scan line by line
2. `MM/DD` pattern = transaction start
3. If amounts found on same line → parse immediately
4. If no amounts on date line → `pending_no_amounts` state, look at next line for amounts (OCR column split)
5. Continuation lines (vendor name, reference #) appended to description (max 2 lines)
6. Boilerplate markers stop continuation and flush current transaction

### Amount Classification
- Credits checked FIRST (more specific), then debits — prevents "Returned Insufficient Funds - Check #" matching debit "Check #"
- `[CHECK TYPE]` flag added to description when classification is unknown
- 1-amount lines: use keyword to decide if it's the transaction amount (balance missed by OCR)

### Statement Period Detection (3-tier fallback)
1. OCR text: "AS OF MONTH DD, YYYY" (readable text)
2. Banner crop: dark header with white text — crop image region, threshold, OCR with `--psm 7`
3. Infer from last transaction date on page + detected year

### Totals Validation
- Parses "Total Subtracted/Added" line at bottom of each transaction page
- Compares against sum of parsed transactions
- On mismatch: flags ALL rows on that page with `VERIFY - page total mismatch`
- Inserts sentinel placeholder row: `*** MISSING ROWS - check page manually ***` with gap amounts

## Known Issues / Limitations
- **Blanket page flag**: All rows on a mismatched page get flagged even if only 1 row is wrong. Accepted tradeoff — no reliable way to pinpoint specific bad rows.
- **OCR quality**: Some pages have overlapping/garbled text from scan quality — these show up as flagged pages. Manual correction required for those.
- **Statement period**: "AS OF" banner is white text on dark background, Tesseract misses it. Banner crop + threshold partially works (gets month, year garbled). Date inference fills remaining gaps.

## Keywords
### DEBIT_KEYWORDS (subtracted)
Wire Transfer Fee, Incoming Wire Fee, Debit Card Purchase, ACH Electronic Debit,
Check #, Check#, Recurring Card Purchase, Bill Payment, Online Payment,
Zelle Payment, Zelle Debit, Wire Transfer Debit, ATM Withdrawal, Cash Withdrawal,
Debit Pay, Citibank Online Pmt, Transfer To, Transter to (OCR variant),
Outgoing Domestic, Domestic Funds Transfer, Service Fee, Mobile Purchase, Purchase

### CREDIT_KEYWORDS (added) — checked FIRST
Incoming Wire Transfer, Incoming Wire, Insufficient Funds (returned funds),
ACH Electronic Credit, Deposit, Transfer From, Direct Dep, DIRECT DEP,
Wire Transfer Credit, Zelle Credit, Other Credit, Refund, Interest Payment

### Adding new keywords
- Open `extract_bank_txns.py`, find `DEBIT_KEYWORDS` / `CREDIT_KEYWORDS` lists
- Add more specific patterns before generic ones
- Keywords are case-insensitive (both sides `.upper()` before comparison)
- If a keyword appears in both debit and credit contexts, put the more specific one in CREDIT_KEYWORDS (checked first)

### Boilerplate markers
"Monthly Service Fee*" (with asterisk) is boilerplate (fee table row).
"Monthly Service Fee" (no asterisk) is a real transaction — NOT in boilerplate list.

## Parking Lot
- **Garbled text detection**: User suggested skipping a page entirely if OCR output looks garbled, with a warning. Decided against — too hard to define "garbled" reliably. Totals validation catches the same cases more precisely (tells you the gap amount too). Could revisit if false positives become a problem.

## Adding New Keywords — Workflow
1. Run script, check `[CHECK TYPE]` flagged rows in CSV
2. OCR the specific page: `tesseract image.jpg stdout` to see exact text
3. Add keyword to appropriate list
4. Re-run and verify flag disappears

## Remote System Setup
1. Install Python 3
2. Install Tesseract OCR binary (Linux: `sudo apt install tesseract-ocr`, Windows: UB Mannheim installer)
3. `pip install pytesseract Pillow`
4. If Tesseract not on PATH, uncomment line 19 in script and set path:
   `pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'`
