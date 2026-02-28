# Stock Processor — Architecture & Broker Design Decisions

## Three Numeric Anchors Rule
```
[DateAcq] [DateSold] | Proceeds | Cost | [Accrued?] | [Wash Sale?] | Gain/Loss
                       ← always → ←      optional zone      → ← never empty →
```
- **Proceeds + Cost**: always present, always first 2 numerics after DateSold
- **Gain/Loss**: always present (NEVER empty for real transaction rows), always last numeric
- **Between Cost and Gain/Loss**: optional zone — Accrued Market Discount and/or Wash Sale Loss
- Gain/Loss position = `cost_col + len(optional_cols) + 1` (derivable from BROKER_CONFIG)

## Three Column Shift Problems

### Problem 1: Right Shift (QC Pass 1)
Part 1 (description area) consumes extra columns → all of Part 2 shifts right.
Detection: date found to the right of expected position.
Fix (in pdf_qc.py): shift Part 2 left to re-align with header.

### Problem 2: Empty Cell Collapse / Left Shift (QC Pass 2)
When optional cols are absent, Gain/Loss slides LEFT into optional positions.
Detection: Gain/Loss col is empty (Gain/Loss is NEVER empty, so this is conclusive).
Fix: scan backward from expected Gain/Loss position, find misplaced value, move it right to correct position.
Legacy implementation in fidelity.py `_fix_empty_cell_collapse()` — to be removed (QC Pass 2 handles universally).

### Problem 3: Optional Right Shift (PLANNED — QC Pass 3)
Optional columns (Accrued, Wash Sale) shift RIGHT past Gain/Loss while anchors stay in place.
Discovered in JP Morgan: options rows push Accrued/Wash from expected cols 9-10 to cols 13-14.
Detection: optional zone empty + summary page totals show non-zero optionals expected.
Fix: scan right of Gain/Loss, pull numeric values back into optional zone.
**Not yet built** — depends on Summary Page QC feature. Current workaround: broker-level fallback in jpmorgan.py.
See [stock_processor_qc.md](stock_processor_qc.md) for full design discussion and per-broker analysis.

## Per-Broker Financial Column Reading Strategy

| Broker | Reading Strategy | Collapse Handled By |
|---|---|---|
| Fidelity | By column NAME from detected header | `_fix_empty_cell_collapse()` in fidelity.py |
| Merrill | Dynamic: `_find_date_columns()` per row → `fin_start = ds_idx + 1` | Natural — financials anchored to actual DateSold position |
| Morgan Stanley | Fixed index (col 4=Proceeds, col 5=Cost, col 6=Accrued, col 7=Wash, col 9=FedTax) | QC corrects right-shifts; fixed index then works |
| Schwab | Relative to date position (`fin_start = date_col + offset`) | Natural — anchored to actual date position |
| Betterment | Fixed index (CSV, no PDF24 artifacts) | N/A |
| Apex Clearing | Fixed index (col 0=DateSold, 2=Proceeds, 4=DateAcq, 5=Cost, 6=Wash, 7=G/L) | QC Pass 2 handles left-shift |
| JP Morgan | Fixed index (col 5=DateAcq, 7=Proceeds, 8=Cost, 9=Accrued, 10=Wash, 11=G/L) | Broker-level fallback for cols 13-14 (pending Pass 3) |

## Date Pattern Usage Across Brokers
- **QC**: date at expected col = aligned; date found further right = right-shifted → shift Part 2 left
- **Merrill** `_find_date_columns()`: scans every row for date pattern to find DA/DS dynamically
- **Morgan Stanley** `_classify_row()`: fixed-position date check (cols 2 & 3) for row type classification only — not for financial col location
- **Fidelity**: dates used only by QC, not by broker parser for financial col location
- **Schwab** `_standardize_columns()`: scans first row for date → reads financials relative to it

## Row Classification by Broker
- **Fidelity**: description row = text ONLY in col 0, all others empty; transaction = has data in other cols
- **Merrill**: `_classify_row()` — skip/merged/description/continuation/transaction. Merged rows have `\n`-separated values (multiple txns per cell). Date + financial data = transaction.
- **Morgan Stanley**: skip (1 non-empty cell or header keywords) | stock_name (col 0 + CUSIP keyword) | transaction (date at col 2 & 3, numeric at col 4)
- **Schwab**: all rows with any date value = potential transaction; paired rows (Row1=primary+proceeds, Row2=CUSIP+DateSold)
- **Apex Clearing**: alternating desc/data rows. Parent row = description in col 0. Child row = DateSold in col 0, financials in cols 1-7.
- **JP Morgan**: skip (header keywords, "Column1" Excel auto-headers, grand total) | transaction (dates in cols 5+6) | description (text in cols 0-3, no dates) | subtotal ("Subtotals" in col 3). Description-only rows append to previous tx. Company name TX rows (no PUT/CALL prefix) append to previous option TX.

## QC — Merrill Notes
- QC runs for Merrill for Part 1 right-shifts (confirmed cases: Sheets 3, 6)
- Merrill does NOT need QC for empty cell collapse — dynamic date-finding naturally handles it
- Earlier confusion: QC was briefly moving Gain/Loss values for Merrill; resolution was that Merrill handles collapse at broker level, QC only for right-shifts

## BROKER_CONFIG in pdf_qc.py
- Fidelity: date_acq_col=2, cost_col=5, optional_cols=['Accrued', 'Wash Sale'] → gain_loss_col=8
- Merrill: date_acq_col=2, cost_col=5, optional_cols=['Accrued', 'Wash Sale'] → gain_loss_col=8
- Morgan Stanley: date_acq_col=2, cost_col=5, optional_cols=['Accrued', 'Wash Sale'] → gain_loss_col=8, fed_tax_col=9
- Robinhood: date_acq_col=3, cost_col=4, optional_cols=['Wash Sale'] → gain_loss_col=6
- Apex Clearing: date_acq_col=4, cost_col=5, optional_cols=['Accrued/Wash merged'] → gain_loss_col=7
- JP Morgan: date_acq_col=5, cost_col=8, optional_cols=['Accrued', 'Wash Sale'] → gain_loss_col=11
- Schwab: date_acq_col=None (auto-detect), cost_col=None

## Key Regression Risk
- Fidelity.py was modified during Merrill Lynch session (13:25) — introduced collapse regression
- Test data in `testdata/passedtestcases/` should be run after every change
- Regression: gain/loss values appearing in Accrued or Wash Sale output columns
