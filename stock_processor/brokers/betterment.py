"""
Betterment broker processor.

Source: Native CSV export (no PDF24 conversion needed — skip QC).

Column layout (0-indexed):
  0:  Description
  1:  Symbol
  2:  CUSIP
  3:  Date Acquired
  4:  Date Sold
  5:  Gross Proceeds
  6:  Cost or Other Basis
  7:  Gain/(Loss)              ← NOT used in Drake output
  8:  Wash Sale Loss Disallowed
  9:  Federal Income Tax Withheld
  10: Type of Gain(Loss)
  11: Noncovered Securities
  12: Reporting Category

Row 0 is the header — skipped.
All remaining rows are transactions (no stock-name rows, subtotal rows, or section headers).

Note: Gain/Loss (col 7) appears BEFORE Wash Sale (col 8) — opposite of other brokers.
This is fine since columns are read by fixed index, not by zone detection.
"""

import numpy as np
import pandas as pd


def _extract_numeric(val):
    """Return cleaned numeric string, or empty string if not a valid number."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ''
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', '--', ''):
        return ''
    cleaned = s.replace('$', '').replace(',', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        float(cleaned)
        return cleaned
    except (ValueError, TypeError):
        return ''


def process(file_obj):
    """
    Process Betterment CSV transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Description, Date Acquired, Date Sold,
                               Proceeds, Cost, Wash Sale Loss, Fed Tax Withheld,
                               Source Sheet
    """
    df = pd.read_csv(file_obj, header=0, dtype=str)

    rows = []
    for idx, row in df.iterrows():
        # Skip rows with no date (safety net for any blank/footer rows)
        date_acq = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
        if not date_acq or date_acq.lower() in ('nan', 'none', ''):
            continue

        tx = {
            'Description':  str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else '',
            'Date Acquired': date_acq,
            'Date Sold':     str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else '',
            'Proceeds':      _extract_numeric(row.iloc[5]),
            'Cost':          _extract_numeric(row.iloc[6]),
            'Wash Sale Loss': _extract_numeric(row.iloc[8]),
            'Fed Tax Withheld': _extract_numeric(row.iloc[9]),
            'Type':          str(row.iloc[10]).strip() if pd.notna(row.iloc[10]) else '',
            'Source Sheet':  'CSV',
        }
        rows.append(tx)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)
