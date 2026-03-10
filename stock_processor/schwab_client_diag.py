#!/usr/bin/env python3
"""
Diagnostic script for Schwab client file analysis.
Usage: python schwab_client_diag.py [file_path] [--raw]
Default: ../testdata/Charles Schwab 1099.xlsx
"""
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brokers import schwab
import drake_mapper

_DEFAULT_PATH = '../testdata/Charles Schwab 1099.xlsx'


def _cli_path():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    return args[0] if args else _DEFAULT_PATH


def _sum_col(drake, col):
    return drake[col].apply(
        lambda v: float(v) if v is not None and str(v).strip() not in ('', 'nan', 'None') else 0
    ).sum()


def _run_pipeline(path):
    import pdf_qc
    with open(path, 'rb') as f:
        raw = f.read()
    file_io = io.BytesIO(raw)
    qc = pdf_qc.detect_and_correct(file_io, 'charles_schwab')
    print(f'QC fixes: {qc["total_fixes"]}')
    for line in qc['log']:
        print(f'  {line}')
    if qc['corrected_excel'] is not None:
        qc['corrected_excel'].seek(0)
        processed = schwab.process(qc['corrected_excel'])
    else:
        file_io.seek(0)
        processed = schwab.process(file_io)
    print(f'Broker rows: {len(processed)}')
    return processed


def _print_financials(drake):
    proceeds = _sum_col(drake, 'Proceeds')
    cost = _sum_col(drake, 'Cost')
    print(f'Proceeds: ${proceeds:,.2f} (expected: $139,268.68)')
    print(f'Cost:     ${cost:,.2f}')
    print(f'Gap:      ${139268.68 - proceeds:,.2f}')
    print()

    def _is_empty(v):
        return v is None or str(v).strip() in ('', 'nan', 'None')
    da_empty = drake['Date Acquired'].apply(_is_empty).sum()
    ds_empty = drake['Date Sold'].apply(_is_empty).sum()
    print(f'Date Acquired empty: {da_empty}/{len(drake)}')
    print(f'Date Sold empty:     {ds_empty}/{len(drake)}')
    print()


def main():
    path = _cli_path()
    print(f'File: {path}')
    processed = _run_pipeline(path)
    if processed.empty:
        print('No data processed')
        return
    drake = drake_mapper.map_to_drake_format(processed, 'charles_schwab')
    print(f'Drake rows: {len(drake)}')
    _print_financials(drake)
    cols = ['Desc', 'Date Acquired', 'Date Sold', 'Proceeds', 'Cost']
    print('First 10 rows:')
    print(drake[cols].head(10).to_string())
    print()
    print('Last 5 rows:')
    print(drake[cols].tail().to_string())


def _classify_sheet(xl, sheet):
    from brokers.schwab import _classify_row, _clean_str
    df = xl.parse(sheet, header=None, dtype=str)
    num_cols = len(df.columns)
    primaries, secondaries, skipped_with_data = [], [], []
    for idx in range(len(df)):
        row = df.iloc[idx]
        rtype = _classify_row(row, num_cols)
        if rtype == 'primary':
            primaries.append(idx)
        elif rtype == 'secondary':
            secondaries.append(idx)
        elif rtype == 'skip':
            vals = [_clean_str(row.iloc[i]) if i < num_cols else '' for i in range(num_cols)]
            non_empty = [v for v in vals if v]
            if len(non_empty) >= 3:
                skipped_with_data.append((idx, vals[:6]))
    return df, primaries, secondaries, skipped_with_data


def raw_analysis():
    """Analyze raw sheet data — row classification and pair detection."""
    import pandas as pd
    path = _cli_path()
    xl = pd.ExcelFile(path)
    total_primary = total_secondary = 0
    for sheet in xl.sheet_names:
        df, primaries, secondaries, skipped = _classify_sheet(xl, sheet)
        total_primary += len(primaries)
        total_secondary += len(secondaries)
        print(f'\n=== {sheet} ({len(df)} rows, {len(df.columns)} cols) ===')
        print(f'  Primary: {len(primaries)}, Secondary: {len(secondaries)}')
        if skipped:
            print('  Skipped rows with 3+ non-empty cells:')
            for idx, vals in skipped:
                print(f'    Row {idx}: {vals}')
    print(f'\nTOTAL: {total_primary} primary, {total_secondary} secondary')


if __name__ == '__main__':
    if '--raw' in sys.argv:
        raw_analysis()
    else:
        main()
