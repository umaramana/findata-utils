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


def _redact(val):
    """Classify a cell's TYPE only -- never return its actual content. Used
    so this script's output can be pasted back for diagnosis without
    exposing real descriptions/dollar amounts (see data_safety.md)."""
    from brokers.schwab import _clean_str, _is_monetary
    from utils import is_date, is_date_strict
    s = _clean_str(val)
    if not s:
        return 'blank'
    if s == '--':
        return 'DASH(--)'
    if s.upper() == 'VARIOUS':
        return 'VARIOUS'
    if is_date_strict(s):
        return 'real-date'
    if is_date(s):
        return 'date-ish(other)'
    if _is_monetary(val):
        return 'monetary'
    return f'text(len={len(s)})'


def _skip_reason(vals, row_text):
    """
    Re-derive WHY _is_schwab_skip_or_subtotal (or the date/proceeds check)
    would skip a row -- returns a rule name and, for keyword matches, the
    matched keyword itself. Keywords are fixed strings already visible in
    schwab.py's source (generic English words like "cost"/"gain", broker
    boilerplate phrases) -- never client cell content -- so this is safe to
    print/paste per data_safety.md.
    """
    from brokers.schwab import _SKIP_KEYWORDS, _HEADER_KEYWORDS

    non_empty = [v for v in vals if v]
    if not non_empty:
        return 'empty-row'
    for kw in _SKIP_KEYWORDS:
        if kw in row_text:
            return f'skip-keyword:"{kw}"'
    matched = [kw for kw in _HEADER_KEYWORDS if kw in row_text]
    if len(matched) >= 2:
        return f'header-keywords:{matched}'
    if 'subtotal' in vals[0].lower():
        return 'subtotal-label'
    import re
    if re.match(r'^totals?\b', vals[0].strip(), re.IGNORECASE):
        return 'totals-label'
    return None  # falls through to the date/proceeds check in _classify_row


def _classify_sheet(xl, sheet):
    from brokers.schwab import _classify_row, _detect_date_col, _clean_str
    df = xl.parse(sheet, header=None, dtype=str)
    num_cols = len(df.columns)
    date_col = _detect_date_col(df, num_cols)
    primaries, secondaries, skipped_with_shape = [], [], []
    for idx in range(len(df)):
        row = df.iloc[idx]
        rtype = _classify_row(row, num_cols, date_col)
        if rtype == 'primary':
            primaries.append(idx)
        elif rtype == 'secondary':
            secondaries.append(idx)
        elif rtype == 'skip':
            shape = [_redact(row.iloc[i]) if i < num_cols else 'blank' for i in range(num_cols)]
            non_blank = sum(1 for s in shape if s != 'blank')
            if non_blank >= 3:
                vals = [_clean_str(row.iloc[i]) if i < num_cols else '' for i in range(num_cols)]
                row_text = ' '.join(vals).lower()
                reason = _skip_reason(vals, row_text) or 'date/proceeds-check-failed'
                skipped_with_shape.append((idx, shape, reason))
    return df, date_col, primaries, secondaries, skipped_with_shape


def raw_analysis():
    """Analyze raw sheet data — row classification and pair detection.
    Prints STRUCTURE ONLY (column count, detected date column, cell TYPES
    like 'real-date'/'DASH(--)'/'monetary'/'text') -- never actual cell
    content, so this output is safe to paste back for diagnosis."""
    import pandas as pd
    path = _cli_path()
    xl = pd.ExcelFile(path)
    total_primary = total_secondary = 0
    for sheet in xl.sheet_names:
        df, date_col, primaries, secondaries, skipped = _classify_sheet(xl, sheet)
        total_primary += len(primaries)
        total_secondary += len(secondaries)
        print(f'\n=== {sheet} ({len(df)} rows, {len(df.columns)} cols, '
              f'detected date_col={date_col}) ===')
        print(f'  Primary: {len(primaries)}, Secondary: {len(secondaries)}')
        if skipped:
            print('  Skipped rows with 3+ non-blank cells (types only, no content):')
            for idx, shape, reason in skipped:
                print(f'    Row {idx} [{reason}]: {shape}')
    print(f'\nTOTAL: {total_primary} primary, {total_secondary} secondary')


if __name__ == '__main__':
    if '--raw' in sys.argv:
        raw_analysis()
    else:
        main()
