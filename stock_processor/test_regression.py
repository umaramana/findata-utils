#!/usr/bin/env python3
"""
Regression test suite for Stock Transaction Processor.

Usage:
  python test_regression.py              # run all tests
  python test_regression.py -v           # verbose: confirm cell count on pass too
  python test_regression.py Merrill      # run only tests whose name contains 'Merrill'
  python test_regression.py Fidelity -v  # filter + verbose
  python test_regression.py --update     # regenerate ALL expected output files (update baselines)
  python test_regression.py Fidelity --update  # regenerate only matching tests
"""
import io
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brokers import apex_clearing, betterment, fidelity, jpmorgan, merrill, morgan_stanley, robinhood, schwab
import drake_mapper
import pdf_qc


# ── Test case manifest ────────────────────────────────────────────────────────
_TC = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'testdata', 'passedtestcases')
)

TEST_CASES = [
    dict(
        name='Fidelity am12025',
        broker_key='fidelity',
        input=os.path.join(_TC, 'fidelity_1099 test am1 2025.xlsx'),
        expected=os.path.join(_TC, 'fidelity_drake_import am12025.xlsx'),
    ),
    dict(
        name='Fidelity sk2025',
        broker_key='fidelity',
        input=os.path.join(_TC, 'fidelity_1099 test sk 2025.xlsx'),
        expected=os.path.join(_TC, 'fidelity_drake_import sk 2025.xlsx'),
    ),
    dict(
        name='Merrill Lynch',
        broker_key='merrill',
        input=os.path.join(_TC, 'merrill_1099 test am2025.xlsx'),
        expected=os.path.join(_TC, 'merrill_lynch_drake_import.xlsx'),
    ),
    dict(
        name='Morgan Stanley',
        broker_key='morgan_stanley',
        input=os.path.join(_TC, 'morgan_1099 test 2025 simple.xlsx'),
        expected=os.path.join(_TC, 'morgan_stanley_drake_import.xlsx'),
    ),
    dict(
        name='Betterment (CSV)',
        broker_key='csv_betterment',
        input=os.path.join(_TC, 'csv_betterment_1099 test sd 2025-withtype.csv'),
        expected=os.path.join(_TC, 'csvbetterment_drake_import.xlsx'),
    ),
    dict(
        name='Apex Clearing',
        broker_key='apex_clearing',
        input=os.path.join(_TC, 'apex_1099 test sd 2025.xlsx'),
        expected=os.path.join(_TC, 'apex_clearing_drake_import.xlsx'),
    ),
    dict(
        name='Robinhood',
        broker_key='robinhood',
        input=os.path.join(_TC, 'robinhood test 2025.xlsx'),
        expected=os.path.join(_TC, 'robinhood_drake_import.xlsx'),
    ),
    dict(
        name='JP Morgan',
        broker_key='jpmorgan',
        input=os.path.join(_TC, 'jpmorgan_1099 test sd 2025.xlsx'),
        expected=os.path.join(_TC, 'jpmorgan_drake_import.xlsx'),
    ),
    dict(
        name='Charles Schwab',
        broker_key='charles_schwab',
        input=os.path.join(_TC, 'schwab_1099 test 2025.xlsx'),
        expected=os.path.join(_TC, 'charles_schwab_drake_import.xlsx'),
    ),
    dict(
        name='Charles Schwab RM wash sale',
        broker_key='charles_schwab',
        input=os.path.join(_TC, 'Charles Schwab 1099 RM_s.xlsx'),
        expected=os.path.join(_TC, 'charles_schwab_rms_drake_import.xlsx'),
    ),
]

_BROKER_FN = {
    'fidelity':       fidelity.process,
    'charles_schwab': schwab.process,
    'robinhood':      robinhood.process,
    'merrill':        merrill.process,
    'morgan_stanley': morgan_stanley.process,
    'csv_betterment': betterment.process,
    'apex_clearing':  apex_clearing.process,
    'jpmorgan':       jpmorgan.process,
}

_NUMERIC_COLS = {'Proceeds', 'Cost', 'AMT Cost Basis', 'Accrued Discount',
                 'Wash Sale Loss', 'Fed Tax Withheld'}
_TOLERANCE    = 0.01   # one cent
_MAX_DIFFS    = 20     # cap per-test cell-diff output


# ── Pipeline (mirrors app.py exactly) ────────────────────────────────────────
def _run_pipeline(input_path, broker_key):
    """Run the full processing pipeline: QC → broker parse → Fed Tax normalize → Drake map."""
    with open(input_path, 'rb') as f:
        raw = f.read()
    file_io = io.BytesIO(raw)

    # QC step — skip for CSV brokers (no PDF24 artifacts)
    if broker_key.startswith('csv_'):
        file_to_process = file_io
    else:
        file_io.seek(0)
        qc = pdf_qc.detect_and_correct(file_io, broker_key)
        corrected = qc.get('corrected_excel')
        if corrected is not None:
            file_to_process = corrected
        else:
            file_io.seek(0)
            file_to_process = file_io

    if hasattr(file_to_process, 'seek'):
        file_to_process.seek(0)

    processed = _BROKER_FN[broker_key](file_to_process)

    # Normalize Fed Tax column name (mirrors the for-loop in app.py process_file)
    for col in list(processed.columns):
        cl = col.lower()
        if col != 'Fed Tax Withheld' and 'federal' in cl and 'tax' in cl:
            processed = processed.rename(columns={col: 'Fed Tax Withheld'})
            break

    return drake_mapper.map_to_drake_format(processed, broker_key)


# ── Comparison helpers ────────────────────────────────────────────────────────
def _norm_val(v, is_numeric):
    """Normalize a single cell value for comparison."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 0.0 if is_numeric else ''
    if is_numeric:
        try:
            return round(float(v), 2)
        except (ValueError, TypeError):
            return 0.0
    return str(v).strip()


def _normalize_df(df, common_cols):
    """Return a new DataFrame with all values normalized to canonical form."""
    out = {}
    for col in common_cols:
        is_num = col in _NUMERIC_COLS
        out[col] = df[col].apply(lambda v, n=is_num: _norm_val(v, n))
    return pd.DataFrame(out)


def _stable_sort(df):
    """Sort DataFrame by (Desc, Date Sold, Proceeds) for stable row comparison."""
    candidates = ['Desc', 'Date Sold', 'Proceeds']
    sort_by = [c for c in candidates if c in df.columns]
    if sort_by:
        return df.sort_values(sort_by, na_position='last').reset_index(drop=True)
    return df.reset_index(drop=True)


def _check_column_alignment(actual, expected):
    common  = [c for c in expected.columns if c in actual.columns]
    missing = [c for c in expected.columns if c not in actual.columns]
    extra   = [c for c in actual.columns   if c not in expected.columns]
    errors = []
    if missing:
        errors.append(f"  Columns missing from actual output: {missing}")
    if extra:
        errors.append(f"  Extra columns in actual output:    {extra}")
    return common, errors


def _check_totals(act, exp, common):
    errors = []
    for col in [c for c in common if c in _NUMERIC_COLS]:
        a_sum, e_sum = act[col].sum(), exp[col].sum()
        if abs(a_sum - e_sum) > _TOLERANCE:
            errors.append(
                f"  TOTAL [{col}]: actual={a_sum:,.2f}  expected={e_sum:,.2f}"
                f"  diff={a_sum - e_sum:+,.2f}"
            )
    return errors


def _check_cells(act, exp, common):
    diffs = []
    n = min(len(act), len(exp))
    for i in range(n):
        for col in common:
            a_val = act.at[i, col]
            e_val = exp.at[i, col]
            if col in _NUMERIC_COLS:
                mismatch = abs(a_val - e_val) > _TOLERANCE
                label    = f"{a_val:.2f} vs {e_val:.2f}"
            else:
                mismatch = (a_val != e_val)
                label    = f"'{a_val}' vs '{e_val}'"
            if mismatch:
                diffs.append(f"  Row {i + 1:>3} [{col}]: {label}")
        if len(diffs) >= _MAX_DIFFS:
            diffs.append(f"  ... (output capped at {_MAX_DIFFS} diffs; run -v for full details)")
            break
    return diffs, n


def _compare(actual, expected, verbose):
    """
    Compare actual vs expected Drake DataFrames.
    Returns a list of error strings. Empty list = pass.
    """
    errors = []

    if len(actual) != len(expected):
        errors.append(f"  Row count: actual {len(actual)} vs expected {len(expected)}")

    common, col_errors = _check_column_alignment(actual, expected)
    errors.extend(col_errors)

    if not common:
        return errors

    act = _normalize_df(_stable_sort(actual[common]),   common)
    exp = _normalize_df(_stable_sort(expected[common]), common)

    errors.extend(_check_totals(act, exp, common))

    diffs, n = _check_cells(act, exp, common)
    if diffs:
        errors.extend(diffs)
    elif verbose and not errors:
        print(f"    {n} rows × {len(common)} cols = {n * len(common)} cells — all match")

    return errors


# ── Test runner ───────────────────────────────────────────────────────────────
def _run_test(tc, verbose):
    """Run one test case. Prints result. Returns True if passed."""
    name = tc['name']

    try:
        actual   = _run_pipeline(tc['input'], tc['broker_key'])
        expected = pd.read_excel(tc['expected'])
    except Exception as exc:
        print(f"FAIL  {name}")
        print(f"  ERROR: {exc}")
        import traceback
        if verbose:
            traceback.print_exc()
        return False

    errors = _compare(actual, expected, verbose)

    if not errors:
        print(f"PASS  {name}  ({len(actual)} rows)")
        return True
    else:
        n_exp = len(expected)
        print(f"FAIL  {name}  (actual={len(actual)} rows, expected={n_exp} rows)")
        for line in errors:
            print(line)
        return False


def _update_baseline(tc):
    """Regenerate the expected output file for one test case."""
    name = tc['name']
    try:
        actual = _run_pipeline(tc['input'], tc['broker_key'])
        actual.to_excel(tc['expected'], index=False)
        print(f"UPDATED  {name}  ({len(actual)} rows  →  {tc['expected']})")
        return True
    except Exception as exc:
        print(f"ERROR    {name}  —  {exc}")
        return False


def main():
    args        = sys.argv[1:]
    verbose     = '-v' in args
    update      = '--update' in args
    filter_name = next((a for a in args if not a.startswith('-')), None)

    cases = TEST_CASES
    if filter_name:
        cases = [tc for tc in TEST_CASES if filter_name.lower() in tc['name'].lower()]
        if not cases:
            print(f"No test cases match '{filter_name}'")
            sys.exit(1)

    if update:
        print(f"\nUpdating {len(cases)} baseline(s)...\n")
        ok = all(_update_baseline(tc) for tc in cases)
        print(f"\n{'─' * 42}")
        print("  Baselines updated." if ok else "  Some updates failed.")
        if not ok:
            sys.exit(1)
        return

    print(f"\nRunning {len(cases)} regression test(s)...\n")

    passed = failed = 0
    for tc in cases:
        if _run_test(tc, verbose):
            passed += 1
        else:
            failed += 1

    print(f"\n{'─' * 42}")
    print(f"  {passed} passed  |  {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
