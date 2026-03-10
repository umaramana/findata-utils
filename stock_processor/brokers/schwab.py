"""
Charles Schwab broker processor.

Handles:
- 9-column layout from PDF-to-Excel conversion (PDF24 or similar)
- Paired row structure: primary (financials) + secondary (CUSIP)
- Merged Proceeds/Cost in a single cell ("$ X $ Y" or "$ X $" + separate Cost col)
- Merged Accrued Market Discount / Wash Sale in col 7
- "VARIOUS" and date codes (SC, BC) in Date Acquired column
- Multi-sheet files with consistent layout across sheets

Column layout (0-indexed, 9-col new file):
  0: Description (primary row) / CUSIP+symbol (secondary row)
  1: Strike price info (e.g. "$592")
  2: Option expiry (e.g. "EXP 03/03/25")
  3: Date Acquired / code (SC=Sold to Close, BC=Bought to Close)
  4: Date Sold (1c)
  5: Proceeds (1d) — sometimes merged with Cost as "$ X $ Y"
  6: Cost (1e) — sometimes NaN when merged into col 5
  7: Accrued Market Discount (1f) / Wash Sale Loss (1g) — MERGED
  8: Realized Gain or (Loss)
"""

import re

import numpy as np
import pandas as pd

from utils import extract_numeric, parse_accrued_wash_sale, is_date


_SKIP_KEYWORDS = [
    'proceeds from broker',
    'form 1099',
    'omb no',
    'short-term',
    'long-term',
    'description of property',
    'cusip number',
    'example 100 sh',
    'important tax',
    'furnished to the internal',
    'fatca filing',
    'please see the',
    'charles schwab',
    'taxpayers are',
    'copy b for recipient',
    'department of the treasury',
    'date prepared',
    'tax year',
]

_HEADER_KEYWORDS = ['proceeds', 'cost', 'gain', 'loss', 'date sold', 'date acquired',
                     '1d-', '1e-', '1f-', '1g-', 'reported to irs']


def _is_monetary(val):
    """Check if value contains at least one monetary amount (handles merged Proceeds+Cost)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    s = str(val).strip()
    if not s or s == '--':
        return False
    parts = [p.strip() for p in s.split('$') if p.strip()]
    if not parts:
        return False
    first = parts[0].replace(',', '').replace('(', '').replace(')', '').strip()
    try:
        float(first)
        return True
    except (ValueError, TypeError):
        return False


def _clean_str(val):
    """Convert to string, return '' for nan/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ''
    s = str(val).strip()
    if s.lower() in ('nan', 'none'):
        return ''
    return s


def _clean_currency(value):
    """Clean currency value: remove $ and commas, handle parentheses for negatives."""
    if not value or value in ('--', 'nan', 'NaN', 'None', ''):
        return ''
    cleaned = re.sub(r'[\$,\s]', '', str(value))
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    if not cleaned:
        return ''
    try:
        float(cleaned)
        return cleaned
    except (ValueError, TypeError):
        return ''


def _split_proceeds_cost(col5_val, col6_val):
    """
    Parse Proceeds and Cost from cols 5 and 6.

    Schwab sometimes merges both into col 5 as "$ X $ Y" (two $ signs)
    or "$ X $" (trailing $, Cost in col 6), or "$ X" (single value, Cost in col 6).

    Returns (proceeds_str, cost_str) — cleaned numeric strings.
    """
    s5 = _clean_str(col5_val)
    s6 = _clean_str(col6_val)

    if not s5:
        return ('', _clean_currency(s6))

    # Count $ signs to detect merged pattern
    dollar_parts = [p.strip() for p in s5.split('$') if p.strip()]

    if len(dollar_parts) >= 2:
        # Merged: "$ X $ Y" → Proceeds=X, Cost=Y
        proceeds = _clean_currency(dollar_parts[0])
        cost = _clean_currency(dollar_parts[1])
        return (proceeds, cost)
    elif len(dollar_parts) == 1:
        # Single value in col 5; Cost from col 6
        proceeds = _clean_currency(s5)
        cost = _clean_currency(s6)
        return (proceeds, cost)
    else:
        return (_clean_currency(s5), _clean_currency(s6))


def _is_schwab_skip_or_subtotal(vals, row_text):
    """
    Check if a Schwab row should be skipped or is a subtotal.
    Returns 'skip', 'subtotal', or None (continue classification).
    """
    non_empty = [v for v in vals if v]
    if not non_empty:
        return 'skip'

    if any(kw in row_text for kw in _SKIP_KEYWORDS):
        return 'skip'

    if sum(1 for kw in _HEADER_KEYWORDS if kw in row_text) >= 2:
        return 'skip'

    if 'subtotal' in vals[0].lower():
        return 'subtotal'

    return None


def _classify_row(row, num_cols):
    """
    Classify a row as: skip | primary | secondary | subtotal.

    - primary: has a date in col 4 AND monetary value in col 5 (financial data)
    - secondary: has a date in col 4 but NO monetary in col 5 (CUSIP row)
    - subtotal: col 0 contains "Subtotal"
    - skip: headers, footers, empty rows
    """
    vals = [_clean_str(row.iloc[i]) if i < num_cols else '' for i in range(num_cols)]
    row_text = ' '.join(vals).lower()

    skip_or_sub = _is_schwab_skip_or_subtotal(vals, row_text)
    if skip_or_sub is not None:
        return skip_or_sub

    # Check for date in col 4 (Date Sold position)
    col4 = vals[4] if num_cols > 4 else ''
    if not is_date(col4):
        return 'skip'

    # Check for monetary value in col 5 (Proceeds)
    col5 = row.iloc[5] if num_cols > 5 else None
    return 'primary' if _is_monetary(col5) else 'secondary'


def _build_schwab_transaction(row1, secondary, num_cols):
    """
    Build a transaction dict from a primary row and optional secondary row.
    Returns the dict, or None if no financial data present.
    """
    desc1 = _clean_str(row1.iloc[0]) if num_cols > 0 else ''
    desc2 = _clean_str(secondary.iloc[0]) if secondary is not None and num_cols > 0 else ''
    full_desc = f"{desc1} {desc2}".strip()

    # Date Acquired: col 4 of primary row (col 4 carries both dates across the pair)
    date_acquired = _clean_str(row1.iloc[4]) if num_cols > 4 else ''

    # Date Sold: col 4 of secondary row (fallback to primary col 4 if no secondary)
    if secondary is not None and num_cols > 4:
        date_sold = _clean_str(secondary.iloc[4])
    else:
        date_sold = date_acquired

    # Proceeds and Cost (handle merged pattern)
    col5 = row1.iloc[5] if num_cols > 5 else None
    col6 = row1.iloc[6] if num_cols > 6 else None
    proceeds, cost = _split_proceeds_cost(col5, col6)

    # Accrued / Wash Sale (merged col 7)
    col7 = row1.iloc[7] if num_cols > 7 else None
    accrued_wash = parse_accrued_wash_sale(col7)

    # Only emit if we have actual financial data
    if not proceeds and not cost:
        return None

    return {
        'Description': full_desc,
        'Date Acquired': date_acquired,
        'Date Sold': date_sold,
        'Proceeds': proceeds,
        'Cost': cost,
        'Accrued Market Discount': accrued_wash['Accrued Market Discount'],
        'Wash Sale Loss': accrued_wash['Wash Sale Loss'],
    }


def _pair_rows_into_transactions(rows_classified, num_cols):
    """Pair primary + optional secondary rows into transaction dicts."""
    transactions = []
    i = 0
    while i < len(rows_classified):
        idx1, type1, row1 = rows_classified[i]

        if type1 != 'primary':
            i += 1
            continue

        secondary = None
        if i + 1 < len(rows_classified) and rows_classified[i + 1][1] == 'secondary':
            secondary = rows_classified[i + 1][2]
            i += 2
        else:
            i += 1

        tx = _build_schwab_transaction(row1, secondary, num_cols)
        if tx:
            transactions.append(tx)

    return transactions


def _process_sheet(df):
    """Process one sheet. Returns list of transaction dicts."""
    num_cols = len(df.columns)
    rows_classified = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        rtype = _classify_row(row, num_cols)
        if rtype in ('primary', 'secondary'):
            rows_classified.append((idx, rtype, row))

    return _pair_rows_into_transactions(rows_classified, num_cols)


def process(file_obj):
    """
    Process Schwab transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Description, Date Acquired, Date Sold,
                               Proceeds, Cost, Accrued Market Discount,
                               Wash Sale Loss, Source Sheet
    """
    excel_file = pd.ExcelFile(file_obj)
    all_rows = []

    for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name, header=None, dtype=str)
        txns = _process_sheet(df)
        for tx in txns:
            tx['Source Sheet'] = sheet_name
        all_rows.extend(txns)

    if not all_rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(all_rows)

    # Clean up nan/None strings
    for col in result_df.columns:
        result_df[col] = result_df[col].astype(str).replace(['nan', 'NaN', 'None', 'none'], '')

    return result_df
