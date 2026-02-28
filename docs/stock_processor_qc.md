# Stock Processor QC — Detailed Notes

## pdf_qc.py Architecture
- **Universal module** — works for all brokers, not broker-specific
- **Header row as anchor**: Find header row via highest keyword match count (not first >= 2, to avoid false positives like "PROCEEDS FROM BROKER & BARTER EXCHANGE TRANSACTIONS")
- **Two anchors from header**: Date Acquired column + Cost column (hardcoded per broker config, keyword fallback)
- **Per-row correction**: Validate date pattern at expected Date Acquired position. If shifted right, shift Part 2 left.

## Column Structure (all brokers)
- **Part 1**: Description — merged header spanning 2+ columns
- **Part 2**: Date Acquired | Date Sold | Proceeds | Cost | [optionals] | Gain/Loss
- Extra blank columns can appear in **either** part due to PDF24 artifacts
- Part 1 extras shift all of Part 2 right; Part 2 extras only affect post-Cost zone

## Key Lessons Learned

### Gain/Loss as a "never empty" signal (revised understanding)
- Gain/Loss is NOT used in Drake output
- Gain/Loss is ALWAYS the last financial column and is NEVER empty for real transaction rows
- This makes it a detection signal: if Gain/Loss col is empty → empty cell collapse detected
- Date Acquired is the anchor for RIGHT-shift detection; Gain/Loss emptiness is the anchor for COLLAPSE detection
- Gain/Loss position is derivable: `cost_col + len(optional_cols) + 1` (from BROKER_CONFIG)

### PDF24 artifacts that cause column shifts
1. **Wash sale split**: "15.38(W)" → "15.38" in wash sale col + "(W)" in new blank col (Part 2 extra)
2. **Blank header column**: PDF24 adds empty column in Part 1 on some pages
3. **Per-row variation**: Some rows (e.g., NVIDIA merged) have Part 1 consuming extra cols while other rows on the same sheet don't

### Header row detection pitfall
- Keywords like 'action' match "TRANSACTIONS", '1a' matches "1545" — substring false positives
- Fix: pick row with MOST keyword matches, not first row with >= 2

### pandas column count padding
- `pd.read_excel` may pad sheets to match max column count in workbook
- Don't rely on `len(df.columns)` to determine actual data width per sheet

## QC Pass 3 — Optional Right-Shift (PLANNED, not yet built)

### Problem
Optional columns (Accrued, Wash Sale) shift RIGHT past Gain/Loss. Discovered in JP Morgan where options rows push Accrued/Wash from cols 9-10 to cols 13-14, while all anchor columns (dates, proceeds, cost, gain/loss) stay in place.

### Current workaround
Fallback in `jpmorgan.py`: if cols 9-10 empty, check cols 13-14. Works but is broker-specific.

### Planned general solution
Trigger Pass 3 using **Summary Page totals** (parking lot feature):
1. Scan summary/totals rows for expected Accrued and Wash Sale totals
2. Run Pass 1 + 2 → process broker data → compute output totals
3. If optional totals don't match summary → run Pass 3 to scan right of Gain/Loss and pull values back

### Why not just scan right unconditionally?
Analysis of all brokers revealed risks:
- **Morgan Stanley**: Fed Tax Withheld (numeric) sits at col 9, right after Gain/Loss at col 8. If optionals were empty, unconditional scan would grab Fed Tax and misplace it.
- **Fidelity/Apex**: Have genuinely empty (NaN) optional columns on some rows — scan would trigger but find nothing (harmless no-op, but unnecessary).
- **Robinhood**: Has text ("Sale") right of Gain/Loss — would need numeric-only filter.

### Data analysis: what's right of Gain/Loss per broker
| Broker | After Gain/Loss | Content | Would Pass 3 false-trigger? |
|---|---|---|---|
| Fidelity | Cols 9-10 | All empty | No harm (finds nothing) but triggers on NaN optional rows |
| Robinhood | Col 7 | Text ("Sale") | No if numeric-only filter |
| Merrill | — | No cols exist | No |
| Morgan Stanley | Col 9 | **Fed Tax (numeric, 100% populated)** | **YES — would grab Fed Tax** |
| Apex Clearing | Col 8 | All empty | No harm (finds nothing) but triggers on NaN optional rows |
| JP Morgan | Cols 13-14 | Shifted Accrued/Wash (91 rows) | Correct fix |

### Data analysis: empty optionals behavior per broker
| Broker | When no value in optionals | Format |
|---|---|---|
| Fidelity | **NaN** (truly empty) | Pass 3 would trigger |
| Robinhood | `'...'` placeholder | Would NOT trigger |
| Merrill | `' 0.00'` (space + zero) | Would NOT trigger |
| Morgan Stanley | `'0'` (bare zero) | Would NOT trigger |
| Apex Clearing | **Mixed: NaN and `'0'`** | Would trigger on NaN rows |
| JP Morgan | **Mixed: NaN and `'$0.00'`** | Would trigger on NaN rows |

### Design decision
Use Summary Page totals as the trigger (Option C from design discussion). This:
- Eliminates false positives entirely (only scan when we KNOW values are missing)
- Delivers the Summary Page QC parking lot feature
- Provides end-to-end validation (output totals vs PDF totals)
- Sequence: Summary scan → Pass 1+2 → broker processing → total comparison → Pass 3 if needed
