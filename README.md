# findata-utils

Three tools for financial data processing and practice management.

---

## 1. Stock Transaction Processor (`stock_processor/`)

Converts broker 1099-B files (Excel or CSV) into Drake tax software import format.

**Supported brokers:** Fidelity, Merrill Lynch, Morgan Stanley, Robinhood, Apex Clearing, JP Morgan, Betterment, Charles Schwab, Pershing LLC

**How to run:**
```bash
cd stock_processor
pip install -r requirements.txt
streamlit run rasrich_tools.py
```

Then open the browser, select your broker, upload the file, and download the Drake-formatted output.

**Run regression tests:**
```bash
python test_regression.py          # all 10 tests (9 brokers, 2 Schwab variants)
python test_regression.py Merrill  # single broker
python test_regression.py -v       # verbose (shows cell counts)
```

**Profile a new broker file before building a module:**
```bash
python broker_profiler.py <file.xlsx> [sheet_name]
```

The Streamlit app also includes the **Transaction Tagger** — a 5-step workflow to tag bank/CC transactions to tax expense categories using Claude AI + preparer review. Features two-level taxonomy (generic IRS tag + specific subcategory), improved vendor name extraction, and monthly summary pivot. See `REQUIREMENTS.md` for full spec.

---

## 2. Bank Statement OCR Extractor (`bankdetails_dataextraction/`)

Extracts transactions from scanned bank statement images (Chase checking) using OCR.
Reconciles extracted transactions against printed section totals — flags gaps and inserts sentinel rows for missing transactions.

**Dependencies:** Requires [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed at `C:\Program Files\Tesseract-OCR\tesseract.exe`

**How to run:**
```bash
cd bankdetails_dataextraction
pip install -r requirements.txt

# Chase checking statements → CSV
python extract_chase_txns.py "path/to/images/folder" --output result.csv

# Chase credit card statements → Excel
python extract_chase_cc_txns.py "path/to/images/folder" --output result.xlsx
```

Input is a folder of JPG/PNG images (one per statement page, extracted from PDF via PDF24).

**Chase checking** output: CSV with columns `statement_period, date, description, subtracted, added, balance, flag, source_page`. Sections recognised: Deposits & Additions, Checks Paid, ATM & Debit Card Withdrawals, Electronic Withdrawals, Other Withdrawals, Service Fees, Fees.

**Chase credit card** output: Excel with columns `Date, Description, Amount, Source Page, Flag`. Detects ACCOUNT ACTIVITY section, reconciles against TRANSACTIONS THIS CYCLE total.

**Indian bank statements** (`extract_india_bank_txns.py`): PDF extraction (no OCR needed for digital PDFs) supporting HDFC, Kotak, and scanned/rotated formats. Output: Excel with Transactions + Reconciliation sheets.

### Interest & TDS Finder (`find_interest_tds.py`)

Scans any bank transaction Excel or CSV and extracts **Interest Income** and **Tax Deducted (TDS)** rows into a summary Excel. Uses two-pass detection: keyword regex (bank abbreviation codes) + cosine semantic similarity (natural language descriptions). Near-miss rows land in an amber **Review** sheet for human inspection.

**How to run:**
```bash
cd bankdetails_dataextraction
pip install -r requirements.txt

python find_interest_tds.py transactions.xlsx
python find_interest_tds.py transactions.csv --locale us --threshold 0.6
```

Also available as a Claude Code slash command: `/find-interest-tds transactions.xlsx`

Locale configs (keywords, anchors, column hints) in `interest_tds_configs/india.yaml` and `us.yaml` — tune without any code changes. See `REQUIREMENTS.md` for full spec.

---

## 3. Trello Weekly Status Pivot (`trellostatus/`)

Generates a formatted Excel summary of card counts per Trello list from a board JSON export. Run every Saturday.

**How to run:**
```bash
cd trellostatus
python trello_pivot.py
```

Export the Trello board as JSON (Board menu → Print and Export → Export as JSON), drop it in the `trellostatus/` folder, then run the script. Output is `trello_list_pivot.xlsx` — import into Google Sheets.

See `trellostatus/README.md` for the full weekly routine.
