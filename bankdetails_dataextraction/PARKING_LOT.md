# Bank Details Extraction — Parking Lot

Future features and known gaps for scripts in `bankdetails_dataextraction/`.

---

## Regression Suite — Bank Statement Extractors

Build a regression test suite for all OCR extractors, similar to `stock_processor/test_regression.py`.

**What's needed:**
- `test_regression_bank.py` — one test per extractor
- Baselines in `testdata/passedtestcases/` — input image set + expected Excel per extractor
- Tests verify: transaction count, total Subtracted, total Added, Summary Gap = $0
- Test runner: `python test_regression_bank.py` → pass/fail per extractor

**Test data already in `testdata/`:**
- `testdata/citibank/CCF_000020 images/` — Citibank Basic Banking format
- `testdata/freedom/freedomimgs/` — Chase Freedom screenshots
- `testdata/india/indiabanktrans/` — Indian bank PDFs (HDFC, Kotak)

**Gaps — test data still needed:**
- Capital One: 1–2 months, 1 account
- Chase business checking: any month
- Chase credit card: any month

**Priority**: High — zero regression coverage currently

---

## Citibank — DPI Upscaling (VERIFY flag reduction)

~22 VERIFY flags per full-year run caused by OCR digit misreads in narrow Citi Priority amount columns (e.g., `$1,461.42` read as `$18.42`).

**Proposed fix**: 2× image upscale before Tesseract in `ocr_image()`:
```python
img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
```

**Why deferred**: 2× upscale increased transaction counts on some pages (PSM picked up continuation lines as transactions), inflating totals. Needs more investigation — possibly a 1.5× upscale or a page-type-specific DPI override.

---

## Interest & TDS Finder — Bank Account Tagging

When a client has multiple bank accounts, output totals broken down per account.

**Requirements:**
- Input carries a **Bank Account** column (account number, bank name, or alias)
- Output sheets show totals per bank account + currency
- Support mixed INR/USD files
- If no account column → skip grouping (current behaviour preserved)

| Bank Account | Currency | Total |
|---|---|---|
| HDFC SB ××××1234 | INR | +12,500.00 |
| Chase ××××9012 | USD | +340.50 |

**Design**: add `account` to `column_hints` in YAML; add `default_currency` per locale YAML.

**Priority**: Medium

---

## Chase CC — Summary tab + reconciliation row

- Add a Summary tab to `extract_chase_cc_txns.py` output (one row per month, totals + net)
- Add a reconciliation summary row after all transactions showing `TRANSACTIONS THIS CYCLE: $X.XX` — green if reconciled, red if gap

---

## OCR Extractors — Shared utilities refactor

Scripts (`extract_bank_txns.py`, `extract_chase_txns.py`, `extract_capitalone_txns.py`, etc.) duplicate OCR boilerplate: image loading, natural sort, Tesseract config, PSM picker, Excel styling constants.

**Proposed**: extract into `scripts/ocr_utils.py` — shared module imported by all extractors.

**Why deferred**: scripts work correctly today; refactor has regression risk and no user-facing benefit. Do when adding a new extractor that would otherwise copy the pattern a 5th time.

---

## Streamlit Integration

Wrap all OCR extractors as a new page in the Streamlit app:
- Upload images → pick bank/statement type → download Excel
- Would eliminate the need to run scripts from the command line

**Prerequisite**: shared utils refactor above.

---

## PDF-direct extraction (skip PDF24 image conversion)

For digitally-generated PDFs (not scanned), `pdfplumber` can extract text directly — no image conversion needed. Capital One and Citibank PDFs are typically native (text-based).

**Effort**: ~4 hrs per bank (new parser, reuse Excel infrastructure). See session notes for full assessment.

**Priority**: Low — current image-based workflow works; PDF-direct is a convenience improvement.
