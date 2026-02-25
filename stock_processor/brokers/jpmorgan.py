"""
JP Morgan broker processor.

Handles:
- Excel files converted from PDF via Excel's built-in import (not PDF24)
- Multi-row repeating headers (CUSIP / Box 1a markers) — skip
- Transaction rows: dates in cols 5 AND 6
- Description-only rows: text in cols 0-3, no dates — carry forward
- Multi-column description: col 0 + col 1 combined on transaction rows
- Subtotal and grand total rows — skip
- Wash sales with $0.00 Gain/Loss (valid, not empty-cell-collapse)

Column layout (0-indexed, cols 13-35 are empty padding):
  0: Type prefix / overflow     ("PUT", "PALANTIR", or empty)
  1: Description / ticker       ("CALL NBIS", "NEBIUS GROUP N V")
  2: CUSIP / desc overflow      ("45891", "TECHNOLOGIES INC CL")
  3: CUSIP cont / "Subtotals"   ("75", "Subtotals")
  4: Quantity Sold
  5: Date Acquired (1b)         MM/DD/YYYY
  6: Date Sold (1c)             MM/DD/YYYY
  7: Proceeds (1d)              "$602.61"
  8: Cost (1e)                  "$1,245.39"
  9: Accrued Mkt Discount (1f)  "$0.00"
 10: Wash Sale Loss (1g)        "$0.00", "$8.02"
 11: Gain/Loss
 12: Additional Info
"""

import re

import numpy as np
import pandas as pd


_DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')

_HEADER_KEYWORDS = ['cusip', '(box 1a)', '(box 1b)', '(box 1c)', '(box 1d)',
                     '(box 1e)', '(box 1f)', '(box 1g)', 'description of property',
                     'quantity sold', 'date acquired', 'date sold']

_SKIP_KEYWORDS = ['items - total', 'grand total']

# Excel auto-generated column headers from PDF import
_EXCEL_COL_RE = re.compile(r'^column\d+$', re.IGNORECASE)


def _is_date(val):
    """Check if value matches MM/DD/YYYY date pattern."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    return bool(_DATE_RE.match(str(val).strip()))


def _extract_numeric(val):
    """Return cleaned numeric string, or empty string if not valid."""
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


def _cell_text(row, col_idx):
    """Get stripped string from a row cell, or '' if empty/NaN."""
    if col_idx >= len(row):
        return ''
    val = row.iloc[col_idx]
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ''
    return str(val).strip()


def _classify_row(row):
    """
    Classify a row as: skip | transaction | description | subtotal.

    - skip: empty, header rows (CUSIP/Box 1a), grand total, page footers
    - transaction: dates in cols 5 AND 6
    - description: text in cols 0-3, no dates in cols 5-6
    - subtotal: "Subtotals" in col 3
    """
    num_cols = len(row)
    vals = [_cell_text(row, i) for i in range(min(num_cols, 13))]
    non_empty = [v for v in vals if v]

    if not non_empty:
        return 'skip'

    row_text = ' '.join(vals).lower()

    # Skip grand total rows
    if any(kw in row_text for kw in _SKIP_KEYWORDS):
        return 'skip'

    # Skip header rows (CUSIP or Box 1a markers)
    if any(kw in row_text for kw in _HEADER_KEYWORDS):
        return 'skip'

    # Skip Excel auto-generated column header rows ("Column1", "Column2", ...)
    if any(_EXCEL_COL_RE.match(v) for v in vals if v):
        return 'skip'

    # Subtotal rows
    if vals[3].lower() == 'subtotals' if len(vals) > 3 else False:
        return 'subtotal'

    # Transaction: dates in cols 5 AND 6
    has_date_acq = num_cols > 5 and _is_date(row.iloc[5])
    has_date_sold = num_cols > 6 and _is_date(row.iloc[6])
    if has_date_acq and has_date_sold:
        return 'transaction'

    # Description: text in cols 0-3, no dates
    has_text = any(vals[i] for i in range(min(4, len(vals))))
    if has_text:
        return 'description'

    return 'skip'


def _build_description(row):
    """Build description from cols 0 + 1 on a transaction row."""
    parts = []
    for i in range(2):
        t = _cell_text(row, i)
        if t:
            parts.append(t)
    return ' '.join(parts) if parts else ''


def _build_full_description(row):
    """Build description from cols 0-3 on a description-only row."""
    parts = []
    for i in range(4):
        t = _cell_text(row, i)
        if t:
            parts.append(t)
    return ' '.join(parts) if parts else ''


def _process_sheet(df, current_description):
    """
    Process one sheet. Returns (list_of_tx_dicts, updated_description).

    Description logic:
    - Transaction row with text in cols 0+1: use that text, update current_description
    - Transaction row with empty cols 0+1: inherit current_description
    - Description-only row: append text to the PREVIOUS transaction's description,
      and update current_description for future empty-description rows
    """
    rows = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_type = _classify_row(row)

        if row_type in ('skip', 'subtotal'):
            continue

        elif row_type == 'description':
            desc_text = _build_full_description(row)
            if desc_text:
                # Append to previous transaction's description (retroactive)
                if rows:
                    rows[-1]['Description'] += ' ' + desc_text
                # Update current_description for future rows
                current_description = desc_text

        elif row_type == 'transaction':
            tx_desc = _build_description(row)
            if tx_desc:
                # Transaction has its own description — use it
                full_desc = tx_desc
                current_description = tx_desc
            else:
                # No description on this row — inherit from current
                full_desc = current_description or 'UNKNOWN'

            # Accrued (col 9) and Wash Sale (col 10) — normal position.
            # On options rows (expiry/strike in cols 2-3), these shift to cols 13-14.
            accrued = _extract_numeric(row.iloc[9]) if len(row) > 9 else ''
            wash = _extract_numeric(row.iloc[10]) if len(row) > 10 else ''
            if not accrued and not wash and len(row) > 14:
                accrued = _extract_numeric(row.iloc[13])
                wash = _extract_numeric(row.iloc[14])

            tx = {
                'Description': full_desc,
                'Date Acquired': _cell_text(row, 5),
                'Date Sold': _cell_text(row, 6),
                'Proceeds': _extract_numeric(row.iloc[7]) if len(row) > 7 else '',
                'Cost': _extract_numeric(row.iloc[8]) if len(row) > 8 else '',
                'Accrued Market Discount': accrued,
                'Wash Sale Loss': wash,
            }
            rows.append(tx)

    return rows, current_description


def process(file_obj):
    """
    Process JP Morgan transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Description, Date Acquired, Date Sold,
                               Proceeds, Cost, Accrued Market Discount,
                               Wash Sale Loss, Source Sheet
    """
    excel_file = pd.ExcelFile(file_obj)
    all_rows = []
    current_description = None

    for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name, header=None, dtype=str)
        new_rows, current_description = _process_sheet(df, current_description)
        for row in new_rows:
            row['Source Sheet'] = sheet_name
        all_rows.extend(new_rows)

    if not all_rows:
        return pd.DataFrame()

    return pd.DataFrame(all_rows)
