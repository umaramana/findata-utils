# How to Tag a Bank Statement — Full Pipeline

## Overview

```
Bank Statement PDF
      ↓
  PDF24 (PDF → images)
      ↓
  OCR Extractor (command line — per bank)
      ↓
  Tab Collator (app — only if bank has monthly tabs, no Master sheet)
      ↓
  Transaction Tagger (app — 5-step workflow)
```

---

## Prerequisites

- **PDF24** installed — used to split the bank statement PDF into one image per page
- **Tesseract OCR** installed at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Python and dependencies installed (see First-time setup below)

### First-time setup (new machine)

1. Install Python from python.org — tick **"Add Python to PATH"** during setup.
2. Install dependencies:

```
cd C:\Users\UN\fractals\VibeCoding\ClaudeCode
pip install -r stock_processor\requirements.txt
pip install -r bankdetails_dataextraction\requirements.txt
```

### Starting the app

```
cd C:\Users\UN\fractals\VibeCoding\ClaudeCode
python -m streamlit run app.py
```

> If you see `'streamlit' is not recognized`, use `python -m streamlit run app.py` instead of `streamlit run app.py`. This works even when Streamlit is not on the system PATH.

---

## Stage 1 — Convert PDF to Images (PDF24)

Open PDF24 → **PDF to Images**.

- Input: bank statement PDF
- Output format: JPG or PNG
- One image per page
- Save all images to a single folder, e.g. `chase_jan_mar\`

---

## Stage 2 — Run the OCR Extractor

Run the script for your bank from the `bankdetails_dataextraction/` folder. Each script takes the folder of images as its input.

### Citibank (checking)
```
python scripts/extract_bank_txns.py "path\to\citi\images"
```
Output: Excel with **Summary + Master + monthly tabs** — skip Stage 3, go straight to Stage 4.

### Capital One
```
python scripts/extract_capitalone_txns.py "path\to\capitalone\images"
```
> Image filenames must be prefixed `YYYYMMDD-` (e.g. `20240115-page1.jpg`).

Output: one Excel per account — skip Stage 3, go straight to Stage 4.

### Chase Business Checking
```
python scripts/extract_chase_txns.py "path\to\chase\images"
```
Output: Excel with **Summary + monthly tabs** (no Master) — go to Stage 3.

### Chase Credit Card
```
python scripts/extract_chase_cc_txns.py "path\to\chase_cc\images"
```
Output: Excel with **monthly tabs** (no Master) — go to Stage 3.

### Chase Freedom (mobile screenshots)
```
python scripts/extract_freedom_txns.py "path\to\freedom\images"
```
Output: CSV — go straight to Stage 4, upload the CSV directly.

### Indian Banks (HDFC, Kotak, scanned)
```
python scripts/extract_india_bank_txns.py file.pdf
python scripts/extract_india_bank_txns.py folder\   # all PDFs in folder
```
Output: Excel with **Transactions + Reconciliation tabs** — skip Stage 3, go straight to Stage 4.

---

## Stage 3 — Tab Collator (Chase only)

> Skip this stage if your extractor output already has a Master sheet (Citibank, Capital One, Indian banks).

In the app, open **Excel Utilities**.

1. Upload the extractor output Excel file.
2. Select the monthly tabs to include (deselect Summary/header tabs if present).
3. Review auto-detected column types — mark any whole-number columns (e.g. check numbers) as Integer.
4. Click **Collate**.
5. Download the output — it has a new **Master** tab prepended with an inline reconciliation summary.

Use this Master-sheet Excel as the input to Stage 4.

---

## Stage 4 — Transaction Tagger

In the app, open **Transaction Tagger**.

### Step 1 — Setup

| Field | What to enter |
|---|---|
| **Client ID** | Short identifier, e.g. `devlin` — used as the lookup filename |
| **Entity Type** | Sole Prop / SMLLC, S-Corp, or Partnership / MMLLC |
| **Primary Business Activity** | e.g. `Interior design and construction` |
| **Secondary Activity** | Optional, e.g. `Rental property` |
| **Confidence Threshold** | Default 75% — Claude flags anything below this for your review |
| **Tagging Mode** | Review-first (you tag first, Claude fills gaps) or Pre-tag (Claude tags all, you review) |

### Step 2 — Upload Transactions

1. Upload the Excel or CSV from Stage 3 (or directly from Stage 2 for Citibank/Capital One).
2. If the file has multiple sheets, select **Master**.
3. Map the columns:
   - **Description** — the transaction narrative column
   - **Amount format**: single column (negative = expense, e.g. Chase) or two columns (Debit/Credit, both positive)
   - **Date column** — optional; enables monthly pivot in output
4. If the file has a **Lookup tab** (sheet name containing "lookup"), client-specific tags load automatically.

In Pre-tag mode, Claude runs here with a progress bar before moving to Step 3.

### Step 3 — Preparer Review

**Review-first**: tag what you recognise in the vendor table — leave blank to send to Claude. Click **Apply & Refresh**, then **Next**.

**Pre-tag**: two sections appear — pre-tagged vendors (Claude/lookup suggestions, expand to review) and vendors needing your attention. Fill blanks, then click **Next**.

### Step 4 — Claude Tags the Rest

Click **Run Claude →**. Claude Haiku processes remaining vendors in batches of 30.

After Claude runs, low-confidence rows are surfaced for your review. Correct any tags in the **Your Tag** and **Your Subcategory** columns, then click **Apply Tags & Continue**.

### Step 5 — Output

Click **Download Tagged File**. The lookup table is updated automatically for next time.

| Tab | Contents |
|---|---|
| **Tagged** | All transactions with Tag, Subcategory, Tag Source, Confidence, Reason |
| **Personal** | Rows tagged "Personal - *" |
| **Review with Client** | Unresolved rows |
| **Summary** | Monthly pivot — Tag/Subcategory rows, month columns, Grand Total |

---

## Notes

- **Lookup file** — saved automatically to `stock_processor/lookups/{client_id}_lookup.csv` after each run. Known vendors are pre-filled without calling Claude on the next run. Never commit this file.
- **Restart the app** after changing any Python scripts (`Ctrl+C` then `python -m streamlit run app.py`) — Streamlit hot-reload does not re-import modules.
- **Reconciliation** — every OCR extractor includes a balance-walk check. Rows with mismatches are flagged `VERIFY` in the Flag column. Review these before tagging.
