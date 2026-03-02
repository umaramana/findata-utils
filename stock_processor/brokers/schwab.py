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


def _classify_row(row, num_cols):
    """
    Classify a row as: skip | primary | secondary | subtotal.

    - primary: has a date in col 4 AND monetary value in col 5 (financial data)
    - secondary: has a date in col 4 but NO monetary in col 5 (CUSIP row)
    - subtotal: col 0 contains "Subtotal"
    - skip: headers, footers, empty rows
    """
    vals = [_clean_str(row.iloc[i]) if i < num_cols else '' for i in range(num_cols)]
    non_empty = [v for v in vals if v]

    if not non_empty:
        return 'skip'

    col0 = vals[0]
    row_text = ' '.join(vals).lower()

    # Skip known header/footer keywords
    if any(kw in row_text for kw in _SKIP_KEYWORDS):
        return 'skip'

    # Skip header rows (multiple header keywords)
    if sum(1 for kw in _HEADER_KEYWORDS if kw in row_text) >= 2:
        return 'skip'

    # Subtotal rows
    if 'subtotal' in col0.lower():
        return 'subtotal'

    # Check for date in col 4 (Date Sold position)
    col4 = vals[4] if num_cols > 4 else ''
    has_date = is_date(col4)

    if not has_date:
        return 'skip'

    # Check for monetary value in col 5 (Proceeds)
    col5 = row.iloc[5] if num_cols > 5 else None
    if _is_monetary(col5):
        return 'primary'
    else:
        return 'secondary'


def _process_sheet(df):
    """
    Process one sheet. Returns list of transaction dicts.

    Pairs primary + secondary rows into single transactions.
    """
    num_cols = len(df.columns)
    rows_classified = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        rtype = _classify_row(row, num_cols)
        if rtype in ('primary', 'secondary'):
            rows_classified.append((idx, rtype, row))

    # Pair primary + secondary
    transactions = []
    i = 0
    while i < len(rows_classified):
        idx1, type1, row1 = rows_classified[i]

        if type1 == 'primary':
            # Look ahead for a secondary row
            secondary = None
            if i + 1 < len(rows_classified):
                idx2, type2, row2 = rows_classified[i + 1]
                if type2 == 'secondary':
                    secondary = row2
                    i += 2
                else:
                    i += 1
            else:
                i += 1

            # Build transaction
            desc1 = _clean_str(row1.iloc[0]) if num_cols > 0 else ''
            desc2 = _clean_str(secondary.iloc[0]) if secondary is not None and num_cols > 0 else ''
            full_desc = f"{desc1} {desc2}".strip()

            # Date Acquired: col 3 if it's a date, otherwise empty
            col3 = _clean_str(row1.iloc[3]) if num_cols > 3 else ''
            date_acquired = col3 if is_date(col3) else ''

            # Date Sold: col 4 of primary row
            date_sold = _clean_str(row1.iloc[4]) if num_cols > 4 else ''

            # Proceeds and Cost (handle merged pattern)
            col5 = row1.iloc[5] if num_cols > 5 else None
            col6 = row1.iloc[6] if num_cols > 6 else None
            proceeds, cost = _split_proceeds_cost(col5, col6)

            # Accrued / Wash Sale (merged col 7)
            col7 = row1.iloc[7] if num_cols > 7 else None
            accrued_wash = parse_accrued_wash_sale(col7)

            # Gain/Loss (col 8) — for validation only (not in Drake output)
            gain_loss = extract_numeric(row1.iloc[8]) if num_cols > 8 else ''

            # Only emit if we have actual financial data
            if proceeds or cost:
                transactions.append({
                    'Description': full_desc,
                    'Date Acquired': date_acquired,
                    'Date Sold': date_sold,
                    'Proceeds': proceeds,
                    'Cost': cost,
                    'Accrued Market Discount': accrued_wash['Accrued Market Discount'],
                    'Wash Sale Loss': accrued_wash['Wash Sale Loss'],
                })
        else:
            # Orphan secondary row — skip
            i += 1

    return transactions


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
