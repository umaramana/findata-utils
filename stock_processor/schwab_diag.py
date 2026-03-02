#!/usr/bin/env python3
"""
Schwab diagnostic script — reusable inspection of Schwab 1099-B test files.

Usage:
  python schwab_diag.py                           # inspect default new test file
  python schwab_diag.py path/to/file.xlsx         # inspect a specific file
  python schwab_diag.py --process                 # run full pipeline and show output
  python schwab_diag.py --process --validate      # run pipeline + compare totals
"""
import io
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'testdata', 'Schwab-1099-Stocktrans.xlsx')
)

_DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')


def _is_monetary(val):
    """Check if value contains at least one monetary amount (handles merged 'Proceeds $ Cost' too)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    s = str(val).strip()
    if not s or s == '--':
        return False
    # Split on $ to handle merged values like "$ 389.44 $ 235.56"
    parts = [p.strip() for p in s.split('$') if p.strip()]
    if not parts:
        return False
    # Check if at least the first part is numeric
    first = parts[0].replace(',', '').replace('(', '').replace(')', '').strip()
    try:
        float(first)
        return True
    except (ValueError, TypeError):
        return False


def inspect_file(filepath):
    """Show column layout, row types, and transaction counts per sheet."""
    print(f"\n{'='*60}")
    print(f"FILE: {filepath}")
    xls = pd.ExcelFile(filepath)
    print(f"Sheets: {xls.sheet_names}")

    total_primary = 0
    total_secondary = 0
    total_subtotal = 0

    for sheet in xls.sheet_names:
        df = xls.parse(sheet, header=None, dtype=str)
        n_rows, n_cols = df.shape
        print(f"\n--- {sheet}: {n_rows} rows x {n_cols} cols ---")

        # Show header rows (rows 6-8 typically)
        for i in range(min(9, n_rows)):
            row_text = ' | '.join(
                str(df.iat[i, c])[:35] if pd.notna(df.iat[i, c]) else '.'
                for c in range(n_cols)
            )
            print(f"  [{i:2d}] {row_text}")

        # Classify data rows
        primary_rows = []
        secondary_rows = []
        subtotal_rows = []

        for i in range(9, n_rows):
            c0 = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ''
            c4 = str(df.iat[i, 4]) if n_cols > 4 and pd.notna(df.iat[i, 4]) else ''
            c5 = str(df.iat[i, 5]) if n_cols > 5 and pd.notna(df.iat[i, 5]) else ''

            has_date = bool(_DATE_RE.match(c4.strip()))
            has_proceeds = _is_monetary(c5) if c5 else False

            if 'subtotal' in c0.lower():
                subtotal_rows.append(i)
            elif has_date and has_proceeds:
                primary_rows.append(i)
            elif has_date and not has_proceeds and c0:
                secondary_rows.append(i)

        print(f"  Primary (date+proceeds): {len(primary_rows)} rows  {primary_rows}")
        print(f"  Secondary (CUSIP):       {len(secondary_rows)} rows  {secondary_rows}")
        print(f"  Subtotal:                {len(subtotal_rows)} rows")

        # Show primary row details
        for i in primary_rows:
            vals = []
            for c in range(n_cols):
                v = str(df.iat[i, c]) if pd.notna(df.iat[i, c]) else '.'
                vals.append(v[:40])
            print(f"    Row {i}: {vals}")

        total_primary += len(primary_rows)
        total_secondary += len(secondary_rows)
        total_subtotal += len(subtotal_rows)

    print(f"\n{'='*60}")
    print(f"TOTALS: {total_primary} primary txns, {total_secondary} secondary rows, {total_subtotal} subtotals")
    return total_primary


def process_and_show(filepath):
    """Run the full pipeline (QC → broker → Drake) and display output."""
    import drake_mapper
    import pdf_qc
    from brokers import schwab

    with open(filepath, 'rb') as f:
        raw = f.read()
    file_io = io.BytesIO(raw)

    # QC step
    file_io.seek(0)
    qc = pdf_qc.detect_and_correct(file_io, 'charles_schwab')
    print(f"\nQC log:")
    for line in qc['log']:
        print(f"  {line}")

    corrected = qc.get('corrected_excel')
    if corrected is not None:
        file_to_process = corrected
    else:
        file_io.seek(0)
        file_to_process = file_io

    if hasattr(file_to_process, 'seek'):
        file_to_process.seek(0)

    # Broker processing
    processed = schwab.process(file_to_process)
    print(f"\nBroker output: {len(processed)} rows x {len(processed.columns)} cols")
    print(f"Columns: {list(processed.columns)}")

    if not processed.empty:
        print("\nFirst 5 rows:")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 200)
        pd.set_option('display.max_colwidth', 40)
        print(processed.head().to_string())

        # Totals
        for col in ['Proceeds', 'Cost', 'Wash Sale Loss', 'Accrued Market Discount']:
            if col in processed.columns:
                total = 0
                for v in processed[col]:
                    try:
                        total += float(str(v).replace('$', '').replace(',', ''))
                    except (ValueError, TypeError):
                        pass
                print(f"  {col} total: ${total:,.2f}")

    # Drake mapping
    drake = drake_mapper.map_to_drake_format(processed, 'charles_schwab')
    print(f"\nDrake output: {len(drake)} rows x {len(drake.columns)} cols")
    print(f"Columns: {list(drake.columns)}")

    if not drake.empty:
        print("\nAll Drake rows:")
        print(drake.to_string())

        # Drake totals
        for col in ['Proceeds', 'Cost', 'Wash Sale Loss', 'Accrued Discount']:
            if col in drake.columns:
                vals = drake[col].dropna()
                total = vals.sum() if pd.api.types.is_numeric_dtype(vals) else 0
                print(f"  {col} total: ${total:,.2f}")

    return drake


def main():
    args = sys.argv[1:]
    filepath = DEFAULT_FILE
    do_process = '--process' in args
    do_validate = '--validate' in args

    # Check for file path argument
    for a in args:
        if not a.startswith('--') and os.path.exists(a):
            filepath = a
            break

    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    n_txns = inspect_file(filepath)

    if do_process:
        drake = process_and_show(filepath)
        if do_validate:
            print(f"\n--- VALIDATION ---")
            print(f"Expected transactions: {n_txns}")
            print(f"Drake rows:           {len(drake)}")
            if len(drake) == n_txns:
                print("  MATCH")
            else:
                print(f"  MISMATCH (diff={len(drake) - n_txns})")


if __name__ == '__main__':
    main()
