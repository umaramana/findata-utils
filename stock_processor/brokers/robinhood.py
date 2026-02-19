"""
Robinhood broker processor.
Handles:
- Multi-row headers at different positions per sheet
- Parent-child structure (stock description row + transaction rows)
- Wash sale notation: "156.26 W" -> 156.26
- "Various" date handling
- Security subtotal and summary rows to skip
- (cont'd) notation for continued stocks from previous page

NEW implementation based on TECHNICAL_SPEC.md
"""

import pandas as pd
import numpy as np
import re


def process(file_obj):
    """
    Process Robinhood transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Description, Date Acquired, Date Sold,
                               Proceeds, Cost, Accrued Market Discount,
                               Wash Sale Loss, Source Sheet
    """
    excel_file = pd.ExcelFile(file_obj)
    all_processed_dfs = []

    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(file_obj, sheet_name=sheet_name)
        processed_df = _process_sheet(df, sheet_name)

        if not processed_df.empty:
            all_processed_dfs.append(processed_df)

    if not all_processed_dfs:
        return pd.DataFrame()

    combined_df = pd.concat(all_processed_dfs, ignore_index=True)
    return combined_df


def _process_sheet(df, sheet_name):
    """Process a single Robinhood sheet."""
    if df.empty:
        return pd.DataFrame()

    # Find the multi-row header
    header_info = _detect_header(df)
    if header_info is None:
        return pd.DataFrame()

    header_end_row, column_mapping = header_info

    # Extract data rows (after header)
    data_df = df.iloc[header_end_row + 1:].reset_index(drop=True)

    if data_df.empty:
        return pd.DataFrame()

    # Process transactions with parent-child structure
    transactions = _extract_transactions(data_df, column_mapping)

    if not transactions:
        return pd.DataFrame()

    result_df = pd.DataFrame(transactions)
    result_df['Source Sheet'] = sheet_name

    return result_df


def _detect_header(df):
    """
    Detect the multi-row header in Robinhood files.
    Headers span 2-3 rows and contain keywords like:
    - "1a- Description of property/CUSIP/Symbol"
    - "1c- Date sold or disposed"
    - "1b- Date acquired"
    - "1d- Proceeds"
    - "1e- Cost or other basis"
    - "1g- Wash sale loss disallowed"

    Returns: (header_end_row, column_mapping) or None
    """
    # Look for the specific "1a- Description" row which marks the start of headers
    header_start = None
    header_end = None

    for idx, row in df.iterrows():
        row_text = ' '.join([str(x).lower() if not pd.isna(x) else '' for x in row.values])

        # Look for "1a- description" which is the definitive header start
        if '1a-' in row_text and 'description' in row_text:
            header_start = idx
            continue

        # Once we found header start, look for the row with "sold" and "disposed"
        # which marks the end of the multi-row header
        if header_start is not None:
            if ('sold' in row_text or 'disposed' in row_text) and 'quantity' in row_text:
                header_end = idx
                break

    # Fallback: if we didn't find "1a-", look for row with many column keywords
    if header_start is None:
        header_keywords = ['quantity', '1b-', '1c-', '1d-', '1e-', 'proceeds', 'cost', 'basis']
        for idx, row in df.iterrows():
            row_text = ' '.join([str(x).lower() if not pd.isna(x) else '' for x in row.values])
            match_count = sum(1 for kw in header_keywords if kw in row_text)
            if match_count >= 4:
                header_start = idx
                header_end = idx
                break

    if header_start is None:
        return None

    if header_end is None:
        header_end = header_start

    # Build column mapping by analyzing header rows
    column_mapping = _build_column_mapping(df, header_start, header_end)

    return header_end, column_mapping


def _build_column_mapping(df, header_start, header_end):
    """
    Build column mapping from multi-row header.
    Combines text from header rows to determine column purposes.

    Robinhood layout (typical):
    Col 0: Date Sold (1c)
    Col 1: Quantity
    Col 2: Proceeds (1d)
    Col 3: Date Acquired (1b)
    Col 4: Cost (1e)
    Col 5: Wash Sale (1g)
    Col 6: Gain/Loss
    Col 7: Additional Info
    """
    num_cols = len(df.columns)
    col_texts = [''] * num_cols

    # Combine text from all header rows
    for idx in range(header_start, header_end + 1):
        row = df.iloc[idx]
        for col_idx, val in enumerate(row):
            if not pd.isna(val) and str(val).strip():
                col_texts[col_idx] += ' ' + str(val).strip()

    # Clean up
    col_texts = [t.strip().lower() for t in col_texts]

    # Create mapping - start with positional defaults (known Robinhood layout)
    mapping = {
        'date_sold_col': 0,      # Col 0: Date sold/disposed
        'quantity_col': 1,       # Col 1: Quantity
        'proceeds_col': 2,       # Col 2: Proceeds
        'date_acquired_col': 3,  # Col 3: Date acquired
        'cost_col': 4,           # Col 4: Cost/basis
        'accrued_market_discount_col': None,  # Col for 1f: Accrued market discount
        'wash_sale_col': 5,      # Col 5: Wash sale
        'description_col': None,
        'additional_info_col': 7
    }

    # Override with detected values if we find clear indicators
    for col_idx, text in enumerate(col_texts):
        # Use specific IRS codes (1a-, 1b-, etc.) for more reliable detection
        if '1c-' in text or ('sold' in text and 'disposed' in text):
            mapping['date_sold_col'] = col_idx
        elif 'quantity' in text and '1' not in text:
            mapping['quantity_col'] = col_idx
        elif '1d-' in text or ('proceeds' in text and 'reported' not in text):
            mapping['proceeds_col'] = col_idx
        elif '1b-' in text or ('date' in text and 'acquired' in text):
            mapping['date_acquired_col'] = col_idx
        elif '1e-' in text or ('cost' in text and 'basis' in text):
            mapping['cost_col'] = col_idx
        elif '1f-' in text or ('accrued' in text and 'market' in text and 'discount' in text):
            mapping['accrued_market_discount_col'] = col_idx
        elif '1g-' in text or ('wash' in text and 'sale' in text):
            mapping['wash_sale_col'] = col_idx
        elif 'additional' in text and 'info' in text:
            mapping['additional_info_col'] = col_idx

    return mapping


def _extract_transactions(df, column_mapping):
    """
    Extract transactions using parent-child structure.
    - Parent rows: Stock description (contains CUSIP pattern)
    - Child rows: Transaction data with dates
    """
    transactions = []
    current_stock_description = None

    for idx, row in df.iterrows():
        row_values = [str(val).strip() if not pd.isna(val) else '' for val in row.values]
        row_text = ' '.join(row_values).lower()

        # Skip footer/summary rows
        if _is_footer_row(row_text):
            continue

        # Skip security subtotal rows
        if _is_subtotal_row(row_text):
            continue

        # Skip total rows
        if _is_total_row(row_text):
            continue

        # Check if this is a stock description row (contains CUSIP)
        if _is_stock_description_row(row_values):
            current_stock_description = _extract_stock_description(row_values)
            continue

        # Check if this is a transaction row (has date in date_sold column)
        date_sold_col = column_mapping['date_sold_col']
        date_sold_val = row_values[date_sold_col] if date_sold_col < len(row_values) else ''

        if _is_date_value(date_sold_val) and current_stock_description:
            transaction = _extract_transaction_data(row_values, column_mapping, current_stock_description)
            if transaction:
                transactions.append(transaction)

    return transactions


def _is_footer_row(row_text):
    """Check if row is a footer/disclaimer row."""
    footer_patterns = [
        'important tax information',
        'furnished to the internal revenue service',
        'irs determines',
        'negligence penalty',
        'taxpayers are ultimately responsible'
    ]
    return any(pattern in row_text for pattern in footer_patterns)


def _is_subtotal_row(row_text):
    """Check if row is a security subtotal row."""
    return 'security total' in row_text or 'security subtotal' in row_text


def _is_total_row(row_text):
    """Check if row is a totals row."""
    # "Totals :" at start of row
    return row_text.strip().startswith('totals')


def _is_stock_description_row(row_values):
    """
    Check if row is a stock description row.
    Contains CUSIP pattern or stock name pattern.
    """
    row_text = ' '.join(row_values).upper()

    # CUSIP pattern
    if 'CUSIP:' in row_text or 'CUSIP :' in row_text:
        return True

    # Stock name patterns with company suffixes
    if re.search(r'\b(INC|CORP|LTD|PLC|COMPANY|CO)\b.*\b(COMMON|STOCK|CLASS)\b', row_text):
        return True

    # Pattern: "APPLE INC. COMMON STOCK / CUSIP:"
    if re.search(r'[A-Z]{2,}\s+(INC|CORP)\.?\s+(COMMON\s+)?STOCK', row_text):
        return True

    return False


def _extract_stock_description(row_values):
    """Extract stock description from row, cleaning up formatting."""
    # Find the first non-empty substantial value
    for val in row_values:
        val = str(val).strip()
        if len(val) > 10 and ('CUSIP' in val.upper() or 'STOCK' in val.upper() or 'INC' in val.upper()):
            # Clean up the description
            desc = val.replace('(cont\'d)', '').replace("(cont'd)", '').strip()
            # Remove trailing "/ Symbol:" if present
            desc = re.sub(r'/\s*Symbol:\s*$', '', desc).strip()
            return desc

    # Fallback: join non-empty values
    non_empty = [v for v in row_values if v and v.lower() not in ['nan', 'none', '']]
    if non_empty:
        return ' '.join(non_empty[:2])

    return None


def _is_date_value(value):
    """Check if value is a date."""
    if not value or value.lower() in ['nan', 'none', '']:
        return False

    # Check for Various
    if value.upper() == 'VARIOUS':
        return True

    # Date patterns
    date_patterns = [
        r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$',  # MM/DD/YYYY or MM/DD/YY
        r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}$',     # YYYY-MM-DD
    ]

    for pattern in date_patterns:
        if re.match(pattern, value.strip()):
            return True

    return False


def _extract_transaction_data(row_values, column_mapping, stock_description):
    """Extract transaction data from a transaction row."""
    def get_val(col_key):
        col_idx = column_mapping.get(col_key)
        if col_idx is not None and col_idx < len(row_values):
            val = row_values[col_idx]
            if val.lower() in ['nan', 'none', '', '...']:
                return ''
            return val
        return ''

    date_sold = get_val('date_sold_col')
    date_acquired = get_val('date_acquired_col')
    proceeds = get_val('proceeds_col')
    cost = get_val('cost_col')
    accrued_mkt_disc = get_val('accrued_market_discount_col')
    wash_sale = get_val('wash_sale_col')

    # Parse wash sale - handle "156.26 W" format
    wash_sale_amount = _parse_wash_sale(wash_sale)

    # Clean numeric values
    proceeds_clean = _clean_currency(proceeds)
    cost_clean = _clean_currency(cost)
    accrued_mkt_disc_clean = _clean_currency(accrued_mkt_disc)

    return {
        'Description': stock_description,
        'Date Acquired': date_acquired if date_acquired else '',
        'Date Sold': date_sold if date_sold else '',
        'Proceeds': proceeds_clean,
        'Cost': cost_clean,
        'Accrued Market Discount': accrued_mkt_disc_clean,
        'Wash Sale Loss': wash_sale_amount
    }


def _parse_wash_sale(value):
    """
    Parse wash sale value.
    "156.26 W" -> "156.26"
    "2,184.79 W" -> "2184.79"
    "..." or "--" -> ""
    """
    if not value or value.lower() in ['nan', 'none', '', '...', '--']:
        return ''

    # Remove "W" suffix and any whitespace
    cleaned = re.sub(r'\s*W\s*$', '', value, flags=re.IGNORECASE)

    # Remove commas
    cleaned = cleaned.replace(',', '')

    # Check if it's a valid number
    try:
        float(cleaned)
        return cleaned
    except (ValueError, TypeError):
        return ''


def _clean_currency(value):
    """Clean currency value - remove $ and commas."""
    if not value or value.lower() in ['nan', 'none', '', '...', '--']:
        return ''

    # Remove $ and commas
    cleaned = re.sub(r'[\$,]', '', value)

    # Check if valid number
    try:
        float(cleaned)
        return cleaned
    except (ValueError, TypeError):
        return value
