"""
Morgan Stanley broker processor.

Handles:
- Forward-fill description from stock name rows (col 0 is empty on transaction rows)
- Repeated column header rows (skip)
- Section header rows (single populated cell — skip)
- Subtotal/total rows (filter)
- Col 9 = Fed Tax Withheld (PDF24 merged col 8/9 header artifact)

Column layout (0-indexed):
  0: Description (empty on transaction rows — forward-filled from stock name row)
  1: Quantity
  2: Date Acquired
  3: Date Sold
  4: Proceeds
  5: Cost or Other Basis
  6: Accrued Market Discount   (optional)
  7: Wash Sale Loss Disallowed (optional)
  8: Gain/(Loss)
  9: Federal Income Tax Withheld

Stock name rows: col 0 has company name + CUSIP/Symbol keywords in other cols.
Section headers: only one non-empty cell across the entire row — skip.
"""

import re

import numpy as np
import pandas as pd


_DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')

_SKIP_KEYWORDS = [
    'security subtotal',
    'total short term',
    'total long term',
    'total covered',
    'total noncovered',
    'grand total',
    'continued on next page',
]

# If a row contains 2+ of these keywords it's a column header row
_HEADER_KEYWORDS = [
    'description',
    'date acquired',
    'date sold',
    'proceeds',
    'cost or other basis',
]

_STOCK_ID_KEYWORDS = ['cusip', 'symbol']


def _is_date(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    s = str(val).strip()
    return bool(_DATE_RE.match(s)) or s.upper() == 'VARIOUS'


def _is_numeric(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    cleaned = str(val).replace('$', '').replace(',', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        float(cleaned)
        return True
    except (ValueError, TypeError):
        return False


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


def _classify_row(row):
    """Classify a row as: skip | stock_name | transaction."""
    num_cols = len(row)
    vals = [str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else '' for i in range(num_cols)]
    non_empty = [v for v in vals if v]

    # Empty row
    if not non_empty:
        return 'skip'

    col0 = vals[0]
    row_text = ' '.join(vals).lower()

    # Subtotal / total rows
    if any(kw in row_text for kw in _SKIP_KEYWORDS):
        return 'skip'

    # Column header rows (2+ header keywords present)
    if sum(1 for kw in _HEADER_KEYWORDS if kw in row_text) >= 2:
        return 'skip'

    # Section header: exactly one non-empty cell across the whole row
    if len(non_empty) == 1:
        return 'skip'

    # Stock name row: col 0 has text AND CUSIP/Symbol appears somewhere in the row
    if col0 and any(kw in row_text for kw in _STOCK_ID_KEYWORDS):
        return 'stock_name'

    # Transaction row: valid dates in cols 2 & 3, numeric value in col 4
    if num_cols > 4:
        if (_is_date(row.iloc[2]) and
                _is_date(row.iloc[3]) and
                _is_numeric(row.iloc[4])):
            return 'transaction'

    return 'skip'


def _process_sheet(df, current_description):
    """Process one sheet. Returns (list_of_tx_dicts, updated_description)."""
    rows = []
    num_cols = len(df.columns)

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_type = _classify_row(row)

        if row_type == 'skip':
            continue

        elif row_type == 'stock_name':
            current_description = str(row.iloc[0]).strip()

        elif row_type == 'transaction':
            tx = {
                'Description': current_description or 'UNKNOWN',
                'Date Acquired': str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else '',
                'Date Sold': str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else '',
                'Proceeds': _extract_numeric(row.iloc[4]),
                'Cost': _extract_numeric(row.iloc[5]) if num_cols > 5 else '',
                'Accrued Market Discount': _extract_numeric(row.iloc[6]) if num_cols > 6 else '',
                'Wash Sale Loss': _extract_numeric(row.iloc[7]) if num_cols > 7 else '',
                'Fed Tax Withheld': _extract_numeric(row.iloc[9]) if num_cols > 9 else '',
            }
            rows.append(tx)

    return rows, current_description


def process(file_obj):
    """
    Process Morgan Stanley transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Description, Date Acquired, Date Sold,
                               Proceeds, Cost, Accrued Market Discount,
                               Wash Sale Loss, Fed Tax Withheld, Source Sheet
    """
    excel_file = pd.ExcelFile(file_obj)
    all_rows = []
    current_description = None

    for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name, header=None)
        new_rows, current_description = _process_sheet(df, current_description)
        for row in new_rows:
            row['Source Sheet'] = sheet_name
        all_rows.extend(new_rows)

    if not all_rows:
        return pd.DataFrame()

    return pd.DataFrame(all_rows)
