# findata-utils

Three tools for financial data processing and practice management.

---

## 1. Stock Transaction Processor (`stock_processor/`)

Converts broker 1099-B files (Excel or CSV) into Drake tax software import format.

**Supported brokers:** Fidelity, Merrill Lynch, Morgan Stanley, Robinhood, Apex Clearing, JP Morgan, Betterment

**How to run:**
```bash
cd stock_processor
pip install -r requirements.txt
streamlit run app.py
```

Then open the browser, select your broker, upload the file, and download the Drake-formatted output.

**Run regression tests:**
```bash
python test_regression.py          # all 8 brokers
python test_regression.py Merrill  # single broker
python test_regression.py -v       # verbose (shows cell counts)
```

**Profile a new broker file before building a module:**
```bash
python broker_profiler.py <file.xlsx> [sheet_name]
```

---

## 2. Bank Statement OCR Extractor (`bankdetails_dataextraction/`)

Extracts transactions from scanned Citibank checking statement images using OCR.

**Dependencies:** Requires [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed at `C:\Program Files\Tesseract-OCR\tesseract.exe`

**How to run:**
```bash
cd bankdetails_dataextraction
pip install -r requirements.txt
python extract_bank_txns.py "path/to/images/folder" --output result.csv
```

Input is a folder of JPG/PNG images (one per statement page, extracted from PDF via PDF24).
Output is a CSV with columns: `statement_period, date, description, subtracted, added, balance, flag, source_page`

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
