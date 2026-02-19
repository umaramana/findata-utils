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
  - Right-shift detection: Date pattern validation per row against header anchor
  - Shifts Part 2 values left to re-align with header
  - Anchors: Date Acquired + Cost column positions (hardcoded per broker, keyword fallback)
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

| | Fidelity | Charles Schwab | Robinhood | Merrill Lynch | Morgan Stanley | Betterment |
|---|---|---|---|---|---|---|
| **Status** | Complete | Needs test data | Needs test data | Complete | Complete | Complete |
| **File type** | Excel | Excel | Excel | Excel | Excel | CSV |
| **Date Acq col** | 2 | Auto-detect | 3 | 2 | 2 | 3 |
| **Cost col** | 5 | Auto-detect | 4 | 5 | 5 | 6 |
| **Optional cols** | Accrued Mkt Discount, Wash Sale | — | Wash Sale | Accrued Mkt Discount, Wash Sale | Accrued Mkt Discount, Wash Sale | Wash Sale |
| **Type (S/L)** | — | — | — | — | — | Yes (col 10) |
| **Fed Tax Withheld** | — | — | — | — | Yes (col 9) | Yes (col 9) |
| **QC** | Yes | Yes | Yes | Yes | Yes | Skipped (CSV) |

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

## Parking Lot
- **Subtotal aggregation per stock**: Roll up transactions per security for summary view
- **PDF Summary Page QC**: Compare page 1 totals against sum of processed transactions
- **Proceeds gap investigation (Merrill)**: 96 transactions extracted, total proceeds $43,898.49 vs expected $48,538.58 (~$4,640 gap, ~4 missing transactions still unaccounted for)
- **Type column for remaining brokers**: Fidelity, Schwab, Robinhood, Merrill, Morgan Stanley — enable when source data confirmed
- **New brokers queued**: Apex Clearing, JP Morgan (Excel/PDF24), pending test data
