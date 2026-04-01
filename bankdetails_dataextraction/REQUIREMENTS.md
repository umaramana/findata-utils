# Bank Details Extraction — Requirements

---

## Tool: Interest & TDS Finder (`find_interest_tds`)

### Purpose
Scan a bank transaction file (Excel or CSV) and extract two categories of transactions:
- **Interest Income** — interest credited to the account
- **Tax Deducted** — TDS / tax withheld at source

Output is an Excel file with one sheet per category plus an optional amber-coloured **Near Miss — Review** sheet for human inspection.

---

### Architecture: Two Layers

This tool is deliberately split into two layers:

| Layer | File | Purpose |
|---|---|---|
| Core module | `find_interest_tds.py` | Importable Python function — reusable by Streamlit, pipelines, other scripts |
| Claude Code skill | `.claude/commands/find-interest-tds.md` | Slash command that invokes the script and summarises results in the conversation |

The skill is the first custom Claude Code slash command in this project. It wraps the CLI entry point — it does not contain logic itself.

---

### Invoking the Skill

After restarting Claude Code, type directly in the prompt:

```
/find-interest-tds path/to/transactions.xlsx
/find-interest-tds path/to/transactions.csv --locale us
/find-interest-tds path/to/transactions.xlsx --threshold 0.6 --output results.xlsx
```

Claude will run the script, then report: rows found per category, totals, near-miss count, and output path.

---

### CLI (direct)

```bash
cd bankdetails_dataextraction
python find_interest_tds.py transactions.xlsx
python find_interest_tds.py transactions.csv --locale india --threshold 0.55
python find_interest_tds.py transactions.xlsx --locale us --output summary.xlsx
```

---

### Python import

```python
from find_interest_tds import find_transactions

result = find_transactions("transactions.xlsx", locale="india")
# result keys: "interest_income", "tax_deducted", "_review"
# Each value is a DataFrame with columns: Date | Description | Debit/Credit | Match
```

---

### Input

| Format | Notes |
|---|---|
| `.xlsx` / `.xls` | Reads first sheet |
| `.csv` | Standard comma-separated |

**Required columns** (names are auto-detected — see `column_hints` in YAML):
- Date
- Description / Narration / Particulars (any variant)
- Debit/Credit / Amount / Withdrawal/Deposit (any variant)

Column detection: exact match first, then substring match against `column_hints` list in the locale YAML. If detection fails, the error message lists what was found and what was expected — fix by adding a hint to the YAML.

---

### Two-Pass Detection

#### Pass 1 — Keyword (regex, case-insensitive, whole-word)
Each keyword in the YAML becomes `\bKEYWORD\b`. Handles bank-specific abbreviation codes that semantic models don't understand well (e.g., `Int.Pd`, `TDS`, `INT CR`).

#### Pass 2 — Cosine Similarity (semantic)
Runs only on rows not matched by Pass 1. Uses `sentence-transformers` model `all-MiniLM-L6-v2` (local, ~80MB, cached after first download — no API calls, no tokens consumed). Each unmatched description is compared against all anchor phrases; best score wins if ≥ threshold.

Handles natural-language descriptions like `"Quarterly interest on savings balance"` that keyword matching would miss.

---

### Near-Miss Band

Rows that scored **between `review_threshold` and `threshold`** in Pass 2 go into a separate **"Near Miss — Review"** sheet (amber header). These were not confident enough to classify automatically but are worth a human look.

Columns: Date | Description | Debit/Credit | Nearest Category | Score

**Workflow:** If a near-miss row is clearly correct → promote its pattern to a keyword in the YAML → next run it hits Pass 1 instead.

---

### Configuration (YAML)

One YAML file per locale in `interest_tds_configs/`:

```
interest_tds_configs/
  india.yaml    ← active
  us.yaml       ← active
```

**YAML structure:**

```yaml
locale: india
threshold: 0.55           # cosine match cutoff
review_threshold: 0.35    # near-miss band lower bound

categories:
  interest_income:
    display_name: "Interest Income"
    keywords: [INT CR, Int.Pd, TDS ON INT, ...]
    anchors:
      - "interest received on savings account"
      - ...
  tax_deducted:
    display_name: "Tax Deducted"
    keywords: [TDS, TAX DEDUCTED AT SOURCE, ...]
    anchors:
      - "tax deducted at source"
      - ...

column_hints:
  date: [Date, VALUE DATE, Txn Date, ...]
  description: [Description, Narration, Particulars, ...]
  amount: [Debit/Credit, Amount, Withdrawal/Deposit, ...]
```

**Tuning** — no code changes ever needed:
- New abbreviation found → add to `keywords`
- New anchor phrase helps semantic matching → add to `anchors`
- New bank uses different column names → add to `column_hints`
- Threshold too strict/loose → change `threshold` in YAML (or override via `--threshold` CLI flag)

---

### Output

File: `<input_name>_interest_tds.xlsx`

| Sheet | Header colour | Contains |
|---|---|---|
| Interest Income | Blue | Matched interest rows + Total row |
| Tax Deducted | Blue | Matched TDS rows + Total row |
| Near Miss — Review | Amber | Rows in review band (omitted if empty) |

Each matched row has a `Match` column: `keyword` or `cosine (0.72)` — audit trail showing how it was classified.

Signs are preserved as-is from the source file (credits positive, debits negative).

---

### Adding a New Locale

1. Copy `interest_tds_configs/india.yaml` → `interest_tds_configs/<locale>.yaml`
2. Update keywords, anchors, and column_hints for the new locale
3. Run with `--locale <locale>`

No code changes required.

---

### Dependencies

```
sentence-transformers>=2.7.0   # semantic model
scikit-learn>=1.4.0            # cosine similarity
openpyxl>=3.1.2                # Excel output
pandas                         # data processing
pyyaml                         # config loading
```

Install: `pip install -r requirements.txt`

First run downloads `all-MiniLM-L6-v2` (~80MB) and caches it locally. All subsequent runs are fully offline.

---

### Known Limitations / Parking Lot

See `stock_processor/PARKING_LOT.md` → **Interest & TDS Finder** section.
