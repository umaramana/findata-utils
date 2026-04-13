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

Extracts transactions from scanned bank statement images using Tesseract OCR. Outputs Excel workbooks with Summary, Master, and per-month/per-account tabs. Balance reconciliation built into every extractor.

**Folder structure:**
```
bankdetails_dataextraction/
├── scripts/        ← all 7 Python scripts
├── configs/        ← YAML config files (bank formats, interest/TDS categories)
├── testdata/       ← test images and PDFs
├── REQUIREMENTS.md ← full spec for all scripts
└── PARKING_LOT.md  ← future features
```

**Dependencies:** Requires [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed at `C:\Program Files\Tesseract-OCR\tesseract.exe`

```bash
cd bankdetails_dataextraction
pip install -r requirements.txt
```

### Supported banks

| Script | Bank | Output |
|---|---|---|
| `scripts/extract_bank_txns.py` | Citibank checking | Excel — Summary + Master + monthly tabs |
| `scripts/extract_capitalone_txns.py` | Capital One (all accounts) | One Excel per account |
| `scripts/extract_chase_txns.py` | Chase business checking | Excel — Summary + monthly tabs |
| `scripts/extract_chase_cc_txns.py` | Chase credit card | Excel — monthly tabs |
| `scripts/extract_freedom_txns.py` | Chase Freedom (mobile screenshots) | CSV |
| `scripts/extract_india_bank_txns.py` | HDFC, Kotak, scanned Indian banks | Excel — Transactions + Reconciliation |

**How to run:**
```bash
# Citibank — images folder (any naming)
python scripts/extract_bank_txns.py "path/to/citi/images"

# Capital One — images must be named YYYYMMDD-*.jpg
python scripts/extract_capitalone_txns.py "path/to/capitalone/images"

# Chase checking
python scripts/extract_chase_txns.py "path/to/chase/images"

# Indian bank PDFs
python scripts/extract_india_bank_txns.py file.pdf
python scripts/extract_india_bank_txns.py folder/   # all PDFs in folder
```

Input: folder of JPG/PNG images, one per statement page (extracted from PDF via PDF24).

**Reconciliation**: every extractor includes balance-walk verification. Mismatches flagged as `VERIFY` in the Flag column. Summary tab shows parsed totals vs statement totals — Gap should be $0.

### Interest & TDS Finder (`scripts/find_interest_tds.py`)

Scans any bank transaction Excel or CSV and extracts **Interest Income** and **Tax Deducted (TDS)** rows. Two-pass detection: keyword regex (bank abbreviation codes like `Int.Pd`, `TDS`) + cosine semantic similarity for natural language descriptions. Near-miss rows go to an amber **Review** sheet.

```bash
python scripts/find_interest_tds.py transactions.xlsx
python scripts/find_interest_tds.py transactions.csv --locale us --threshold 0.6
```

Also available as a Claude Code slash command: `/find-interest-tds transactions.xlsx`

Locale configs in `configs/interest_tds_configs/india.yaml` and `us.yaml` — tune keywords and anchors without code changes.

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
