"""
Fidelity broker processor.
Handles the parent-child row structure where:
- Parent row: Stock description (e.g., "ALPHABET INC CAP STKCL C, GOOG, 02079K107")
- Child row(s): Transaction action ("Sale", "Expire")

Ported from existing VibeVimala/fidelity_app/app.py
"""

import pandas as pd
import numpy as np
import re


# Default Fidelity 1099-B column names (standard IRS column order)
# Used as fallback when no header row is detected in a sheet
FIDELITY_DEFAULT_COLUMNS = [
    'Action', 'Quantity', '1b Date\nAcquired',
    '1c Date Sold\nor Disposed', '1d Proceeds',
    '1e Cost or\nOther Basis (b)', '1f Accrued Market\nDiscount',
    '1g Wash Sale\nLoss', 'Gain/Loss', 'Fed Tax Withheld'
]


def process(file_obj):
    """
    Process Fidelity transaction file and return standardized DataFrame.

    Args:
        file_obj: File path or file-like object (BytesIO from Streamlit upload)

    Returns:
        DataFrame with columns: Action, Quantity, Date Acquired, Date Sold,
                               Proceeds, Cost, Wash Sale Loss, Source Sheet
    """
    # Read all sheets
    excel_file = pd.ExcelFile(file_obj)
    all_processed_dfs = []

    for sheet_name in excel_file.sheet_names:
        # Use header=None to prevent the first row from being consumed as column names.
        # The _process_sheet function has its own header detection logic.
        df = excel_file.parse(sheet_name, header=None)
        processed_df = _process_sheet(df)

        if not processed_df.empty:
            processed_df['Source Sheet'] = sheet_name
            all_processed_dfs.append(processed_df)

    if not all_processed_dfs:
        return pd.DataFrame()

    # Combine all sheets
    combined_df = pd.concat(all_processed_dfs, ignore_index=True)
    return combined_df


def _detect_header_row(df):
    """
    Find the header row index in a Fidelity sheet.
    Looks for "Action"/"Quantity" in first two columns, or falls back to
    pattern matching with 3+ keyword hits.

    Returns header_row_idx or None.
    """
    # Look for the row that has "Action" in first column and "Quantity" in second
    for idx, row in df.iterrows():
        first_val = str(row.iloc[0]).strip().lower() if pd.notna(row.iloc[0]) else ''
        second_val = str(row.iloc[1]).strip().lower() if len(row) > 1 and pd.notna(row.iloc[1]) else ''
        if first_val == 'action' and second_val == 'quantity':
            return idx

    # Fall back to pattern matching
    header_patterns = ['action', 'quantity', 'date acquired', 'date sold', 'proceeds']
    for idx, row in df.iterrows():
        row_text = ' '.join([str(x).lower() if not pd.isna(x) else '' for x in row.values])
        match_count = sum(1 for pattern in header_patterns if pattern in row_text)
        if match_count >= 3:
            return idx

    return None


def _extract_data_with_header(df, header_row_idx):
    """
    Extract data rows after header and apply header row as column names.
    If no header found, assign default Fidelity column names.

    Returns DataFrame with named columns.
    """
    if header_row_idx is not None:
        # Get column names from the header row (preserve \n characters)
        header_values = df.iloc[header_row_idx].values
        new_columns = []
        for i, val in enumerate(header_values):
            if pd.notna(val) and str(val).strip():
                new_columns.append(str(val).strip())
            else:
                new_columns.append(f'Column_{i}')

        relevant_rows = df.iloc[header_row_idx+1:].copy()
        relevant_rows.columns = new_columns
    else:
        relevant_rows = df.copy()
        _assign_default_column_names(relevant_rows)

    return relevant_rows


def _process_sheet(df):
    """
    Process a single Fidelity sheet.
    Core logic ported from existing process_transactions() function.
    """
    header_row_idx = _detect_header_row(df)
    relevant_rows = _extract_data_with_header(df, header_row_idx)

    # Determine action column (first column or one named 'Action')
    action_col = _find_action_column(relevant_rows)
    if action_col is None and len(relevant_rows.columns) > 0:
        action_col = relevant_rows.columns[0]

    # Clean rows (remove dotted lines, subtotals)
    cleaned_rows = _clean_rows(relevant_rows, action_col)

    if not cleaned_rows:
        return pd.DataFrame()

    cleaned_df = relevant_rows.loc[[idx for idx, _ in cleaned_rows]].copy()

    # Fix PDF24 empty cell collapse before parent-child processing.
    # Fidelity layout: cost=col5, optional_cols=2 (Accrued+WashSale), gain_loss=col8.
    cleaned_df = _fix_empty_cell_collapse(cleaned_df, cost_col_idx=5, gain_loss_col_idx=8)

    # Handle merged cells for stock descriptions
    cleaned_df = _handle_merged_cells(cleaned_df, action_col)

    # Process parent-child relationships
    all_processed_rows = _process_parent_child(cleaned_df, action_col)

    if not all_processed_rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(all_processed_rows)

    # Final cleanup
    result_df = _final_cleanup(result_df, action_col)

    return result_df


def _fix_empty_cell_collapse(df, cost_col_idx, gain_loss_col_idx):
    """
    Fix PDF24 empty cell collapse: when optional columns (Accrued, Wash Sale)
    are absent for a row, Gain/Loss slides left into those optional positions.

    Gain/Loss is NEVER empty for real transaction rows. If it is empty at its
    expected position, a collapse occurred: scan backward through the optional
    zone, move the first non-empty value found to the Gain/Loss column, and
    clear it from where it was. Proceeds and Cost are always at fixed positions
    and are not touched.

    Args:
        df: DataFrame with named columns (col positions still addressable by iloc)
        cost_col_idx: 0-based index of the Cost column
        gain_loss_col_idx: 0-based index of the expected Gain/Loss column
                           = cost_col_idx + len(optional_cols) + 1

    This function is a standalone utility — reusable for other brokers.
    """
    num_cols = len(df.columns)
    if gain_loss_col_idx >= num_cols:
        return df

    for row_idx in range(len(df)):
        gain_val = df.iloc[row_idx, gain_loss_col_idx]
        if not (pd.isna(gain_val) or str(gain_val).strip() in ('', 'nan', 'NaN', 'None')):
            continue  # Gain/Loss is present — no collapse

        # Scan backward through optional zone (between Cost and Gain/Loss)
        for col in range(gain_loss_col_idx - 1, cost_col_idx, -1):
            val = df.iloc[row_idx, col]
            if pd.isna(val) or str(val).strip() in ('', 'nan', 'NaN', 'None'):
                continue
            # Found collapsed Gain/Loss — move to expected position, clear source
            df.iloc[row_idx, gain_loss_col_idx] = val
            df.iloc[row_idx, col] = None
            break

    return df


def _assign_default_column_names(df):
    """Assign default Fidelity column names by position when no header row is found."""
    num_cols = len(df.columns)
    new_names = []
    for i in range(num_cols):
        if i < len(FIDELITY_DEFAULT_COLUMNS):
            new_names.append(FIDELITY_DEFAULT_COLUMNS[i])
        else:
            new_names.append(f'Column_{i}')
    df.columns = new_names


def _find_action_column(df):
    """Find the column containing action information (Sale, Expire, etc.)"""
    # Check column names
    for col in df.columns:
        col_lower = str(col).lower()
        if 'action' in col_lower:
            return col

    # Check first column for "Sale" values
    if len(df.columns) > 0:
        first_col = df.columns[0]
        if df[first_col].astype(str).str.contains('ale', case=False).any():
            return first_col

    return None


_FIDELITY_FOOTER_PATTERNS = [
    'this is important tax information',
    'furnished to the internal revenue service',
    'irs determines',
    'if applicable is not',
    'reported to the irs',
    'substitute statement'
]


def _is_dotted_line(action_value):
    """Check if action value is a dotted/dashed separator line."""
    if not isinstance(action_value, str):
        return False
    return bool(re.match(r'^-+$', action_value.strip())) or action_value.count('-') > 10


def _is_summary_or_footer_row(row_text):
    """Check if row text matches subtotal, total, sum, or footer patterns."""
    if 'subtotal' in row_text or 'total' in row_text or 'sum' in row_text:
        return True
    return any(pattern in row_text for pattern in _FIDELITY_FOOTER_PATTERNS)


def _count_numeric_columns(row, df_columns, action_col):
    """Count non-action columns that contain numeric values."""
    count = 0
    for col in df_columns:
        if col != action_col and not pd.isna(row[col]) and str(row[col]).strip():
            try:
                float(str(row[col]).replace('$', '').replace(',', '').strip())
                count += 1
            except (ValueError, TypeError):
                pass
    return count


def _clean_rows(df, action_col):
    """Remove dotted lines, subtotals, and empty rows."""
    cleaned_rows = []

    for idx, row in df.iterrows():
        action_value = row[action_col] if action_col in row else None

        # Skip empty rows
        if pd.isna(action_value) or action_value == '':
            continue

        # Skip dotted line rows
        if _is_dotted_line(action_value):
            continue

        # Skip subtotal rows and footer/disclaimer rows
        row_values = [str(val).strip() if not pd.isna(val) else '' for val in row]
        row_text = ' '.join(row_values).lower()

        if _is_summary_or_footer_row(row_text):
            continue

        # Skip sum-like rows: short label + only 1-2 numeric values (likely a subtotal line)
        numeric_columns = _count_numeric_columns(row, df.columns, action_col)
        if numeric_columns >= 1 and numeric_columns <= 2 and (pd.isna(action_value) or len(str(action_value)) < 5):
            continue

        cleaned_rows.append((idx, row))

    return cleaned_rows


def _handle_merged_cells(df, action_col):
    """Handle merged cells that might contain stock descriptions."""
    df = df.copy()

    for idx, row in df.iterrows():
        row_values = [str(val).strip() if not pd.isna(val) else '' for val in row]
        row_text = ' '.join(row_values)

        # Check if this might be a stock description row
        if (len(row_text) > 20 and
            ('cusip' in row_text.lower() or
             any(word in row_text.upper() for word in ['INC', 'CORP', 'LTD', 'PLC']) or
             re.search(r'[A-Z]{4,5}', row_text))):

            # Find first non-empty value and move to action column
            for col_idx, val in enumerate(row):
                if not pd.isna(val) and str(val).strip():
                    df.at[idx, action_col] = val
                    for other_col in df.columns:
                        if other_col != action_col:
                            df.at[idx, other_col] = np.nan
                    break

    return df


def _is_description_row(row, action_col):
    """A stock description row has text only in the action column; all other columns are empty."""
    action_value = row[action_col]
    if not isinstance(action_value, str) or len(action_value.strip()) < 3:
        return False
    # Check that all other columns are empty/NaN
    for col in row.index:
        if col == action_col:
            continue
        val = row[col]
        if pd.notna(val) and str(val).strip() != '':
            return False
    return True


def _process_parent_child(df, action_col):
    """Process parent-child relationships - associate transaction rows with stock descriptions."""
    all_processed_rows = []
    current_stock_description = None

    for idx, row in df.iterrows():
        action_value = row[action_col] if action_col in row else None

        if pd.isna(action_value) or action_value == '':
            continue

        # Stock description row: text only in first column, rest empty
        if _is_description_row(row, action_col):
            current_stock_description = str(action_value).strip()

        # Transaction row: has data in other columns
        elif current_stock_description:
            processed_row = row.copy()
            processed_row[action_col] = current_stock_description
            all_processed_rows.append(processed_row)

    return all_processed_rows


def _final_cleanup(df, action_col):
    """Final cleanup to remove any remaining dotted lines or subtotals."""
    rows_to_keep = []

    for idx, row in df.iterrows():
        action_value = row[action_col] if action_col in row else None

        # Skip dotted separator lines
        if isinstance(action_value, str) and (
            re.match(r'^-+$', action_value.strip()) or
            action_value.count('-') > 10
        ):
            continue

        # Skip subtotal rows
        row_values = [str(val).strip() if not pd.isna(val) else '' for val in row]
        row_text = ' '.join(row_values).lower()
        if 'subtotal' in row_text or 'total' in row_text or 'sum' in row_text:
            continue

        rows_to_keep.append(idx)

    if rows_to_keep:
        df = df.loc[rows_to_keep].reset_index(drop=True)

    return df
