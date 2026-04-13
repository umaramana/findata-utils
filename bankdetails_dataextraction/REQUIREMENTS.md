# Bank Details Extraction — Requirements

All scripts live in `bankdetails_dataextraction/`.  
Input: scanned statement images (JPG/PNG) or PDFs.  
Output: Excel workbooks with Summary, Master, and per-month/per-section tabs.

---

## Scripts at a Glance

| Script | Bank / Source | Input | Output |
|---|---|---|---|
| `extract_bank_txns.py` | Citibank checking | Image folder | One Excel, tabs by month |
| `extract_capitalone_txns.py` | Capital One (all accounts) | Image folder | One Excel **per account** |
| `extract_chase_txns.py` | Chase business checking | Image folder | One Excel, tabs by month |
| `extract_chase_cc_txns.py` | Chase credit card | Image folder | One Excel, tabs by month |
| `extract_freedom_txns.py` | Chase Freedom (mobile screenshots) | Image folder | CSV |
| `extract_india_bank_txns.py` | Indian banks (HDFC, Kotak, etc.) | PDF folder | Excel per file |
| `find_interest_tds.py` | Any bank — interest & TDS scan | Excel / CSV | Excel with category sheets |

---

## 1. Citibank Statement Extractor (`extract_bank_txns.py`)

### Usage
```bash
python extract_bank_txns.py "path/to/images/folder"
python extract_bank_txns.py "path/to/images/folder" --output result.xlsx
```

### Supported statement formats
| Format | Date style | Months seen |
|---|---|---|
| Basic Banking (bordered) | `MM/DD` | Jan, Feb, Mar 2025 |
| Citi Priority (borderless) | `MM/DD/YY` | Apr–Dec 2025 |

Both formats detected automatically per page.

### Input
Folder of JPG/PNG images. Files named anything — sorted naturally.  
Multiple months can be in one folder; period is auto-detected per page.

### Output
Single Excel file: **Summary → Master → per-month tabs** (chronological).

| Tab | Contents |
|---|---|
| Summary | Month \| Txns \| Parsed Sub \| Parsed Add \| Net \| Statement Sub \| Statement Add \| Sub Gap \| Add Gap |
| Master | All transactions with Month column |
| Jan 2025 … Dec 2025 | Date \| Description \| Subtracted \| Added \| Balance \| Flag |

**Statement Sub/Add** = values from the `Total Subtracted/Added` row on the last page of each month (cumulative month total). Gap should be $0 when all transactions are captured.

### Transaction columns
- **Date**: `MM/DD` or `MM/DD/YY` — kept as OCR'd
- **Subtracted / Added**: separate columns (not a single signed amount)
- **Balance**: running balance from statement
- **Flag**: `VERIFY: expected X, got Y` when balance walk detects a mismatch

### OCR strategy
- PSM 6 vs PSM 3 compared per page; whichever finds more `MM/DD[/YY]` transaction lines wins
- PSM 3 wins on Citi Priority (borderless) pages — critical for picking up Zelle Credits and other right-column amounts that PSM 6 misses

### Credit keyword classification
When a transaction row has 2 amounts (one pre-balance amount + balance), sign is inferred from description keywords.  
Credits checked first (more specific) → debits → unknown (defaults to subtracted + `[CHECK TYPE]` tag).

Key credit keywords include: `ACH Electronic Credit`, `Deposit`, `Zelle Credit`, `Purchase Return`, `Transfer From`, `Mobile Deposit`, `Refund`, `Direct Dep`, `Incoming Wire`.

### Reconciliation
- **Balance walk** (per statement period): `prev_balance + added − subtracted ≈ balance`. Mismatches flagged as VERIFY in Flag column. Walk resets at each new statement period — no cross-month contamination.
- **Summary tab Gap**: Parsed total vs statement's own `Total Subtracted/Added` cumulative row.
- No auto-correction — original OCR values always preserved.

### Known limitations
- ~22 VERIFY flags per full year run (OCR digit misreads on amount columns in narrow Citi Priority layout)
- DPI upscaling (2×) reduces misreads but can inflate transaction counts — deferred

---

## 2. Capital One Statement Extractor (`extract_capitalone_txns.py`)

### Usage
```bash
python extract_capitalone_txns.py "path/to/images/folder"
python extract_capitalone_txns.py "path/to/images/folder" --output-dir "path/to/output"
```

### Accounts
Auto-detected from statement headers. Three accounts for RLS client:
- Simply Checking 6502
- Simply Checking 4130
- Confidence Savings 0018

New account types (`Performance Savings`, etc.) are detected automatically — no code changes needed.

### Input
Folder of JPG/PNG images. **Filename must start with `YYYYMMDD`** (e.g., `20250101-Bank statement-1.jpg`) — this is how months are grouped. All pages for the same month share the same YYYYMMDD prefix.

### Output
**One Excel file per account**, written to `--output-dir` (defaults to same folder as input).

Filename: `capitalone_<account_type>_<last4>_transactions.xlsx`

| Tab | Contents |
|---|---|
| Summary | Month \| Txns \| Subtracted \| Added \| Net \| Opening Balance \| Closing Balance \| Calc Closing \| Gap |
| Master | All transactions with Month column |
| Jan 2025 … | Date \| Description \| Subtracted \| Added \| Balance \| Flag |

**Gap** = `Opening + Added − Subtracted − Closing Balance`. Should be $0 when all transactions are captured. Red if non-zero.

### Statement structure
- Page 1: Account Summary / Cashflow Summary (informational, not skipped — account header is at the bottom)
- Transaction pages: Date \| Description \| Category (ignored) \| Amount \| Balance
- Amount format: `- $88.29` (withdrawal) / `+ $2,400.00` (deposit) — sign explicit
- Fees Summary section after each account: skipped
- Opening Balance / Closing Balance rows: tracked for reconciliation, not added as transactions

### Date handling
- Format: `Jan 6`, `Jan 18` (abbreviated month + day, no year)
- Year inferred from filename prefix (`20250101` → 2025)
- Permissive regex handles OCR garbles: `Jans` (garbled `Jan 8`), `Jani` (garbled `Jan 11`)

### OCR strategy
PSM 6 vs PSM 3 per page; whichever finds more `Mon DD + signed amount` lines wins.

### Reconciliation
Opening Balance + Added − Subtracted = Calculated Closing. Compared against actual Closing Balance per account per month. Also: row-level balance walk with VERIFY flags.

### Performance (2025 full year)
- 268 transactions across 3 accounts, 12 months
- 35/36 account-months: Gap = $0.00
- 1 gap: Jun 2025 Simply Checking 6502 ($2,400 — OCR-missed deposit reversal)

---

## 3. Chase Business Statement Extractor (`extract_chase_txns.py`)

### Usage
```bash
python extract_chase_txns.py "path/to/images/folder"
python extract_chase_txns.py "path/to/images/folder" --output result.xlsx

# Subfolder mode — each subfolder becomes one tab:
python extract_chase_txns.py "path/to/root/folder"
```

### Input
Flat folder (all images = one tab) or subfolders (each subfolder = one monthly tab).

### Output
Excel with **Summary → per-month tabs**.

| Tab | Contents |
|---|---|
| Summary | Month \| Txns \| per-section totals \| Net |
| Per-month tab | Date \| Description \| Amount (signed) \| Section \| Source Page \| Flag |

### Statement structure
Section-based: transactions grouped under printed section headers.

| Section | Sign |
|---|---|
| Deposits and Additions | + |
| Checks Paid | − |
| ATM & Debit Card Withdrawals | − |
| Electronic Withdrawals | − |
| Other Withdrawals | − |
| Service Fees | − |

Sign determined by section, not by description keywords.

### Reconciliation
Per section: parsed total vs printed `Total <Section> $X.XX` line. BTP-1: removes phantom total row if it accounts for entire excess. Sentinel row inserted for genuine gaps.

---

## 4. Chase Credit Card Extractor (`extract_chase_cc_txns.py`)

### Usage
```bash
python extract_chase_cc_txns.py "path/to/images/folder"
```

### Statement structure
Detects `ACCOUNT ACTIVITY` section header. Transactions listed as `MM/DD description amount`.  
Reconciles against `TRANSACTIONS THIS CYCLE` printed total.

### Output
Excel (one tab per month if subfolders, otherwise single tab).

---

## 5. Chase Freedom Extractor (`extract_freedom_txns.py`)

### Usage
```bash
python extract_freedom_txns.py "path/to/screenshots/folder"
python extract_freedom_txns.py "path/to/screenshots/folder" --output result.csv
```

### Input
Mobile app screenshots (PNG/JPG) — not scanned statements.

### Two layout modes
- **List view** (`char*.png`): date header appears before each transaction group
- **Detail view** (`donations.png`): date appears after each transaction, followed by "Payment"

### Output
CSV: `date, description, amount, source_page`

---

## 6. Indian Bank Statement Extractor (`extract_india_bank_txns.py`)

### Usage
```bash
python extract_india_bank_txns.py file.pdf
python extract_india_bank_txns.py folder/          # processes all PDFs
python extract_india_bank_txns.py file.pdf --output result.xlsx
```

### Supported formats (auto-detected)

| Config key | Bank | Detection | Extraction |
|---|---|---|---|
| `statement_report` | HDFC Statement Report | Table header has "Withdrawal" + "Deposit" + "Closing Balance" | pdfplumber tables |
| `kotak_bank` | Kotak Bank | Page text has "TRANSACTION DATE" + "DEBIT/CREDIT" | pdfplumber text + regex |
| `hdfc_fd` | HDFC FD/Savings (scanned) | pdfplumber finds 0 text chars | PyMuPDF + Tesseract OCR |

### Adding a new bank
Add an entry to `india_bank_configs.yaml` — no code changes needed.

### Output
Excel with two sheets:
- **Transactions**: Date \| Description \| Amount (signed: credit positive, debit negative)
- **Reconciliation**: opening + sum = closing check; row-by-row balance continuity gaps

### Reconciliation logic
`opening + sum(signed_amounts) = closing`. For `statement_report`, true opening derived from last row balance − last row amount (PDF "Opening Balance" is off by one transaction). Row-by-row gap = `|prev_balance + curr_amount − curr_balance| > 0.02`.

### Dependencies
`pdfplumber`, `openpyxl`, `pyyaml`, `pymupdf` (fitz), `pytesseract`, `Pillow`

---

## 7. Interest & TDS Finder (`find_interest_tds.py`)

### Purpose
Scan any bank transaction file and extract Interest Income and Tax Deducted rows.

### Usage
```bash
python find_interest_tds.py transactions.xlsx
python find_interest_tds.py transactions.csv --locale india --threshold 0.55
python find_interest_tds.py transactions.xlsx --locale us --output summary.xlsx

# Claude Code skill:
/find-interest-tds transactions.xlsx
```

### Two-pass detection
1. **Keyword (regex)** — handles bank abbreviation codes: `Int.Pd`, `TDS`, `INT CR`
2. **Cosine similarity** (sentence-transformers `all-MiniLM-L6-v2`, local, no API) — handles natural language descriptions not caught by keywords

### Output
Excel: Interest Income sheet (blue) + Tax Deducted sheet (blue) + Near Miss — Review sheet (amber, omitted if empty).  
`Match` column shows `keyword` or `cosine (0.72)` per row — full audit trail.

### Configuration
`interest_tds_configs/india.yaml` and `us.yaml`. Add keywords, anchors, or column hints to the YAML — no code changes ever needed.

### Near-miss band
Rows scoring between `review_threshold` (0.35) and `threshold` (0.55) → amber sheet for human review.

### Adding a new locale
Copy any existing YAML to `interest_tds_configs/<locale>.yaml`, update contents, run with `--locale <locale>`.

### Dependencies
`sentence-transformers>=2.7.0`, `scikit-learn>=1.4.0`, `openpyxl`, `pandas`, `pyyaml`

---

## Common Dependencies

```
pytesseract==0.3.13          # OCR (image-based extractors)
Pillow==11.1.0                # image handling
openpyxl                      # Excel output (all scripts)
pdfplumber                    # PDF text extraction (Indian extractor)
pymupdf (fitz)                # PDF rendering for OCR (Indian extractor)
pyyaml                        # config loading (Indian extractor, Interest & TDS)
sentence-transformers>=2.7.0  # semantic matching (Interest & TDS only)
scikit-learn>=1.4.0           # cosine similarity (Interest & TDS only)
pandas                        # data processing (Interest & TDS only)
```

Tesseract OCR binary: `C:\Program Files\Tesseract-OCR\tesseract.exe`
