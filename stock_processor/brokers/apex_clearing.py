"""
Apex Clearing broker processor.

Handles:
- Two-row-per-transaction pattern: description row (security name), then data row
- Multi-sheet: transactions span across sheets, description carries across boundaries
- Variable column count: Sheet1 may have 9 cols (with Additional Notes), Sheet2 has 8
- YYYY-MM-DD date format (ISO)
- Column 3 is an empty spacer between Proceeds and Date Acquired

Column layout (0-indexed):
  0: Date Sold
  1: Quantity
  2: Proceeds (1d)
  3: (empty spacer)
  4: Date Acquired (1b)
  5: Cost or Other Basis (1e)
  6: Wash Sale Loss Disallowed (1g) / Accrued Market Discount (1f) — merged
  7: Gain/Loss
  8: Additional Notes (only on some sheets)
"""

import re

import numpy as np
import pandas as pd


_DATE_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')

_SKIP_KEYWORDS = [
    'proceeds from broker',
    'form 1099',
    'omb no',
    'page',
    'short-term',
    'long-term',
    'date sold',
    'quantity',
    'net proceeds',
    'cost or other',
    'wash sale',
    'gain or loss',
    'additional info',
    'important tax',
    'furnished to the internal',
    'taxpayers are',
]

_HEADER_KEYWORDS = ['date sold', 'quantity', 'proceeds', 'cost', 'gain']


def _is_date(val):
    """Check if value matches YYYY-MM-DD pattern."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    return bool(_DATE_RE.match(str(val).strip()))


def _is_numeric(val):
    """Check if value looks like a number."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    cleaned = str(val).replace('$', '').replace(',', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = cleaned[1:-1]
    try:
        float(cleaned)
        return True
    except (ValueError, TypeError):
        return False


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


def _parse_accrued_wash_sale(val):
    """
    Parse the merged Accrued/Wash Sale column (col 6).

    For now: treats any non-zero value as Wash Sale Loss.
    Markers "(M)" and "(D)" handling to be added when non-zero test data available.

    Returns dict with 'Accrued Market Discount' and 'Wash Sale Loss'.
    """
    numeric = _extract_numeric(val)
    if not numeric:
        return {'Accrued Market Discount': '', 'Wash Sale Loss': ''}
    try:
        if float(numeric) == 0:
            return {'Accrued Market Discount': '', 'Wash Sale Loss': ''}
    except (ValueError, TypeError):
        pass
    return {'Accrued Market Discount': '', 'Wash Sale Loss': numeric}


def _classify_row(row):
    """
    Classify a row as: skip | description | transaction | totals.

    - description: col 0 has text (security name), no date in col 0
    - transaction: col 0 has a YYYY-MM-DD date, numeric data present
    - totals: no date, but numeric data in proceeds/cost columns
    - skip: headers, footers, empty rows
    """
    num_cols = len(row)
    vals = [str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else '' for i in range(num_cols)]
    non_empty = [v for v in vals if v]

    if not non_empty:
        return 'skip'

    col0 = vals[0]
    row_text = ' '.join(vals).lower()

    # Skip header/footer keyword matches
    if any(kw in row_text for kw in _SKIP_KEYWORDS):
        return 'skip'

    # Skip column header rows (2+ header keywords)
    if sum(1 for kw in _HEADER_KEYWORDS if kw in row_text) >= 2:
        return 'skip'

    # Skip page headers ("Page X of Y")
    if re.search(r'page\s+\d+\s+of\s+\d+', row_text):
        return 'skip'

    # Transaction row: col 0 has a date
    if _is_date(col0):
        # Verify it has numeric data (proceeds or cost)
        if num_cols > 2 and _is_numeric(row.iloc[2]):
            return 'transaction'

    # Totals row: no date in col 0, but numeric in proceeds+cost columns
    if not _is_date(col0) and not col0:
        if num_cols > 5 and _is_numeric(row.iloc[2]) and _is_numeric(row.iloc[5]):
            return 'totals'

    # Description row: col 0 has text, not a date, not all-numeric
    if col0 and not _is_date(col0):
        # Only one non-empty cell (or two with col 1), rest empty → description
        non_empty_beyond_1 = any(
            vals[i] for i in range(2, num_cols) if i < len(vals)
        )
        if not non_empty_beyond_1:
            return 'description'

    return 'skip'


def _process_sheet(df, current_description):
    """Process one sheet. Returns (list_of_tx_dicts, updated_description)."""
    rows = []
    num_cols = len(df.columns)

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_type = _classify_row(row)

        if row_type == 'skip' or row_type == 'totals':
            continue

        elif row_type == 'description':
            current_description = str(row.iloc[0]).strip()

        elif row_type == 'transaction':
            accrued_wash = _parse_accrued_wash_sale(
                row.iloc[6] if num_cols > 6 else None
            )
            tx = {
                'Description': current_description or 'UNKNOWN',
                'Date Sold': str(row.iloc[0]).strip(),
                'Date Acquired': str(row.iloc[4]).strip() if num_cols > 4 and pd.notna(row.iloc[4]) else '',
                'Proceeds': _extract_numeric(row.iloc[2]) if num_cols > 2 else '',
                'Cost': _extract_numeric(row.iloc[5]) if num_cols > 5 else '',
                'Accrued Market Discount': accrued_wash['Accrued Market Discount'],
                'Wash Sale Loss': accrued_wash['Wash Sale Loss'],
            }
            # Validate: Gain/Loss must be present (col 7) for real transaction rows
            if num_cols > 7 and _is_numeric(row.iloc[7]):
                rows.append(tx)

    return rows, current_description


def process(file_obj):
    """
    Process Apex Clearing transaction file and return standardized DataFrame.

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
