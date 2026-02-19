"""
Charles Schwab broker processor.
Handles:
- Strict date filtering (only keep rows with dates)
- Paired row structure (Row 1: stock + date acquired, Row 2: CUSIP + date sold)
- "VARIOUS" as special date value
- Merging paired rows into single transactions

Ported from existing StockMerger/utils.py
"""

import pandas as pd
import numpy as np
import re


# Special date values
SPECIAL_DATE_VALUES = ["VARIOUS"]


def process(file_obj):
    """
    Process Schwab transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Description, Date Acquired, Date Sold,
                               Proceeds, Cost, Accrued Market Discount,
                               Wash Sale, Source Sheet
    """
    # Read all sheets
    excel_file = pd.ExcelFile(file_obj)
    sheet_dfs = {}

    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(file_obj, sheet_name=sheet_name)

        if df.empty:
            continue

        # Filter to only rows with dates
        filtered_df = _identify_rows_with_dates(df)

        if filtered_df.empty:
            continue

        # Standardize columns
        standardized_df = _standardize_columns(filtered_df)
        standardized_df['Source_Sheet'] = sheet_name

        sheet_dfs[sheet_name] = standardized_df

    if not sheet_dfs:
        return pd.DataFrame()

    # Merge all sheets
    merged_df = _create_merged_df(sheet_dfs)

    # Merge paired rows
    result_df = _merge_paired_rows(merged_df)

    return result_df


def _is_date_value(value):
    """Check if a value matches common date formats or is "VARIOUS"."""
    if pd.isna(value):
        return False

    str_value = str(value).strip()

    # Clean trailing characters (PDF24 sometimes attaches $ to dates like "VARIOUS $")
    cleaned_value = re.sub(r'[\$\s]+$', '', str_value)

    # Check for VARIOUS (after cleaning)
    if cleaned_value.upper() == "VARIOUS":
        return True

    # Date patterns
    date_patterns = [
        r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$',           # MM/DD/YYYY
        r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}$',             # YYYY-MM-DD
        r'^[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,)?\s+\d{2,4}$',  # Month name
        r'^\d{1,2}\s+[A-Za-z]{3,9}(?:,)?\s+\d{2,4}$',  # Day Month Year
        r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}$'   # ISO format
    ]

    for pattern in date_patterns:
        if re.match(pattern, cleaned_value, re.IGNORECASE):
            return True

    return False


def _identify_rows_with_dates(df):
    """Keep only rows that have at least one column with a date value."""
    if df.empty:
        return df

    has_date_mask = pd.Series(False, index=df.index)

    for col in df.columns:
        col_date_mask = df[col].apply(_is_date_value)
        has_date_mask = has_date_mask | col_date_mask

    return df[has_date_mask].copy()


def _standardize_columns(df):
    """
    Standardize column headers by detecting actual column purposes.
    Handles PDF24 conversion quirks where extra columns may be inserted.
    """
    if df.empty:
        return df

    result_df = df.copy()
    num_cols = len(result_df.columns)

    # Analyze first data row to find column purposes
    if len(result_df) > 0:
        first_row = result_df.iloc[0]
        col_mapping = {}

        # Find the date column (contains date pattern or "VARIOUS")
        date_col_idx = None
        for i, val in enumerate(first_row):
            if _is_date_value(val):
                date_col_idx = i
                break

        # Description is always first column (position 0)
        col_mapping[0] = "Description"

        if date_col_idx is not None:
            # Map columns relative to date column
            col_mapping[date_col_idx] = "Date Acquired/Date Sold"

            # Proceeds is typically right after date or 1-2 positions after
            for offset in [1, 2]:
                idx = date_col_idx + offset
                if idx < num_cols:
                    val = first_row.iloc[idx]
                    # Check if it looks like a monetary value
                    if pd.notna(val):
                        str_val = str(val)
                        if '$' in str_val or (str_val.replace(',', '').replace('.', '').replace('-', '').isdigit() and len(str_val) > 2):
                            col_mapping[idx] = "Proceeds"
                            if idx + 1 < num_cols:
                                col_mapping[idx + 1] = "Cost"
                            if idx + 2 < num_cols:
                                col_mapping[idx + 2] = "Accrued Market Discount"
                            if idx + 3 < num_cols:
                                col_mapping[idx + 3] = "Wash Sale"
                            if idx + 4 < num_cols:
                                col_mapping[idx + 4] = "Realised gain/loss"
                            if idx + 5 < num_cols:
                                col_mapping[idx + 5] = "Fed Tax Withheld"
                            break

        # Build new column names
        new_column_names = []
        for i in range(num_cols):
            if i in col_mapping:
                new_column_names.append(col_mapping[i])
            else:
                new_column_names.append(f"Column_{i+1}")

        result_df.columns = new_column_names
    else:
        # Fallback to positional mapping
        standard_columns = [
            "Description", "Code", "Date Acquired/Date Sold", "Proceeds",
            "Cost", "Accrued Market Discount", "Wash Sale", "Realised gain/loss",
            "Federal Tax withheld"
        ]
        new_column_names = []
        for i in range(num_cols):
            if i < len(standard_columns):
                new_column_names.append(standard_columns[i])
            else:
                new_column_names.append(f"Column_{i+1}")
        result_df.columns = new_column_names

    return result_df


def _create_merged_df(sheet_dfs):
    """Combine all sheets into a single DataFrame."""
    if not sheet_dfs:
        return pd.DataFrame()

    processed_dfs = []
    for sheet_name, df in sheet_dfs.items():
        if df.empty:
            continue
        df_copy = df.copy()
        for col in df_copy.select_dtypes(include=['object']).columns:
            df_copy[col] = df_copy[col].astype(str)
        processed_dfs.append(df_copy)

    if not processed_dfs:
        return pd.DataFrame()

    merged_df = pd.concat(processed_dfs, ignore_index=True)

    # Move Source_Sheet to first column
    cols = merged_df.columns.tolist()
    if 'Source_Sheet' in cols:
        cols.remove('Source_Sheet')
        cols = ['Source_Sheet'] + cols
        merged_df = merged_df[cols]

    return merged_df


def _merge_paired_rows(df):
    """
    Merge pairs of rows that represent a single stock transaction.

    Row1 (primary): Has stock name, Date Acquired, Proceeds, Cost
    Row2 (secondary): Has CUSIP/Symbol, Date Sold only

    Detects primary vs secondary by checking if Proceeds column has a value.
    """
    if df.empty:
        return df

    # Re-filter for dates
    df = _identify_rows_with_dates(df).reset_index(drop=True)

    if len(df) < 2:
        return df

    def is_primary_row(row):
        """Primary row has Proceeds value (financial data)."""
        proceeds = row.get('Proceeds', None)
        if pd.isna(proceeds):
            return False
        proceeds_str = str(proceeds).strip()
        if proceeds_str.lower() in ['nan', 'none', '', '--']:
            return False
        # Check if it looks like a number
        cleaned = re.sub(r'[\$,\s]', '', proceeds_str)
        try:
            float(cleaned)
            return True
        except (ValueError, TypeError):
            return False

    merged_rows = []
    i = 0

    while i < len(df):
        row1 = df.iloc[i]

        # Check if this is a primary row (has Proceeds)
        if is_primary_row(row1):
            # Look for the next row as secondary (should be CUSIP row)
            if i + 1 < len(df):
                row2 = df.iloc[i + 1]

                # Verify row2 is secondary (no Proceeds)
                if not is_primary_row(row2):
                    # Valid pair found
                    desc1 = str(row1.get('Description', '')).strip()
                    desc2 = str(row2.get('Description', '')).strip()
                    if desc1.lower() in ['nan', 'none']:
                        desc1 = ''
                    if desc2.lower() in ['nan', 'none']:
                        desc2 = ''
                    full_description = f"{desc1} {desc2}".strip()

                    date_col = 'Date Acquired/Date Sold'
                    date_acquired = str(row1.get(date_col, '')).strip()
                    date_sold = str(row2.get(date_col, '')).strip()
                    date_acquired = re.sub(r'\s*\$\s*$', '', date_acquired)
                    date_sold = re.sub(r'\s*\$\s*$', '', date_sold)
                    if date_acquired.lower() in ['nan', 'none']:
                        date_acquired = ''
                    if date_sold.lower() in ['nan', 'none']:
                        date_sold = ''

                    proceeds = str(row1.get('Proceeds', '')).strip()
                    cost = str(row1.get('Cost', '')).strip()
                    if proceeds.lower() in ['nan', 'none']:
                        proceeds = ''
                    if cost.lower() in ['nan', 'none']:
                        cost = ''

                    if '$' in proceeds and proceeds.count('$') > 1:
                        parts = [p.strip() for p in proceeds.split('$') if p.strip()]
                        if len(parts) >= 2:
                            proceeds = f"${parts[0]}"
                            cost = f"${parts[1]}"

                    accrued_mkt_disc = str(row1.get('Accrued Market Discount', '')).strip()
                    if accrued_mkt_disc.lower() in ['nan', 'none', '--']:
                        accrued_mkt_disc = ''

                    wash_sale = str(row1.get('Wash Sale', '')).strip()
                    if wash_sale.lower() in ['nan', 'none', '--']:
                        wash_sale = ''

                    merged_entry = {
                        'Source_Sheet': str(row1.get('Source_Sheet', '')).strip(),
                        'Description': full_description,
                        'Date Acquired': date_acquired,
                        'Date Sold': date_sold,
                        'Proceeds': _clean_currency_value(proceeds),
                        'Cost': _clean_currency_value(cost),
                        'Accrued Market Discount': _clean_currency_value(accrued_mkt_disc),
                        'Wash Sale': _clean_currency_value(wash_sale),
                        'Realised gain/loss': str(row1.get('Realised gain/loss', '')).strip(),
                        'Fed Tax Withheld': str(row1.get('Fed Tax Withheld', '')).strip()
                    }
                    merged_rows.append(merged_entry)
                    i += 2  # Skip both rows
                    continue
                else:
                    # row2 is also primary - row1 might be missing its pair
                    # Just process row1 alone
                    pass

            # Process row1 alone (no valid pair found)
            desc = str(row1.get('Description', '')).strip()
            if desc.lower() in ['nan', 'none']:
                desc = ''

            date_col = 'Date Acquired/Date Sold'
            date_val = str(row1.get(date_col, '')).strip()
            date_val = re.sub(r'\s*\$\s*$', '', date_val)

            proceeds = str(row1.get('Proceeds', '')).strip()
            cost = str(row1.get('Cost', '')).strip()
            accrued_mkt_disc = str(row1.get('Accrued Market Discount', '')).strip()
            wash_sale = str(row1.get('Wash Sale', '')).strip()

            merged_entry = {
                'Source_Sheet': str(row1.get('Source_Sheet', '')).strip(),
                'Description': desc,
                'Date Acquired': date_val,
                'Date Sold': '',
                'Proceeds': _clean_currency_value(proceeds),
                'Cost': _clean_currency_value(cost),
                'Accrued Market Discount': _clean_currency_value(accrued_mkt_disc) if accrued_mkt_disc.lower() not in ['nan', 'none', '--'] else '',
                'Wash Sale': _clean_currency_value(wash_sale) if wash_sale.lower() not in ['nan', 'none', '--'] else '',
                'Realised gain/loss': str(row1.get('Realised gain/loss', '')).strip(),
                'Fed Tax Withheld': str(row1.get('Fed Tax Withheld', '')).strip()
            }
            merged_rows.append(merged_entry)
            i += 1
        else:
            # This is a secondary/orphan row (CUSIP only, no Proceeds)
            # Skip it - it's either orphaned or will be picked up by its primary
            i += 1

    result_df = pd.DataFrame(merged_rows)

    # Clean up nan/None strings
    for col in result_df.columns:
        result_df[col] = result_df[col].astype(str).replace(['nan', 'NaN', 'None', 'none'], '')

    return result_df


def _clean_currency_value(value):
    """Clean currency value - remove $ and commas, handle parentheses for negative."""
    if not value or value in ['--', 'nan', 'NaN', 'None', '']:
        return ''

    # Remove $ and commas
    cleaned = re.sub(r'[\$,\s]', '', str(value))

    # Handle parentheses for negative numbers: (100.50) -> -100.50
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]

    return cleaned
