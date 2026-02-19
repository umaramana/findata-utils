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
        'Wash Sale': 'Wash Sale Loss'
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
    }
}


def create_drake_template():
    """
    Returns empty DataFrame with all 15 Drake columns in correct order.
    """
    return pd.DataFrame(columns=DRAKE_COLUMNS)


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

    # Normalize broker name
    broker_key = broker_name.lower().replace(' ', '_')

    # Get column mapping for this broker
    column_mapping = BROKER_COLUMN_MAPPINGS.get(broker_key, {})

    # Check if source has Fed Tax Withheld to pass through
    has_fed_tax = 'Fed Tax Withheld' in df.columns

    # Create output DataFrame with Drake columns
    drake_df = create_drake_template()

    # Process each row
    rows = []
    for idx, row in df.iterrows():
        drake_row = {col: '' for col in DRAKE_COLUMNS}
        if has_fed_tax:
            drake_row['Fed Tax Withheld'] = ''

        # Map columns from broker format to Drake format
        for broker_col, drake_col in column_mapping.items():
            # Check if this column exists in the source data (handle case variations)
            source_col = None
            for col in df.columns:
                # Normalize column names for comparison
                col_normalized = str(col).replace('\n', ' ').strip()
                broker_col_normalized = str(broker_col).replace('\n', ' ').strip()

                if col_normalized.lower() == broker_col_normalized.lower():
                    source_col = col
                    break

            if source_col is not None and source_col in row:
                value = row[source_col]
                if pd.notna(value) and str(value).strip().lower() not in ['nan', 'none', '']:
                    drake_row[drake_col] = str(value).strip()

        # Handle special case: if no Description was mapped, try first text column
        if not drake_row['Desc']:
            for col in df.columns:
                val = row[col]
                if pd.notna(val) and isinstance(val, str) and len(val) > 10:
                    # Looks like a description
                    if any(word in val.upper() for word in ['INC', 'CORP', 'STOCK', 'CUSIP']):
                        drake_row['Desc'] = val.strip()
                        break

        # Pass through Fed Tax Withheld if present in source
        if has_fed_tax:
            val = row.get('Fed Tax Withheld', '') if hasattr(row, 'get') else row['Fed Tax Withheld']
            if pd.notna(val) and str(val).strip().lower() not in ['nan', 'none', '']:
                drake_row['Fed Tax Withheld'] = str(val).strip()

        rows.append(drake_row)

    result_df = pd.DataFrame(rows)

    # Ensure column order: Drake columns first, then Fed Tax Withheld if present
    if has_fed_tax:
        result_df = result_df[DRAKE_COLUMNS + ['Fed Tax Withheld']]
    else:
        result_df = result_df[DRAKE_COLUMNS]

    # Clean up the data
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


def _format_date(value):
    """
    Format date to mm/dd/yyyy (4-digit year).
    Handles:
    - mm/dd/yy -> mm/dd/yyyy
    - Various -> Various (preserve special value)
    - Empty -> Empty
    """
    import re

    if not value or value in ['', '--', '...']:
        return ''

    value = str(value).strip()

    # Preserve special values
    if value.upper() == 'VARIOUS':
        return 'Various'

    # Match mm/dd/yy or m/d/yy pattern (2-digit year)
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2})$', value)
    if match:
        month, day, year = match.groups()
        # Convert 2-digit year to 4-digit
        year_int = int(year)
        if year_int >= 0 and year_int <= 30:
            full_year = 2000 + year_int
        else:
            full_year = 1900 + year_int
        return f'{int(month):02d}/{int(day):02d}/{full_year}'

    # Match mm/dd/yyyy (already 4-digit year)
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', value)
    if match:
        month, day, year = match.groups()
        return f'{int(month):02d}/{int(day):02d}/{year}'

    # Return as-is if no pattern matches
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

    # Unique securities
    if 'Desc' in df.columns:
        summary['unique_securities'] = df['Desc'].nunique()

    # Sum proceeds
    if 'Proceeds' in df.columns:
        proceeds_sum = 0
        for val in df['Proceeds']:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            try:
                proceeds_sum += float(str(val).replace(',', '').replace('$', ''))
            except (ValueError, TypeError):
                pass
        summary['total_proceeds'] = round(proceeds_sum, 2)

    # Sum cost
    if 'Cost' in df.columns:
        cost_sum = 0
        for val in df['Cost']:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            try:
                cost_sum += float(str(val).replace(',', '').replace('$', ''))
            except (ValueError, TypeError):
                pass
        summary['total_cost'] = round(cost_sum, 2)

    # Wash sale count
    if 'Wash Sale Loss' in df.columns:
        wash_count = 0
        for val in df['Wash Sale Loss']:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            try:
                if float(str(val).replace(',', '').replace('$', '')) > 0:
                    wash_count += 1
            except (ValueError, TypeError):
                pass
        summary['wash_sale_count'] = wash_count

    # Fed Tax Withheld total
    if 'Fed Tax Withheld' in df.columns:
        summary['fed_tax_total'] = _sum_numeric_col(df, 'Fed Tax Withheld')

    return summary
