# Stock Transaction Processor — Requirements Summary

## General
- **Purpose**: Convert broker 1099-B files (Excel via PDF24, or native CSV) to Drake tax software import format
- **Output**: 15-column Drake format
  - Populated: Desc, Date Acquired, Date Sold, Proceeds, Cost, Accrued Discount, Wash Sale Loss
  - Conditionally populated: Type (S/L — populated when broker provides term type data)
  - Empty: TSJ, F, State, City, Form 8949 Check Box, Ordinary, AMT Cost Basis
- **UI**: Streamlit web app — broker selection, file upload (CSV or Excel), QC report, preview, download
- **File types**: `.xlsx`, `.xls`, `.csv` accepted for all brokers
- **QC Module** (`pdf_qc.py`): Auto-detects and corrects column misalignment from PDF24 conversion
  - **Pass 1 — Right-shift detection** (existing): Date pattern validation per row against header anchor. If date found right of expected position, shifts Part 2 values left to re-align.
  - **Pass 2 — Left-shift / collapse reconciliation** (new): Header-vs-data position check for each anchor column (Date Acquired, Gain/Loss, Fed Tax). If anchor is empty at expected position but found one position left, shifts it right. Universal across all Excel brokers.
  - Anchors: Date Acquired, Cost, Gain/Loss, Fed Tax (optional) — positions per broker in `BROKER_CONFIG`
  - Header row detection: highest keyword match count in first 10 rows
  - **Skipped automatically for CSV brokers** (no PDF24 artifacts possible)
- **Broker Profiler** (`broker_profiler.py`): Standalone analysis tool for new broker files
  - Run: `python broker_profiler.py <file.xlsx|file.csv> [sheet_name]`
  - Deep analysis: `python broker_profiler.py <file> --broker <key>` (e.g., `--broker jpmorgan`)
  - Outputs: column type profiles, row type distribution, detected anchors, similarity ranking vs existing brokers
  - Deep analysis adds: optional zone analysis, right-of-Gain/Loss scan, shift pattern detection, financial totals

## CSV vs Excel Brokers
- **Convention**: CSV brokers use `csv_` prefix in their broker key (e.g., `csv_betterment`)
- App detects `csv_` prefix → skips QC, shows "CSV file detected" info message
- No manual configuration needed — prefix is self-documenting

## Type Column (S/L)
- Drake expects `S` (short-term) or `L` (long-term) in the Type column
- `_normalize_type()` in `drake_mapper.py` handles any broker's source format:
  - `Long-term`, `LONG`, `long` → `L`
  - `Short-term`, `SHORT`, `short` → `S`
  - `L`, `S` → pass through
- To enable for a broker: add `'Type': 'Type'` to its entry in `BROKER_COLUMN_MAPPINGS`
- Currently populated: Betterment

## Broker-Specific

| | Fidelity | Charles Schwab | Robinhood | Merrill Lynch | Morgan Stanley | Betterment | Apex Clearing | JP Morgan |
|---|---|---|---|---|---|---|---|---|
| **Status** | Complete | Complete | Complete | Complete | Complete | Complete | Complete | Complete |
| **File type** | Excel | Excel | Excel | Excel | Excel | CSV | Excel | Excel (via Excel PDF import) |
| **Date Acq col** | 2 | 4 (paired row) | 3 | 2 | 2 | 3 | 4 (falls back to 3 if shifted) | 5 |
| **Cost col** | 5 | 6 | 4 | 5 | 5 | 6 | 5 | 8 |
| **Gain/Loss col** | 8 | 8 | 6 | 8 | 8 | 7 | 7 | 11 |
| **Optional cols** | Accrued Mkt Discount, Wash Sale | Accrued/Wash merged (col 7) | Wash Sale | Accrued Mkt Discount, Wash Sale | Accrued Mkt Discount, Wash Sale | Wash Sale | 1f/1g merged (col 6) | Accrued Mkt Discount, Wash Sale |
| **Type (S/L)** | — | — | — | — | — | Yes (col 10) | — | — |
| **Fed Tax Withheld** | — | — | — | — | Yes (col 9) | Yes (col 9) | — | — |
| **QC** | Yes | Yes | Yes | Yes | Yes | Skipped (CSV) | Yes | Yes |
| **Left-shift handling** | Gain/Loss collapse (QC Pass 2) | Right-shift (QC Pass 1, 10-col sheets) | — | Dynamic date finding | Gain/Loss collapse (QC Pass 2) | N/A | DateAcq col4→3 (QC Pass 2) | Optional right-shift (broker-level fallback, pending Pass 3) |

## Merrill-Specific Row Patterns
1. **Fully merged multi-tx**: All transactions in one row, `\n`-separated (e.g., AMAZON with 7 txns)
2. **Merged single-tx**: Description + first transaction merged in one row
3. **Description-only**: Stock name row, no financial data
4. **Continuation**: Multi-line description spanning rows (e.g., "CHARTER COMMUNICATIONS" + "INC SHS CL A")
5. **Transaction**: Standard row with dates and financials

## Merrill QC Issues (resolved)
- PDF24 splits wash sale values (e.g., "15.38(W)") into extra columns — Sheet3 has extra blank col in Part 2
- PDF24 adds blank columns in Part 1 on some sheets (Sheet6) — shifts Part 2 right
- NVIDIA merged row has Part 1 consuming extra column — per-row date validation corrects it

## Morgan Stanley Notes
- Description is on stock-name rows (col 0), empty on transaction rows — forward-filled including across sheet boundaries
- Col 9 = Fed Tax Withheld due to PDF24 merging col 8/9 header — expected artifact, not an error
- Column header rows repeat mid-sheet — detected (2+ header keywords) and skipped
- Row types: skip | stock_name | transaction | section header (single populated cell)

## Betterment Notes
- Native CSV export — no PDF24 conversion needed
- Row 0 is the clean header row; all remaining rows are transactions (no stock-name rows, subtotals, or section headers)
- Gain/Loss (col 7) appears BEFORE Wash Sale (col 8) — opposite of other brokers; safe since columns are read by fixed index
- Type of Gain(Loss) (col 10): `Long-term` / `Short-term` → normalized to `L` / `S` in Drake output

## Apex Clearing Notes
- PDF24-converted Excel, 2 sheets in test file (pages 3-4 of 7)
- **Row pairing**: Col 0 carries 1a (description on parent row) and 1c (date sold on child row) — similar to Fidelity's parent-child but col 0 is overloaded with different data types per row type
- **Column layout (data rows)**: Col 0=DateSold(1c), Col 1=Qty, Col 2=Proceeds(1d), Col 3=(no 1x header, artifact), Col 4=DateAcq(1b), Col 5=Cost(1e), Col 6=Accrued/WashSale(1f/1g merged), Col 7=Gain/Loss, Col 8=Additional Notes (Sheet1 only, Sheet2 has 8 cols)
- **Date format**: YYYY-MM-DD (unique among brokers — needs `_format_date()` pattern in drake_mapper.py)
- **Col 6 merged 1f/1g**: Header indicates "(M)" for Accrued Market Discount and "(D)" for Wash Sale Loss Disallowed as markers. Test data has 0 values only. Placeholder `_parse_accrued_wash_sale()` function — expand when non-zero test data available
- **Left-shift**: DateAcq expected at col 4 (per 1b header) but appears at col 3 in data. Handled by universal QC Pass 2.
- **Multi-row header**: Rows 7-10 span 4 rows with partial text per row; 1x IRS codes (1a-1g) identify real columns
- **Totals row**: End of last sheet ("Totals:" in col 0) — filter out
- **Expected totals** (from test file): 10 transactions, Proceeds=$3,192.70, Cost=$5,189.38

## QC Pass 2 — Universal Left-Shift Reconciliation
- **Purpose**: After Pass 1 (right-shift) corrects Part 2 being pushed right, Pass 2 corrects individual anchor columns that shifted left (empty cell collapse or PDF24 artifact columns)
- **Approach**: For each anchor (Date Acquired, Gain/Loss, Fed Tax), check if value is at expected position. If empty, check one position left. If found, move right.
- **Replaces**: Fidelity's broker-level `_fix_empty_cell_collapse()` (to be removed once regression-proven)
- **Transaction row guard**: Only check rows where Cost or Proceeds at expected position is non-empty (avoids false positives on description/header/footer rows)
- **BROKER_CONFIG additions**: `gain_loss_col_idx` and optional `fed_tax_col_idx` added per broker

## Transaction Tagger — Sprint 1

### Purpose
Multi-pass transaction tagger for tax preparers. Tags bank/CC transactions to expense heads (COGS, Supplies, etc.) using Claude API + preparer review. New page in RASRICH Streamlit app.

### Input
- Excel or CSV (output of the Tab Collator is the primary input — single Master sheet)
- Required column: Description / Vendor name (preparer maps in Step 2)
- Optional column: Amount (included in Claude context for disambiguation)
- File may optionally contain a "Lookup" tab (same columns as `rasrich_tag_lists.csv`: `entity_type, tag, form_reference`) with a client-specific reduced tag list

### Tag List (`docs/rasrich_tag_lists.csv`)
- 3 entity types: `Sole Prop / SMLLC`, `S-Corp`, `Partnership / MMLLC`
- Each has ~20-25 tags. "Personal - Not Deductible" and "Review with Client" always included.
- Client tag list = filter generic list by entity_type. If file has "Lookup" tab → use that instead (same column format, subset of generic list).

### Architecture — Pass Sequence
| Pass | What | Sprint | API call? |
|---|---|---|---|
| Setup | Load entity type → tag list | 1 | No |
| Pass 1a | Exact match vs `{client_id}_lookup.csv` | **2** (lookup created in Sprint 1, consumed in Sprint 2) | No |
| Pass 1c | Claude Haiku semantic + persona (deduped, batched 30/call) | 1 | Yes |
| Pass 1d | Low-confidence rows collected for preparer review | 1 | No |
| Pass 2 | Preparer tags unique flagged names; apply back to all matching rows | 1 | No |
| Pass 3 | Unresolved → "Review with Client" | 1 | No |
| Output | Tagged file + RwC list + updated lookup CSV | 1 | No |

### Claude API Design (Pass 1c)
- Model: `claude-haiku-4-5-20251001`
- System prompt includes: full tag list (name only), client persona (primary activity, secondary activity, entity type), instruction to return JSON only
- Each item in batch: `{ "description": "...", "amount": ... }` (amount for disambiguation)
- Required response format per item: `{ "tag": "...", "confidence": 0.0–1.0, "reason": "..." }`
- Claude must select only from provided tag list. If unsure → low confidence score, not a guess.
- Batch size: 30 unique descriptions per API call
- Dedup before API: send unique descriptions only, map results back to all matching rows

### Confidence Threshold
- Configurable slider in Step 1 UI, range 0–100%, default 75%
- At or above threshold → auto-tagged (Pass 1c result applied directly)
- Below threshold → flagged for preparer review (Pass 2)
- Wrong auto-tags are worse than over-flagging — default stays conservative

### Lookup Table (`stock_processor/lookups/{client_id}_lookup.csv`)
- Columns: `vendor_name, tag, source, date_tagged`
- `source`: `"auto"` (Claude-assigned) or `"preparer"` (manually assigned)
- Folder `stock_processor/lookups/` created automatically if absent
- Used in Pass 1a for exact vendor name match (no API call)
- Updated at end of each run with new auto-tagged + preparer-tagged entries
- Per-client, not firm-wide (Sprint 1)

### UI Flow (5 Steps, Streamlit session_state)
| Step | Name | Contents |
|---|---|---|
| 1 | Setup | Client ID, entity type, primary activity, secondary activity, confidence threshold |
| 2 | Upload | File upload, column mapping (Description col, Amount col optional) |
| 3 | Run Pass 1 | Auto-tag button, progress bar, summary counts (auto / flagged / skipped) |
| 4 | Preparer Review | Unique flagged names, tag dropdown per name, "Review with Client" option |
| 5 | Output | Download tagged file, RwC list, lookup table save confirmation |

### Output File
- Original file + added columns: `Tag`, `Tag Source` (auto/preparer/rwc), `Confidence`, `Reason`
- Confidence and Reason populated for auto-tagged rows only (blank for preparer/rwc rows)

### Persona Complexity (Haiku)
- Persona context in system prompt: entity type + primary activity + secondary activity
- Haiku should return low confidence (not guess) when persona context creates ambiguity
- Example: Home Depot for a plumber → Supplies or COGS? Return low confidence, reason explains the ambiguity → surfaces the rule to the preparer
- Additional rules expected to emerge during real client runs — treat low confidence + reason as the mechanism for surfacing them

### Integration Note
- Immediately follows Tab Collator in the preparer workflow
- New page registered in `rasrich_tools.py` as `tagger_page.py`
- Follow existing conventions: sidebar header via `_ui_helpers.py`, same layout patterns as `excel_utilities_page.py`

### Sprint 2+ (Out of Scope Now)
- Pass 1a: exact lookup match (lookup CSV created in Sprint 1, Pass 1a consumption deferred to Sprint 2)
- Google Places API / vendor geo-enrichment (Pass 1b)
- Multi-year lookup, firm-wide lookup option

## Parking Lot
- **Subtotal aggregation per stock**: Roll up transactions per security for summary view
- **Summary Page QC + QC Pass 3**: Scan summary/totals rows for expected totals (Proceeds, Cost, Accrued, Wash Sale). Compare against processed output. If optional totals mismatch → trigger Pass 3 (scan right of Gain/Loss, pull shifted optional values back). This replaces broker-level shift workarounds (e.g., jpmorgan.py cols 13-14 fallback). Sequence: Summary scan → Pass 1+2 → broker processing → total comparison → Pass 3 if needed. See `stock_processor_qc.md` for full per-broker analysis of what's right of Gain/Loss and false-positive risks.
- **Proceeds gap investigation (Merrill)**: 96 transactions extracted, total proceeds $43,898.49 vs expected $48,538.58 (~$4,640 gap, ~4 missing transactions still unaccounted for)
- **Type column for remaining brokers**: Fidelity, Schwab, Robinhood, Merrill, Morgan Stanley — enable when source data confirmed
- **Apex Col 6 marker parsing**: Expand `_parse_accrued_wash_sale()` when non-zero 1f/1g test data available
- **Remove Fidelity `_fix_empty_cell_collapse()`**: After QC Pass 2 proven via regression, remove broker-level collapse handling. Deferred from JP Morgan session — do alongside Pass 3 work.
- **QC `_verify_or_search_col` search cleanup**: Search fallback disabled (trusts config). Was returning wrong anchors for Morgan Stanley, JP Morgan, and Schwab. Review with additional test data and remove if confirmed dead code.

## Charles Schwab Notes
- **Status**: Complete. Regression baseline + client file verified.
- **Paired row structure**: Header and data rows come in pairs. Row 1 (primary) has description + financials. Row 2 (secondary) has CUSIP + Date Sold.
- **Paired header**: Row 7 defines col 3 (Date Acquired code) and col 4 (Date Acquired date). Row 8 defines col 4 (Date Sold), col 5 (Proceeds), col 6 (Cost), col 7 (Wash Sale), col 8 (Gain/Loss).
- **Col 4 dual purpose**: Carries Date Acquired in primary row, Date Sold in secondary row.
- **Col 3**: SC/BC option codes (Sold to Close / Bought to Close). Not used in Drake output — description carries this info.
- **Layout (9-col)**: Col 0=Description/CUSIP, 1=Strike, 2=Option expiry, 3=SC/BC code, 4=Date Acquired (primary) / Date Sold (secondary), 5=Proceeds (sometimes merged with Cost), 6=Cost, 7=Accrued/Wash (merged), 8=Gain/Loss
- **10-col variant**: Some sheets have extra description columns (CLASS/equity type in cols 2-4), shifting Part 2 right by 1. Handled by QC Pass 1 right-shift detection.
- **Merged Proceeds/Cost**: Col 5 sometimes has `"$ X $ Y"` (both values) or `"$ X $"` (trailing $, Cost in col 6). Split logic in `_split_proceeds_cost()`.
- **Merged Accrued/Wash**: Uses shared `parse_accrued_wash_sale()` from `utils.py`
- **VARIOUS**: Valid Date Acquired value for multi-lot positions. Recognized by QC `_has_date()` for right-shift detection.
- **Test file**: 9-col, 4 sheets, 14 options transactions. Client file: 5 sheets (Sheet1=10-col, Sheets 2-5=9-col), 21 stock transactions.
- **Test totals**: Proceeds=$5,174.63, Cost=$4,192.20. Client totals: Proceeds=$139,268.68, Cost=$128,019.96.

## JP Morgan Notes
- **Source**: PDF converted via Excel's built-in PDF import (not PDF24). Single sheet `Append1`.
- **Layout**: Cols 0-3 = description/CUSIP/option info, col 4 = qty, 5 = DateAcq, 6 = DateSold, 7 = Proceeds, 8 = Cost, 9 = Accrued, 10 = Wash Sale, 11 = Gain/Loss, 12 = Additional Info
- **Options row shift**: 91/518 rows (PUT/CALL with expiry/strike in cols 2-3) have Accrued/Wash at cols 13-14 instead of 9-10. Currently broker-level fallback in jpmorgan.py. To be replaced by QC Pass 3.
- **Description**: Transaction rows: cols 0+1. Description-only rows: cols 0-3 (append to previous tx). Empty-description rows inherit `current_description`.
- **Repeating headers**: CUSIP / (Box 1a) markers repeat ~34 times — skipped via keyword matching.
- **Test totals**: 518 txns, Proceeds=$286,497.41, Cost=$286,245.52, Wash Sale=$2,818.89
