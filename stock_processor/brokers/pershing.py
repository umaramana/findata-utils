"""
Pershing LLC broker processor.

Column layout (0-indexed, 9-col standard):
  0: Disposition/Transaction verb or description prefix
  1: Quantity (Box 1a)
  2: Date Acquired (Box 1b)
  3: Date Sold or Disposed (Box 1c)
  4: Proceeds (Box 1d)
  5: Cost or Other Basis (Box 1e)
  6: D=Market Discount (1f) / W=Wash Sale Loss (1g) — merged marker col (currently empty)
  7: (empty spacer — absent on 8-col sheets)
  8: Realized Gain or (Loss)  [col 7 on 8-col sheets]

Row types:
  description  — col0 starts with "Description (Box 1a):" → set current_description
  transaction  — col0 in {'SELL', 'LIQUIDATION'}, or col0 empty with date+numeric data
  skip         — everything else (headers, footers, subtotals, section totals)

Description is forward-filled across sheets: a stock spanning two pages
carries its description from the last description row on the previous sheet.
"""

import pandas as pd

from utils import extract_numeric, is_date

_DESCRIPTION_PREFIX = 'Description (Box 1a):'
_TRANSACTION_VERBS = {'SELL', 'LIQUIDATION'}


def _classify_row(row):
    """Classify row as: description | transaction | skip."""
    col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
    num_cols = len(row)

    if col0.startswith(_DESCRIPTION_PREFIX):
        return 'description'

    if col0 in _TRANSACTION_VERBS:
        return 'transaction'

    # Empty col0: transaction if date + numeric data present
    if (not col0 and num_cols > 4 and
            is_date(row.iloc[2]) and
            extract_numeric(row.iloc[4]) != ''):
        return 'transaction'

    return 'skip'


def _split_merged_transactions(row, description, num_cols):
    """
    Handle rows where multiple transactions are merged into one cell with \\n.
    Example: Proceeds cell = '66.74 \\n148.24 ' → two separate transactions.
    """
    def split_cell(col_idx):
        val = str(row.iloc[col_idx]).strip() if pd.notna(row.iloc[col_idx]) else ''
        return [v.strip() for v in val.split('\n') if v.strip()]

    dates_acq = split_cell(2)
    dates_sold = split_cell(3)
    proceeds_parts = split_cell(4)
    costs_parts = split_cell(5) if num_cols > 5 else []

    txns = []
    for i in range(len(proceeds_parts)):
        txns.append({
            'Description': description or 'UNKNOWN',
            'Date Acquired': dates_acq[i] if i < len(dates_acq) else dates_acq[-1] if dates_acq else '',
            'Date Sold': dates_sold[i] if i < len(dates_sold) else dates_sold[-1] if dates_sold else '',
            'Proceeds': extract_numeric(proceeds_parts[i]),
            'Cost': extract_numeric(costs_parts[i]) if i < len(costs_parts) else '',
            'Accrued Market Discount': '',
            'Wash Sale Loss': '',
        })
    return txns


def _process_sheet(df, current_description):
    """Process one sheet. Returns (list_of_tx_dicts, updated_description)."""
    rows = []
    num_cols = len(df.columns)

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_type = _classify_row(row)

        if row_type == 'description':
            col0 = str(row.iloc[0]).strip()
            current_description = col0[len(_DESCRIPTION_PREFIX):].strip()

        elif row_type == 'transaction':
            proceeds_raw = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ''
            if '\n' in proceeds_raw:
                rows.extend(_split_merged_transactions(row, current_description, num_cols))
            else:
                rows.append({
                    'Description': current_description or 'UNKNOWN',
                    'Date Acquired': str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else '',
                    'Date Sold': str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else '',
                    'Proceeds': extract_numeric(row.iloc[4]),
                    'Cost': extract_numeric(row.iloc[5]) if num_cols > 5 else '',
                    'Accrued Market Discount': '',
                    'Wash Sale Loss': '',
                })

    return rows, current_description


def process(file_obj):
    """
    Process Pershing LLC transaction file and return standardized DataFrame.

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
        df = excel_file.parse(sheet_name, header=None)
        new_rows, current_description = _process_sheet(df, current_description)
        for row in new_rows:
            row['Source Sheet'] = sheet_name
        all_rows.extend(new_rows)

    if not all_rows:
        return pd.DataFrame()

    return pd.DataFrame(all_rows)
