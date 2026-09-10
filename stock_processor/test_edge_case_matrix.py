#!/usr/bin/env python3
"""
Standing edge-case matrix for broker parsing/detection logic.

Why this exists: the 10-baseline regression suite (test_regression.py) only
covers "clean" real files a human already verified. It caught zero of the
two "--" regressions found 2026-09-08 because none of those baselines had
"--" landing where the bug needed it (a column _detect_date_col actually
scans, or the sole transaction on a sheet). Re-deriving a new synthetic case
from scratch every time a real client file breaks something is slow and
never gets ahead of the next edge case.

This suite instead sweeps single-dimension variations (one column's value
changed from the "normal" baseline at a time) across every column that
matters to detection/classification, for every broker whose synthetic
builder exists in synthetic_fixtures.py. It asserts structural invariants
(row count, Proceeds/Cost totals) inline — no hand-verified expected .xlsx
file needed per case — so adding a new scenario is a few lines, not a new
fixture file to eyeball.

MANDATORY: run this (`python test_edge_case_matrix.py`) alongside
test_regression.py any time you touch column-detection, row-classification,
or value-parsing logic in pdf_qc.py, utils.py, or any brokers/*.py — not
just when you happen to have a failing real file to reproduce. See
feedback_synthetic_edge_case_matrix.md in memory.

Usage:
  python test_edge_case_matrix.py            # run all scenarios
  python test_edge_case_matrix.py -v          # verbose
  python test_edge_case_matrix.py Cost        # filter by name substring
"""
import io
import sys

import pandas as pd

# No sys.path hack needed: Python already puts this script's own directory
# (stock_processor/) on sys.path when run as `python test_edge_case_matrix.py`.
import pdf_qc
from brokers import schwab
from synthetic_fixtures import build_schwab_sheet, schwab_date_cols


def _run_schwab(df, broker_key='charles_schwab'):
    """Run a synthetic raw DataFrame through the same pipeline app.py uses:
    QC -> broker parse. Returns the processed (pre-Drake-mapping) DataFrame."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Sheet1', index=False, header=False)
    buf.seek(0)

    qc = pdf_qc.detect_and_correct(buf, broker_key)
    corrected = qc.get('corrected_excel')
    file_to_process = corrected if corrected is not None else buf
    file_to_process.seek(0)

    return schwab.process(file_to_process)


def _money(s):
    """Parse a '$1,234.56' / '$ (12.34)' style string to float, for assertion."""
    if s is None or s == '':
        return None
    s = str(s).replace('$', '').replace(',', '').strip()
    neg = s.startswith('(') and s.endswith(')')
    if neg:
        s = s[1:-1]
    try:
        v = float(s)
        return -v if neg else v
    except (ValueError, TypeError):
        return None


# ── Scenario manifest ──────────────────────────────────────────────────────
# Each scenario builds a sheet via build_schwab_sheet and asserts structural
# invariants. "expect_rows" = how many transactions must survive; "check"
# is an optional extra assertion fn(df) -> (ok: bool, msg: str).

def _one_normal_txn(**overrides):
    tx = dict(desc='5 TEST CORP', cusip='000000000 / TEST',
              date_acq='01/17/2025', date_sold='12/26/2025',
              proceeds='$500.00', cost='$400.00', gain_loss='$100.00')
    tx.update(overrides)
    return [tx]


def _expected_totals(transactions):
    """
    Compute expected Proceeds/Cost totals from the transaction specs
    themselves, so every scenario gets a VALUE check for free, not just a
    row-count check. Row count alone previously let real corruption through
    silently: with the pre-fix broad is_date(), a wrong date_col was picked,
    every row still classified as "primary" (Accrued/Wash's "--" satisfied
    the date check, Gain/Loss satisfied the "next col monetary" check), so
    row count matched expected while Proceeds actually held Gain/Loss values
    and Cost was blank -- exactly the real client bug, and row-count-only
    checks did not catch it.

    Cost total is only checked when every transaction's cost is genuinely
    monetary; scenarios that deliberately use "Not Reported"/blank Cost skip
    that half (there's nothing to sum).
    """
    proceeds_total = sum(_money(tx.get('proceeds', '$100.00')) or 0 for tx in transactions)
    cost_vals = [_money(tx.get('cost', '$80.00')) for tx in transactions]
    cost_total = sum(v or 0 for v in cost_vals) if all(v is not None for v in cost_vals) else None
    return proceeds_total, cost_total


def _check_totals(expected_proceeds, expected_cost):
    def _check(df):
        actual_proceeds = sum(_money(v) or 0 for v in df['Proceeds']) if len(df) else 0.0
        if abs(actual_proceeds - expected_proceeds) > 0.01:
            return False, (f"Proceeds total: actual {actual_proceeds:.2f} vs expected "
                            f"{expected_proceeds:.2f} -- values misaligned (e.g. Gain/Loss "
                            f"leaking into Proceeds), not just a row-count problem")
        if expected_cost is not None:
            actual_cost = sum(_money(v) or 0 for v in df['Cost']) if len(df) else 0.0
            if abs(actual_cost - expected_cost) > 0.01:
                return False, (f"Cost total: actual {actual_cost:.2f} vs expected "
                                f"{expected_cost:.2f} -- values misaligned")
        return True, ''
    return _check


SCENARIOS = []


def scenario(name, num_cols, transactions, expect_rows, check=None, date_col=None):
    if check is None:
        expected_proceeds, expected_cost = _expected_totals(transactions)
        check = _check_totals(expected_proceeds, expected_cost)
    SCENARIOS.append(dict(name=name, num_cols=num_cols, transactions=transactions,
                           expect_rows=expect_rows, check=check, date_col=date_col))


# -- Baseline sanity across all known column widths --------------------------
for _nc in (7, 8, 9, 10):
    scenario(f'{_nc}-col baseline (sanity)', _nc, _one_normal_txn(), 1)

# -- Date Acquired / Date Sold value variations -------------------------------
scenario('Date Acquired = "--"', 9, _one_normal_txn(date_acq='--'), 1)
scenario('Date Acquired = "VARIOUS"', 9, _one_normal_txn(date_acq='VARIOUS'), 1)
scenario('Date Sold = "--"', 9, _one_normal_txn(date_sold='--'), 1)
scenario('Both dates = "--" (single txn, no anchor elsewhere on sheet)',
         8, _one_normal_txn(date_acq='--', date_sold='--'), 1)

# -- Cost column value variations (must never require Cost to be monetary) ---
scenario('Cost = "Not Reported" (non-monetary text)', 9,
         _one_normal_txn(cost='Not Reported'), 1)
scenario('Cost = "" (blank)', 9, _one_normal_txn(cost=''), 1)
scenario('Cost = "Not Reported" AND BOTH dates = "--" AND width formula guesses '
         'the WRONG column (combined — reproduces the real client bug exactly: '
         'zero real dates anywhere on the sheet, Cost non-monetary so it cannot '
         'anchor detection, and an extra padding column means the naive '
         'num_cols-based formula would land on the wrong column too)',
         8, _one_normal_txn(date_acq='--', date_sold='--', cost='Not Reported'), 1,
         date_col=2)  # formula for num_cols=8 would guess col 3 — deliberately wrong

# -- Proceeds variations -------------------------------------------------------
scenario('Proceeds = $0.00 (worthless security)', 9,
         _one_normal_txn(proceeds='$0.00', gain_loss='$ (400.00)'), 1)

# PDF24 merges Cost text into the Proceeds cell when a page has too few rows to
# infer column boundaries (real client, single-txn page, 2026-09-10):
# [desc, P, --, "$ 0.71 Not Provided", blank, --, --]
scenario('Proceeds cell merged with Cost text ("$ 0.71 Not Provided"), blank '
         'Cost, "--" Date Acquired, single txn on page (7-col)', 7,
         _one_normal_txn(date_acq='--', proceeds='$ 0.71 Not Provided', cost='',
                         gain_loss='--'), 1,
         check=_check_totals(0.71, None))
scenario('Proceeds cell merged with Cost text, no space after $ ("$0.71 Not Provided")',
         9, _one_normal_txn(proceeds='$0.71 Not Provided', cost=''), 1,
         check=_check_totals(0.71, None))
scenario('Merged Proceeds cell with a Cost value still in the Cost column '
         '("$ 0.71 Not Provided" + "$0.50") keeps the column Cost', 9,
         _one_normal_txn(proceeds='$ 0.71 Not Provided', cost='$0.50'), 1,
         check=_check_totals(0.71, 0.50))

# -- Gain/Loss variations -------------------------------------------------------
scenario('Gain/Loss negative', 9, _one_normal_txn(gain_loss='$ (250.00)'), 1)
scenario('Gain/Loss = $0.00', 9, _one_normal_txn(gain_loss='$0.00'), 1)

# -- Accrued/Wash Sale variations (must not affect detection; see 7-col dense) -
scenario('Accrued/Wash = non-zero dollar (should still parse + surface for review)',
         9, _one_normal_txn(accrued='$15.38', wash='$22.00'), 1)
scenario('Accrued/Wash "--" densely populates a column inside the scan window '
         '(7-col layout)', 7,
         [dict(desc=f'{i + 1} TEST CORP {i}', cusip=f'00000000{i} / TST{i}',
               date_acq='01/17/2025', date_sold='12/26/2025',
               proceeds=f'${100 + i}.00', cost=f'${80 + i}.00', gain_loss=f'${20}.00')
          for i in range(6)], 6)

# -- Row position within sheet --------------------------------------------------
scenario('Target txn is the FIRST row after header (multi-txn sheet)', 9,
         [dict(desc='1 FIRST ROW TEST', date_acq='--', cost='Not Reported',
               proceeds='$10.00', gain_loss='$ (5.00)')]
         + [dict(desc=f'{i + 2} FILLER {i}', proceeds=f'${100 + i}.00', cost=f'${80 + i}.00',
                  gain_loss='$20.00') for i in range(3)],
         4)
scenario('Target txn is the LAST row before footer (multi-txn sheet)', 9,
         [dict(desc=f'{i + 1} FILLER {i}', proceeds=f'${100 + i}.00', cost=f'${80 + i}.00',
                  gain_loss='$20.00') for i in range(3)]
         + [dict(desc='4 LAST ROW TEST', date_acq='--', cost='Not Reported',
                  proceeds='$10.00', gain_loss='$ (5.00)')],
         4)

# -- Multiple transactions for the same security (from earlier bug-hunt) ------
scenario('2 lots of the same security, one with "--" date', 9,
         [dict(desc='10 SAME CORP LOT A', cusip='111111111 / SAME',
               proceeds='$300.00', cost='$250.00', gain_loss='$50.00'),
          dict(desc='10 SAME CORP LOT A', cusip='111111111 / SAME',
               date_acq='--', proceeds='$150.00', cost='Not Reported',
               gain_loss='$ (50.00)')],
         2)

# -- FALSE-POSITIVE guards: every scenario above checks that a real
# transaction is correctly ACCEPTED. These check the opposite direction --
# that non-transaction rows and garbage values are correctly REJECTED,
# rather than silently manufacturing a phantom transaction or corrupting a
# legitimate sibling row. Both directions matter equally: a detector that
# accepts everything would pass every scenario above too.
scenario('Sheet with ZERO real transactions (boilerplate/subtotal-shaped '
         'rows only) must yield 0 rows, not a phantom transaction', 9, [], 0)
scenario('Garbage/unrecognized date value ("UNKNOWN", not a known sentinel) '
         'is excluded, without corrupting a legitimate sibling transaction '
         'on the same sheet',
         # NOTE: "N/A" was tried first and looked like it worked -- but
         # openpyxl/pandas silently converts the literal string "N/A" to an
         # actual blank/NaN cell on the to_excel/read_excel round-trip (Excel
         # treats "N/A" as a missing-value marker), so that scenario was
         # accidentally testing blank-cell handling, not garbage-text
         # rejection, and would have stayed green even if garbage rejection
         # were broken. "UNKNOWN" survives the round-trip as literal text
         # (verified) -- confirm before trusting any sentinel string in a
         # synthetic fixture; don't assume text round-trips unchanged.
         9,
         [dict(desc='1 GARBAGE ROW', date_acq='UNKNOWN', date_sold='UNKNOWN',
               proceeds='$999.00', cost='$999.00', gain_loss='$0.00'),
          dict(desc='2 LEGIT ROW', proceeds='$300.00', cost='$250.00',
               gain_loss='$50.00')],
         1,
         # Only the legit row's totals should show up -- if the garbage row's
         # $999 leaked in (partially or fully), this total would be wrong.
         check=_check_totals(300.00, 250.00))
scenario('Proceeds cell with "$" but NO number ("$ Not Provided") must not '
         'become a phantom transaction', 9,
         _one_normal_txn(date_acq='--', proceeds='$ Not Provided', cost=''), 0,
         check=_check_totals(0.0, None))


def _totals_row_scenario():
    """A 'Totals' footer row (distinct from a per-security 'Subtotal' row --
    see _is_schwab_skip_or_subtotal, which only keys off the word
    'subtotal') carries monetary Proceeds/Cost values but no date. It must
    NOT be picked up as a phantom transaction just because it structurally
    resembles one (monetary values present) -- the missing/non-date value in
    the date column is what should exclude it."""
    num_cols = 9
    date_col, proceeds_col, cost_col, aw_col, gl_col = schwab_date_cols(num_cols)
    df = build_schwab_sheet(num_cols, _one_normal_txn(), footer=False)
    totals_row = [None] * num_cols
    totals_row[0] = 'Totals'
    totals_row[proceeds_col] = '$500.00'
    totals_row[cost_col] = '$400.00'
    totals_row[gl_col] = '$100.00'
    df = pd.concat([df, pd.DataFrame([totals_row])], ignore_index=True)
    return df


SCENARIOS.append(dict(
    name='"Totals" footer row (monetary, no date) must not be counted as a '
         'second phantom transaction',
    num_cols=None, transactions=None, expect_rows=1,
    check=_check_totals(500.00, 400.00), date_col=None,
    _custom_df=_totals_row_scenario,
))


def _run_scenario(sc, verbose):
    name = sc['name']
    try:
        if sc.get('_custom_df') is not None:
            df = sc['_custom_df']()
        else:
            df = build_schwab_sheet(sc['num_cols'], sc['transactions'], date_col=sc.get('date_col'))
        actual = _run_schwab(df)
    except Exception as exc:
        print(f"FAIL  {name}")
        print(f"  ERROR: {exc}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

    errors = []
    if len(actual) != sc['expect_rows']:
        errors.append(f"  Row count: actual {len(actual)} vs expected {sc['expect_rows']}"
                       f" -- a transaction was likely silently dropped")

    if sc['check'] is not None and not errors:
        ok, msg = sc['check'](actual)
        if not ok:
            errors.append(f"  {msg}")

    if not errors:
        print(f"PASS  {name}  ({len(actual)} rows)")
        if verbose and len(actual):
            print(actual[['Description', 'Date Acquired', 'Date Sold', 'Proceeds', 'Cost']]
                  .to_string(index=False))
        return True
    else:
        print(f"FAIL  {name}")
        for line in errors:
            print(line)
        return False


def main():
    args = sys.argv[1:]
    verbose = '-v' in args
    filter_name = next((a for a in args if not a.startswith('-')), None)

    scenarios = SCENARIOS
    if filter_name:
        scenarios = [s for s in SCENARIOS if filter_name.lower() in s['name'].lower()]
        if not scenarios:
            print(f"No scenarios match '{filter_name}'")
            sys.exit(1)

    print(f"\nRunning {len(scenarios)} edge-case scenario(s)...\n")
    passed = failed = 0
    for sc in scenarios:
        if _run_scenario(sc, verbose):
            passed += 1
        else:
            failed += 1

    print(f"\n{'-' * 42}")
    print(f"  {passed} passed  |  {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
