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
  - Outputs: column type profiles, row type distribution, detected anchors, similarity ranking vs existing brokers

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

| | Fidelity | Charles Schwab | Robinhood | Merrill Lynch | Morgan Stanley | Betterment | Apex Clearing |
|---|---|---|---|---|---|---|---|
| **Status** | Complete | Needs test data | Needs test data | Complete | Complete | Complete | In Progress |
| **File type** | Excel | Excel | Excel | Excel | Excel | CSV | Excel |
| **Date Acq col** | 2 | Auto-detect | 3 | 2 | 2 | 3 | 4 (falls back to 3 if shifted) |
| **Cost col** | 5 | Auto-detect | 4 | 5 | 5 | 6 | 5 |
| **Gain/Loss col** | 8 | — | 6 | 8 | 8 | 7 | 7 |
| **Optional cols** | Accrued Mkt Discount, Wash Sale | — | Wash Sale | Accrued Mkt Discount, Wash Sale | Accrued Mkt Discount, Wash Sale | Wash Sale | 1f/1g merged (col 6) |
| **Type (S/L)** | — | — | — | — | — | Yes (col 10) | — |
| **Fed Tax Withheld** | — | — | — | — | Yes (col 9) | Yes (col 9) | — |
| **QC** | Yes | Yes | Yes | Yes | Yes | Skipped (CSV) | Yes |
| **Left-shift handling** | Gain/Loss collapse (QC Pass 2) | — | — | Dynamic date finding | Gain/Loss collapse (QC Pass 2) | N/A | DateAcq col4→3 (QC Pass 2) |

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

## Parking Lot
- **Subtotal aggregation per stock**: Roll up transactions per security for summary view
- **PDF Summary Page QC**: Compare page 1 totals against sum of processed transactions
- **Proceeds gap investigation (Merrill)**: 96 transactions extracted, total proceeds $43,898.49 vs expected $48,538.58 (~$4,640 gap, ~4 missing transactions still unaccounted for)
- **Type column for remaining brokers**: Fidelity, Schwab, Robinhood, Merrill, Morgan Stanley — enable when source data confirmed
- **Apex Col 6 marker parsing**: Expand `_parse_accrued_wash_sale()` when non-zero 1f/1g test data available
- **Remove Fidelity `_fix_empty_cell_collapse()`**: After QC Pass 2 proven via regression, remove broker-level collapse handling
- **New brokers queued**: JP Morgan (Excel/PDF24), pending test data
