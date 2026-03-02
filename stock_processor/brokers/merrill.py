"""
Merrill Lynch broker processor.
Handles multiple row patterns from PDF-converted 1099-B:
- Fully merged multi-transaction rows (\n-separated values across all columns)
- Merged first-transaction rows (description + first tx in one row)
- Separate description + transaction rows
- Multi-line descriptions (continuation rows)
- Variable column layouts (date columns may shift position)

Note: PDF conversion can produce a repeating artifact where text from a
page-level element (e.g., "ASML HLDG NV NY REG SHS\n1.0000 Sale\n1.0000 Sale")
bleeds into the first data cell on each page. The description may be inaccurate
in those cases, but the CUSIP (appended to description) is always correct.
"""

import re

import pandas as pd
import numpy as np

from utils import is_date


def process(file_obj):
    """
    Process Merrill Lynch transaction file and return standardized DataFrame.

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
        # Carry description across sheets — stocks can span page boundaries
        # (e.g., EBAY description on Sheet2, its transaction on Sheet3 row 1)
        new_rows, current_description = _process_sheet(df, current_description)
        for row in new_rows:
            row['Source Sheet'] = sheet_name
        all_rows.extend(new_rows)

    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(all_rows)


def _process_sheet(df, current_description):
    """Process a single sheet, returning (transaction_list, updated_description)."""
    rows = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_type = _classify_row(row)

        if row_type == 'skip':
            continue
        elif row_type == 'merged':
            desc, transactions = _process_merged_row(row)
            if desc:
                current_description = desc
            for tx in transactions:
                tx['Description'] = current_description or 'UNKNOWN'
                rows.append(tx)
        elif row_type == 'description':
            current_description = _extract_description(row)
        elif row_type == 'continuation':
            cont_text = _extract_continuation(row)
            if current_description:
                current_description = current_description + ' ' + cont_text
            else:
                current_description = cont_text
        elif row_type == 'transaction':
            tx = _extract_transaction(row)
            tx['Description'] = current_description or 'UNKNOWN'
            rows.append(tx)

    return rows, current_description


def _classify_row(row):
    """Classify a row into its processing type."""
    num_cols = len(row)

    # Get string values for key columns
    col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
    col1 = str(row.iloc[1]).strip() if num_cols > 1 and pd.notna(row.iloc[1]) else ''

    # Build full row text for skip pattern matching
    all_vals = [str(v).strip() if pd.notna(v) else '' for v in row]
    row_text = ' '.join(all_vals).lower()
    # Strip zero-width spaces
    row_text_clean = row_text.replace('\u200b', '').strip()

    # Skip completely empty rows
    if not any(all_vals):
        return 'skip'

    # Skip page headers ("Page", "X of Y")
    if re.search(r'\d+\s+of\s+\d+', row_text_clean):
        return 'skip'

    # Skip form header
    if 'form 1099' in row_text_clean or 'omb no' in row_text_clean:
        return 'skip'

    # Skip column headers (1a., 1b., Description of Property, etc.)
    if '1a.' in row_text_clean or 'description of property' in row_text_clean:
        return 'skip'

    # Skip section/category headers
    section_patterns = [
        'short term capital gains',
        'long term capital gains',
        'covered transactions',
        'net short term',
        'net long term',
        'sales proceeds and net',
        'covered short term gains',
        'covered long term gains',
        'form 8949',
    ]
    if any(p in row_text_clean for p in section_patterns):
        return 'skip'

    # Skip subtotals and totals
    if 'subtotal' in row_text_clean or col1.lower() == 'security subtotal':
        return 'skip'

    # Skip footer/disclaimer text (long explanatory text)
    footer_patterns = [
        'this transaction has been identified',
        'important tax information',
        'furnished to the internal revenue',
        'taxpayers are ultimately',
        'deferred loss amount',
        'please refer to the instructions',
    ]
    if any(p in row_text_clean for p in footer_patterns):
        return 'skip'

    # Skip wash sale code explanation rows: (W)/(B)/(Y) with long text
    if col0 in ['(W)', '(B)', '(Y)'] and len(row_text) > 100:
        return 'skip'

    # Skip continuation of wash sale explanations
    if not col0 and (col1.lower().startswith('sales.') or col1.lower().startswith('sale"')):
        return 'skip'

    # Check for dates and financial data to classify the row
    has_date_in_any_col = False
    has_newline_with_date = False
    has_financial_data = False

    for i in range(num_cols):
        val = str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else ''
        if not val:
            continue

        # For \n-separated values, check individual lines
        lines = [l.strip() for l in val.split('\n') if l.strip()] if '\n' in val else [val]

        # Check for dates
        if any(is_date(l) for l in lines):
            has_date_in_any_col = True
            if '\n' in val:
                has_newline_with_date = True

        # Check for financial data (monetary values in later columns)
        # Must look like money: has decimal point, comma, $, or parentheses
        # This excludes CUSIP numbers (9-digit plain integers like "031162100")
        if i >= 2:
            for line in lines:
                cleaned = line.replace('$', '').replace(',', '').strip()
                if cleaned.startswith('(') and cleaned.endswith(')'):
                    cleaned = cleaned[1:-1]
                if '.' in cleaned or '$' in line or ',' in line:
                    try:
                        float(cleaned)
                        has_financial_data = True
                        break
                    except (ValueError, TypeError):
                        pass

    # Merged row: has \n with dates (either multi or single transaction)
    if has_newline_with_date and has_financial_data:
        return 'merged'

    # Check if any column beyond 0-1 has non-empty data (for desc vs continuation)
    has_data_beyond_col1 = any(
        pd.notna(row.iloc[i]) and str(row.iloc[i]).strip()
        for i in range(2, num_cols)
    )

    # Transaction row: has dates and financial data, no \n merging
    if has_date_in_any_col and has_financial_data:
        return 'transaction'

    # Description row: has text, plus data in cols 2+ (e.g., CUSIP info)
    if col0 and not has_date_in_any_col and has_data_beyond_col1:
        return 'description'

    # Continuation row: text only in cols 0-1, nothing beyond
    if col0 and not has_financial_data:
        return 'continuation'

    return 'skip'


def _find_date_columns(row):
    """
    Find the Date Acquired and Date Sold column indices by looking for
    MM/DD/YY date patterns. For \n-separated values, checks lines after
    the first (which may be non-date text like CUSIP info).

    Returns (date_acquired_idx, date_sold_idx) or (None, None).
    """
    num_cols = len(row)
    date_cols = []

    for i in range(num_cols):
        val = str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else ''
        if not val:
            continue

        if '\n' in val:
            lines = [l.strip() for l in val.split('\n') if l.strip()]
            # Check if any line (preferring lines after the first) is a date
            if any(is_date(l) for l in lines):
                date_cols.append(i)
        elif is_date(val):
            date_cols.append(i)

        if len(date_cols) == 2:
            break

    if len(date_cols) == 2:
        return date_cols[0], date_cols[1]
    return None, None


def _process_merged_row(row):
    """
    Process a row with merged data (multi or single transaction).
    Uses date pattern detection to find column positions.

    Returns (description, [transaction_dicts]).
    """
    num_cols = len(row)
    da_idx, ds_idx = _find_date_columns(row)

    if da_idx is None or ds_idx is None:
        return None, []

    # Build description from columns before the date columns
    desc_parts = []
    for i in range(da_idx):
        val = str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else ''
        if not val:
            continue
        # Take only the first line (before any \n)
        first_line = val.split('\n')[0].strip()
        # Skip numeric values (quantities) and action keywords
        if first_line and first_line.lower() not in ('sale', 'nan', 'none', ''):
            if not re.match(r'^\d+\.?\d*$', first_line):
                desc_parts.append(first_line)

    description = ' '.join(desc_parts) if desc_parts else None

    # Extract dates from the date columns
    da_val = str(row.iloc[da_idx]) if pd.notna(row.iloc[da_idx]) else ''
    ds_val = str(row.iloc[ds_idx]) if pd.notna(row.iloc[ds_idx]) else ''

    da_lines = [l.strip() for l in da_val.split('\n') if l.strip()]
    ds_lines = [l.strip() for l in ds_val.split('\n') if l.strip()]

    # Filter to only date-formatted lines
    dates_acquired = [l for l in da_lines if is_date(l)]
    dates_sold = [l for l in ds_lines if is_date(l)]

    # Financial columns start after Date Sold
    fin_start = ds_idx + 1
    fin_col_names = ['Proceeds', 'Cost', 'Accrued Market Discount', 'Wash Sale Loss']

    fin_data = {}
    for j, name in enumerate(fin_col_names):
        col_idx = fin_start + j
        if col_idx < num_cols and pd.notna(row.iloc[col_idx]):
            val = str(row.iloc[col_idx]).strip()
            if '\n' in val:
                fin_data[name] = [v.strip() for v in val.split('\n') if v.strip()]
            else:
                fin_data[name] = [val] if val else []
        else:
            fin_data[name] = []

    # Determine number of transactions
    num_txns = max(len(dates_acquired), len(dates_sold), 1)

    transactions = []
    for i in range(num_txns):
        tx = {
            'Date Acquired': dates_acquired[i] if i < len(dates_acquired) else '',
            'Date Sold': dates_sold[i] if i < len(dates_sold) else '',
        }
        for name in fin_col_names:
            values = fin_data[name]
            if i < len(values):
                tx[name] = values[i]
            elif len(values) == 1:
                tx[name] = values[0]  # Single value applies to all transactions
            else:
                tx[name] = ''
        transactions.append(tx)

    return description, transactions


def _extract_description(row):
    """
    Extract description from a description-only row.
    Takes text from col 0 (first line if \n-separated) + col 1 if present.
    """
    num_cols = len(row)
    parts = []

    col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
    if col0:
        # Take first line only (strip any merged quantity/action text)
        first_line = col0.split('\n')[0].strip()
        if first_line:
            parts.append(first_line)

    col1 = str(row.iloc[1]).strip() if num_cols > 1 and pd.notna(row.iloc[1]) else ''
    if col1 and col1.lower() not in ('nan', 'none', '', 'sale'):
        parts.append(col1)

    return ' '.join(parts) if parts else None


def _extract_continuation(row):
    """Extract continuation text from a continuation row."""
    num_cols = len(row)
    parts = []

    col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
    if col0 and col0.lower() not in ('nan', 'none'):
        parts.append(col0)

    col1 = str(row.iloc[1]).strip() if num_cols > 1 and pd.notna(row.iloc[1]) else ''
    if col1 and col1.lower() not in ('nan', 'none', ''):
        parts.append(col1)

    return ' '.join(parts)


def _extract_transaction(row):
    """
    Extract transaction data from a regular (non-merged) transaction row.
    Finds date columns dynamically using date pattern detection.
    """
    num_cols = len(row)

    # Find the two date columns
    date_cols = []
    for i in range(num_cols):
        val = str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else ''
        if is_date(val):
            date_cols.append(i)
        if len(date_cols) == 2:
            break

    if len(date_cols) == 2:
        da_idx, ds_idx = date_cols
    else:
        # Fallback: assume cols 2, 3 for dates
        da_idx, ds_idx = 2, 3

    # Financial columns start after Date Sold
    fin_start = ds_idx + 1
    fin_col_names = ['Proceeds', 'Cost', 'Accrued Market Discount', 'Wash Sale Loss']

    tx = {
        'Date Acquired': str(row.iloc[da_idx]).strip() if da_idx < num_cols and pd.notna(row.iloc[da_idx]) else '',
        'Date Sold': str(row.iloc[ds_idx]).strip() if ds_idx < num_cols and pd.notna(row.iloc[ds_idx]) else '',
    }

    for j, name in enumerate(fin_col_names):
        col_idx = fin_start + j
        if col_idx < num_cols and pd.notna(row.iloc[col_idx]):
            tx[name] = str(row.iloc[col_idx]).strip()
        else:
            tx[name] = ''

    return tx
