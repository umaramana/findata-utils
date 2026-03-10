# Parking Lot - Future Features

## Subtotal Aggregation per Stock
- Instead of processing all individual transactions for a stock, use the broker's subtotal row for that stock
- Could reduce processing errors and simplify output (e.g., 10 transactions → 1 subtotal row)
- Challenge: each broker has a different format for subtotal rows
- Needs broker-specific detection logic (Schwab, Fidelity, Robinhood)

## PDF vs Excel QC (Quality Check & Auto-Correct) — IMPLEMENTED (Step 2B)
Implemented in `pdf_qc.py` and `app.py`. PDF page 1 is a summary, page 2+ are data pages.
PDF page N maps to Excel sheet N-2 (page 2 → sheet 0).

## PDF Summary Page QC (Page 1)
- PDF page 1 contains a summary/totals page
- Future feature: compare summary totals against the sum of all processed transactions
- Could catch errors that per-page QC misses (e.g., missing pages, double-counted rows)

## QC `_verify_or_search_col` — Review and Cleanup
- The keyword search fallback in `_verify_or_search_col` (pdf_qc.py) was disabled — now trusts BROKER_CONFIG when header verify fails
- Search was unreliable: returned wrong columns for Morgan Stanley (Cost=col 0), JP Morgan (DA=col 17, Cost=col 20), Schwab (DA=col 5 on 10-col sheets)
- All three brokers had 0 QC fixes with wrong anchors — broker modules handle positions independently
- **Action**: Review with additional test data or documentation to confirm search is dead code, then remove entirely
