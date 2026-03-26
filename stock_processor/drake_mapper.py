"""
Drake Mapper Module.
Maps broker-specific DataFrames to Drake tax software import format.
Outputs all 15 Drake columns (up to 7 populated, 8 empty).
"""

import pandas as pd
import numpy as np


# Drake template column order
DRAKE_COLUMNS = [
    'TSJ',
    'F',
    'State',
    'City',
    'Form 8949 Check Box',
    'Desc',
    'Date Acquired',
    'Date Sold',
    'Type',
    'Ordinary',
    'Proceeds',
    'Cost',
    'AMT Cost Basis',
    'Accrued Discount',
    'Wash Sale Loss'
]

# Columns that should be populated
REQUIRED_COLUMNS = ['Desc', 'Date Acquired', 'Date Sold', 'Proceeds', 'Cost', 'Wash Sale Loss']

# Column mappings from broker format to Drake format
BROKER_COLUMN_MAPPINGS = {
    'fidelity': {
        # After Fidelity processing, the action column contains the stock description
        'Action': 'Desc',
        '1b Date Acquired': 'Date Acquired',
        '1b Date\nAcquired': 'Date Acquired',
        '1c Date Sold or Disposed': 'Date Sold',
        '1c Date Sold\nor Disposed': 'Date Sold',
        '1d Proceeds': 'Proceeds',
        '1e Cost or Other Basis (b)': 'Cost',
        '1e Cost or\nOther Basis (b)': 'Cost',
        '1f Accrued Market Discount': 'Accrued Discount',
        '1f Accrued Market\nDiscount': 'Accrued Discount',
        '1f Accrued\nMarket Discount': 'Accrued Discount',
        '1f Accrued\nMarket': 'Accrued Discount',
        '1f Accrued Market': 'Accrued Discount',
        'Accrued Market Discount': 'Accrued Discount',
        '1g Wash Sale Loss': 'Wash Sale Loss',
        '1g Wash Sale\nLoss': 'Wash Sale Loss',
        # Handle variations
        'Wash Sale Loss': 'Wash Sale Loss',
        '1g Wash Sale Disallowed': 'Wash Sale Loss'
    },
    'charles_schwab': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Accrued Market Discount': 'Accrued Discount',
        'Wash Sale Loss': 'Wash Sale Loss',
    },
    'robinhood': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Accrued Market Discount': 'Accrued Discount',
        'Wash Sale Loss': 'Wash Sale Loss'
    },
    'merrill': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Accrued Market Discount': 'Accrued Discount',
        'Wash Sale Loss': 'Wash Sale Loss'
    },
    'morgan_stanley': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Accrued Market Discount': 'Accrued Discount',
        'Wash Sale Loss': 'Wash Sale Loss'
    },
    'csv_betterment': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Wash Sale Loss': 'Wash Sale Loss',
        'Type': 'Type',
    },
    'apex_clearing': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Wash Sale Loss': 'Wash Sale Loss',
        'Accrued Market Discount': 'Accrued Discount',
    },
    'jpmorgan': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Accrued Market Discount': 'Accrued Discount',
        'Wash Sale Loss': 'Wash Sale Loss',
    },
    'pershing': {
        'Description': 'Desc',
        'Date Acquired': 'Date Acquired',
        'Date Sold': 'Date Sold',
        'Proceeds': 'Proceeds',
        'Cost': 'Cost',
        'Accrued Market Discount': 'Accrued Discount',
        'Wash Sale Loss': 'Wash Sale Loss',
    },
}


def create_drake_template():
    """
    Returns empty DataFrame with all 15 Drake columns in correct order.
    """
    return pd.DataFrame(columns=DRAKE_COLUMNS)


def _find_source_column(df_columns, broker_col):
    """Find the actual column name in df that matches a broker column (case/newline insensitive)."""
    broker_col_normalized = str(broker_col).replace('\n', ' ').strip().lower()
    for col in df_columns:
        col_normalized = str(col).replace('\n', ' ').strip().lower()
        if col_normalized == broker_col_normalized:
            return col
    return None


def _map_row_columns(row, df_columns, column_mapping):
    """Map broker columns to Drake columns for a single row."""
    drake_row = {col: '' for col in DRAKE_COLUMNS}
    for broker_col, drake_col in column_mapping.items():
        source_col = _find_source_column(df_columns, broker_col)
        if source_col is not None and source_col in row:
            value = row[source_col]
            if pd.notna(value) and str(value).strip().lower() not in ['nan', 'none', '']:
                drake_row[drake_col] = str(value).strip()
    return drake_row


def _infer_description(row, df_columns):
    """Try to find a description from the first text column that looks like a security name."""
    for col in df_columns:
        val = row[col]
        if pd.notna(val) and isinstance(val, str) and len(val) > 10:
            if any(word in val.upper() for word in ['INC', 'CORP', 'STOCK', 'CUSIP']):
                return val.strip()
    return ''


def _pass_through_fed_tax(row):
    """Extract Fed Tax Withheld value from a row if present and non-empty."""
    val = row.get('Fed Tax Withheld', '') if hasattr(row, 'get') else row['Fed Tax Withheld']
    if pd.notna(val) and str(val).strip().lower() not in ['nan', 'none', '']:
        return str(val).strip()
    return ''


def map_to_drake_format(df, broker_name):
    """
    Maps broker-specific DataFrame to Drake import format.

    Args:
        df: Processed DataFrame from broker parser
        broker_name: 'fidelity', 'charles_schwab', or 'robinhood'

    Returns:
        DataFrame with all 15 Drake columns (6 populated, 9 empty)
    """
    if df.empty:
        return create_drake_template()

    broker_key = broker_name.lower().replace(' ', '_')
    column_mapping = BROKER_COLUMN_MAPPINGS.get(broker_key, {})
    has_fed_tax = 'Fed Tax Withheld' in df.columns

    rows = []
    for idx, row in df.iterrows():
        drake_row = _map_row_columns(row, df.columns, column_mapping)
        if has_fed_tax:
            drake_row['Fed Tax Withheld'] = _pass_through_fed_tax(row)
        if not drake_row['Desc']:
            drake_row['Desc'] = _infer_description(row, df.columns)
        rows.append(drake_row)

    result_df = pd.DataFrame(rows)
    col_order = DRAKE_COLUMNS + (['Fed Tax Withheld'] if has_fed_tax else [])
    result_df = result_df[col_order]
    result_df = _clean_drake_output(result_df)
    return result_df


def _clean_drake_output(df):
    """Clean up Drake output DataFrame."""
    # Replace NaN with empty strings
    df = df.fillna('')

    # Currency columns — keep as numeric (float), not strings
    numeric_cols = ['Proceeds', 'Cost', 'Wash Sale Loss', 'AMT Cost Basis', 'Accrued Discount', 'Fed Tax Withheld']

    # Clean non-numeric columns as strings
    for col in df.columns:
        if col in numeric_cols:
            continue
        df[col] = df[col].astype(str)
        df[col] = df[col].replace(['nan', 'NaN', 'None', 'none'], '')
        df[col] = df[col].str.strip()

    # Normalize date columns to mm/dd/yyyy format
    date_cols = ['Date Acquired', 'Date Sold']
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].apply(_format_date)

    # Normalize Type column to S/L (works for any broker that populates it)
    if 'Type' in df.columns:
        df['Type'] = df['Type'].apply(_normalize_type)

    # Convert currency columns to actual floats (not strings)
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(_parse_to_float)

    return df


def _normalize_type(value):
    """
    Normalize transaction type to Drake's expected S/L values.
    Handles broker variations:
      'Long-term', 'LONG', 'long' → 'L'
      'Short-term', 'SHORT', 'short' → 'S'
      'L', 'S' → pass through
      Empty / unrecognized → ''
    """
    if not value or str(value).strip().lower() in ('', 'nan', 'none'):
        return ''
    v = str(value).strip().upper()
    if v in ('L', 'S'):
        return v
    if 'LONG' in v:
        return 'L'
    if 'SHORT' in v:
        return 'S'
    return ''


def _convert_2digit_year(year_str):
    """Convert 2-digit year string to 4-digit integer."""
    year_int = int(year_str)
    return 2000 + year_int if year_int <= 30 else 1900 + year_int


def _format_mdy(month, day, year):
    """Format month/day/year components to mm/dd/yyyy."""
    return f'{int(month):02d}/{int(day):02d}/{year}'


def _try_slash_date(value):
    """Try to match mm/dd/yy or mm/dd/yyyy with slash separators. Returns formatted date or None."""
    import re
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2})$', value)
    if match:
        month, day, year = match.groups()
        return _format_mdy(month, day, _convert_2digit_year(year))
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', value)
    if match:
        month, day, year = match.groups()
        return _format_mdy(month, day, year)
    return None


def _try_dash_date(value):
    """Try to match mm-dd-yy, mm-dd-yyyy, or yyyy-mm-dd with dash separators. Returns formatted date or None."""
    import re
    match = re.match(r'^(\d{1,2})-(\d{1,2})-(\d{2})$', value)
    if match:
        month, day, year = match.groups()
        return _format_mdy(month, day, _convert_2digit_year(year))
    match = re.match(r'^(\d{1,2})-(\d{1,2})-(\d{4})$', value)
    if match:
        month, day, year = match.groups()
        return _format_mdy(month, day, year)
    match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', value)
    if match:
        year, month, day = match.groups()
        return _format_mdy(month, day, year)
    return None


def _format_date(value):
    """
    Format date to mm/dd/yyyy (4-digit year).
    Handles:
    - mm/dd/yy -> mm/dd/yyyy
    - Various -> Various (preserve special value)
    - Empty -> Empty
    """
    if not value or value in ['', '--', '...']:
        return ''

    value = str(value).strip()

    if value.upper() == 'VARIOUS':
        return 'Various'

    result = _try_slash_date(value)
    if result:
        return result

    result = _try_dash_date(value)
    if result:
        return result

    return value


def _parse_to_float(value):
    """Parse a value to float for currency columns. Returns None for empty/invalid."""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return None

    if isinstance(value, (int, float)):
        return round(float(value), 2)

    str_value = str(value).strip()
    if str_value in ['', '--', '...', 'nan', 'NaN', 'None', 'none']:
        return None

    # Remove currency symbols and commas
    cleaned = str_value.replace('$', '').replace(',', '').strip()

    # Handle negative values in parentheses: (100.50) → -100.50
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]

    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return None


def validate_drake_output(df):
    """
    Validates output has required Drake columns and data.

    Args:
        df: DataFrame to validate

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    # Check all Drake columns exist
    missing_cols = [col for col in DRAKE_COLUMNS if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing Drake columns: {missing_cols}")

    # Check core required columns have data (Wash Sale Loss can be empty)
    core_required = ['Desc', 'Date Acquired', 'Date Sold', 'Proceeds', 'Cost']
    if not df.empty:
        for col in core_required:
            if col in df.columns:
                empty_count = df[col].apply(lambda v: v is None or v == '' or (isinstance(v, float) and np.isnan(v))).sum()
                total = len(df)
                if empty_count == total:
                    errors.append(f"Column '{col}' has no data")

    # Check for any rows with all empty required fields
    if not df.empty:
        def _is_empty(v):
            return v is None or v == '' or (isinstance(v, float) and np.isnan(v))
        required_empty_mask = df['Desc'].apply(_is_empty) & df['Proceeds'].apply(_is_empty) & df['Cost'].apply(_is_empty)
        empty_rows = required_empty_mask.sum()
        if empty_rows > 0:
            errors.append(f"Found {empty_rows} rows with no description or financial data")

    is_valid = len(errors) == 0
    return is_valid, errors


def _sum_numeric_col(df, col):
    """Sum a numeric column, skipping None/NaN."""
    total = 0.0
    for val in df[col]:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        try:
            total += float(str(val).replace(',', '').replace('$', ''))
        except (ValueError, TypeError):
            pass
    return round(total, 2)


def _count_wash_sales(df):
    """Count transactions with non-zero wash sale values."""
    wash_count = 0
    for val in df['Wash Sale Loss']:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        try:
            if float(str(val).replace(',', '').replace('$', '')) > 0:
                wash_count += 1
        except (ValueError, TypeError):
            pass
    return wash_count


def get_processing_summary(df, broker_name):
    """
    Generate a summary of the processed data.

    Returns dict with:
    - total_transactions: Number of transactions
    - unique_securities: Number of unique securities
    - total_proceeds: Sum of proceeds
    - total_cost: Sum of cost basis
    - wash_sale_count: Number of transactions with wash sales
    """
    summary = {
        'total_transactions': len(df),
        'unique_securities': 0,
        'total_proceeds': 0.0,
        'total_cost': 0.0,
        'wash_sale_count': 0,
        'fed_tax_total': 0.0
    }

    if df.empty:
        return summary

    if 'Desc' in df.columns:
        summary['unique_securities'] = df['Desc'].nunique()
    if 'Proceeds' in df.columns:
        summary['total_proceeds'] = _sum_numeric_col(df, 'Proceeds')
    if 'Cost' in df.columns:
        summary['total_cost'] = _sum_numeric_col(df, 'Cost')
    if 'Wash Sale Loss' in df.columns:
        summary['wash_sale_count'] = _count_wash_sales(df)
    if 'Fed Tax Withheld' in df.columns:
        summary['fed_tax_total'] = _sum_numeric_col(df, 'Fed Tax Withheld')

    return summary
