"""
Excel Column QC & Auto-Correct module.

PDF24 converts broker 1099-B PDFs to Excel with correct column headers,
but data rows can be misaligned in two ways:

1. "Right shift" — Part 1 (Description) consumes extra columns, pushing
   all Part 2 columns (dates, financials) one or more positions right.
2. "Empty cell collapse" — when optional columns (Accrued Market Discount,
   Wash Sale Loss) are empty, values shift left.

Fix: Use the header row as the anchor. For each data row, validate that
the Date Acquired column has a date pattern at the expected position.
If the date is found further right, shift Part 2 values left to re-align
with the header.

Each broker has its own column config — column layouts differ per broker.
"""

import io
import re

import pandas as pd
from openpyxl.styles import PatternFill


# Date pattern: MM/DD/YY or MM/DD/YYYY
_DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')


# ── Per-broker column configuration ──────────────────────────────────────
# Each broker defines:
#   cost_col_idx:       expected 0-based column index for Cost
#   date_acq_col_idx:   expected 0-based column index for Date Acquired
#   cost_keywords:      keywords to verify/find the Cost column header
#   date_acq_keywords:  keywords to verify/find the Date Acquired header
#   optional_cols:      names of the optional columns in the zone (for logging)

BROKER_CONFIG = {
    'fidelity': {
        # Fidelity 1099-B column order (0-indexed):
        # 0: Action
        # 1: Quantity
        # 2: 1b Date Acquired
        # 3: 1c Date Sold or Disposed
        # 4: 1d Proceeds
        # 5: 1e Cost or Other Basis
        # 6: 1f Accrued Market Discount  ← optional
        # 7: 1g Wash Sale Loss           ← optional
        # 8: Gain/Loss                   ← always present
        'date_acq_col_idx': 2,
        'cost_col_idx': 5,
        'date_acq_keywords': ['date', 'acquired', '1b'],
        'cost_keywords': ['cost', 'basis', '1e'],
        'optional_cols': ['1f Accrued Market Discount', '1g Wash Sale Loss'],
    },
    'charles_schwab': {
        # Schwab layout — update these when testing with actual Schwab files
        'date_acq_col_idx': None,
        'cost_col_idx': None,  # Auto-detect from headers
        'date_acq_keywords': ['date', 'acquired', '1b'],
        'cost_keywords': ['cost', 'basis', '1e'],
        'optional_cols': [],
    },
    'robinhood': {
        # Robinhood 1099-B column order (0-indexed):
        # 0: 1c Date Sold or Disposed
        # 1: Quantity
        # 2: 1d Proceeds
        # 3: 1b Date Acquired
        # 4: 1e Cost or Other Basis
        # 5: 1g Wash Sale Loss           ← optional
        # 6: Gain/Loss                   ← always present
        'date_acq_col_idx': 3,
        'cost_col_idx': 4,
        'date_acq_keywords': ['date', 'acquired', '1b'],
        'cost_keywords': ['cost', 'basis', '1e'],
        'optional_cols': ['1g Wash Sale Loss'],
    },
    'merrill': {
        # Merrill 1099-B column order (0-indexed):
        # 0: 1a. Description of Property
        # 1: (blank)
        # 2: 1b. Date Acquired
        # 3: 1c. Date Sold or Disposed
        # 4: 1d. Proceeds
        # 5: 1e. Cost Basis
        # 6: 1f. Accrued Market Discount  ← optional
        # 7: 1g. Wash Sale Loss           ← optional
        # 8: Gain or Loss                 ← always present
        'date_acq_col_idx': 2,
        'cost_col_idx': 5,
        'date_acq_keywords': ['date', 'acquired', '1b'],
        'cost_keywords': ['cost', 'basis', '1e'],
        'optional_cols': ['1f Accrued Market Discount', '1g Wash Sale Loss'],
    },
    'morgan_stanley': {
        # Morgan Stanley 1099-B column order (0-indexed):
        # 0: Description (Box 1a)
        # 1: Quantity
        # 2: Date Acquired (Box 1b)
        # 3: Date Sold (Box 1c)
        # 4: Proceeds (Box 1d)
        # 5: Cost or Other Basis (Box 1e)
        # 6: Accrued Market Discount (Box 1f)  ← optional
        # 7: Wash Sale Loss Disallowed (Box 1g) ← optional
        # 8: Gain/(Loss)                        ← always present
        # 9: Federal Income Tax Withheld         ← always present
        'date_acq_col_idx': 2,
        'cost_col_idx': 5,
        'date_acq_keywords': ['date', 'acquired', '1b'],
        'cost_keywords': ['cost', 'basis', '1e'],
        'optional_cols': ['Accrued Market Discount', 'Wash Sale Loss Disallowed'],
    },
}


def _find_header_row(df):
    """Find the header row index in a DataFrame by keyword matching.
    Picks the row with the most keyword matches (within first 10 rows)
    to avoid false positives from form title rows like 'PROCEEDS FROM
    BROKER & BARTER EXCHANGE TRANSACTIONS'.
    """
    keywords = ['proceeds', 'cost', 'basis', 'gain', 'loss', 'action',
                'quantity', 'date', 'acquired', 'sold',
                '1a', '1b', '1c', '1d', '1e', '1f', '1g',
                'wash', 'accrued', 'discount', 'description']

    best_idx = 0
    best_count = 0
    for idx, row in df.head(10).iterrows():
        row_text = ' '.join(str(v).lower() if pd.notna(v) else '' for v in row)
        count = sum(1 for kw in keywords if kw in row_text)
        if count > best_count:
            best_count = count
            best_idx = idx
    return best_idx


def _find_anchor_cols(df, broker_name):
    """
    Find Date Acquired and Cost column indices from the header row.
    Uses hardcoded indices from broker config if available, otherwise
    falls back to keyword matching.
    """
    config = BROKER_CONFIG.get(broker_name)
    if config is None:
        raise ValueError(f"No QC config for broker: {broker_name}")

    header_idx = _find_header_row(df)

    # --- Date Acquired ---
    date_acq_col = config['date_acq_col_idx']
    if date_acq_col is not None:
        cell = str(df.iat[header_idx, date_acq_col]).lower() if date_acq_col < len(df.columns) else ''
        if not any(kw in cell for kw in config['date_acq_keywords']):
            date_acq_col = None

    if date_acq_col is None:
        for row_idx in range(header_idx, min(header_idx + 3, len(df))):
            for col_idx, val in enumerate(df.iloc[row_idx]):
                cell = str(val).lower() if pd.notna(val) else ''
                if any(kw in cell for kw in config['date_acq_keywords']):
                    date_acq_col = col_idx
                    break
            if date_acq_col is not None:
                break

    # --- Cost ---
    cost_col = config['cost_col_idx']
    if cost_col is not None:
        cell = str(df.iat[header_idx, cost_col]).lower() if cost_col < len(df.columns) else ''
        if not any(kw in cell for kw in config['cost_keywords']):
            cost_col = None

    if cost_col is None:
        for row_idx in range(header_idx, min(header_idx + 3, len(df))):
            for col_idx, val in enumerate(df.iloc[row_idx]):
                cell = str(val).lower() if pd.notna(val) else ''
                if any(kw in cell for kw in config['cost_keywords']):
                    cost_col = col_idx
                    break
            if cost_col is not None:
                break

    missing = []
    if date_acq_col is None:
        missing.append('Date Acquired')
    if cost_col is None:
        missing.append('Cost')
    if missing:
        raise ValueError(f"Could not find column(s): {', '.join(missing)}")

    return {'date_acq_col': date_acq_col, 'cost_col': cost_col, 'header_idx': header_idx}


def _is_empty(val):
    """Check if a cell value is empty/NaN."""
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    s = str(val).strip()
    return s == '' or s in ('nan', 'NaN', 'None')


def _has_date(val):
    """Check if a cell contains a date pattern (MM/DD/YY), including \\n-separated values."""
    if _is_empty(val):
        return False
    lines = [l.strip() for l in str(val).split('\n') if l.strip()]
    return any(_DATE_RE.match(l) for l in lines)


def detect_and_correct(excel_file, broker_name):
    """
    Detect and correct column misalignment across all sheets.

    For each data row, validates that Date Acquired is at the expected
    column position (from header). If shifted right (Part 1 consumed
    extra columns), shifts Part 2 values left to re-align with header.

    Args:
        excel_file: File-like object for the Excel file.
        broker_name: One of 'fidelity', 'charles_schwab', 'robinhood', 'merrill'.

    Returns:
        dict with:
            corrected_excel: BytesIO with fixed Excel (or None if no issues).
            log: List of human-readable log entries.
            total_fixes: Total number of rows corrected.
            sheets_checked: Number of sheets processed.
    """
    config = BROKER_CONFIG.get(broker_name)
    if config is None:
        raise ValueError(f"No QC config for broker: {broker_name}")

    excel_file.seek(0)
    xls = pd.ExcelFile(excel_file)

    log = []
    total_fixes = 0
    any_corrections = False
    review_rows = []

    # Find anchors from the first sheet
    first_df = xls.parse(xls.sheet_names[0], header=None)
    anchors = _find_anchor_cols(first_df, broker_name)
    expected_date_col = anchors['date_acq_col']
    cost_col = anchors['cost_col']

    # Map optional zone column indices to human-readable names
    optional_col_names = {}
    for i, name in enumerate(config['optional_cols']):
        optional_col_names[cost_col + 1 + i] = name

    log.append(f"Broker: {broker_name}")
    log.append(f"Anchor columns: Date Acquired=col {expected_date_col}, Cost=col {cost_col}")
    if config['optional_cols']:
        log.append(f"Optional zone: {', '.join(config['optional_cols'])}")

    excel_file.seek(0)
    output = io.BytesIO()

    highlight_fill = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name in xls.sheet_names:
            excel_file.seek(0)
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, dtype=str)
            header_idx = _find_header_row(df)
            sheet_fixes = 0
            sheet_details = []
            corrected_rows = []

            for row_idx in range(header_idx + 1, len(df)):
                if expected_date_col >= len(df.columns):
                    continue

                # Check if date is at expected position
                if _has_date(df.iat[row_idx, expected_date_col]):
                    continue  # Row is aligned — no correction needed

                # Date not at expected position — scan right to find it
                actual_date_col = None
                for col in range(expected_date_col + 1, len(df.columns)):
                    if _has_date(df.iat[row_idx, col]):
                        actual_date_col = col
                        break

                if actual_date_col is None:
                    continue  # No date found (description, header, or skip row)

                # Right shift detected — shift Part 2 values left to align
                offset = actual_date_col - expected_date_col
                num_cols = len(df.columns)

                # Shift values from actual positions to expected positions
                for col in range(expected_date_col, num_cols - offset):
                    df.iat[row_idx, col] = df.iat[row_idx, col + offset]
                # Clear trailing columns that were shifted from
                for col in range(num_cols - offset, num_cols):
                    df.iat[row_idx, col] = None

                sheet_fixes += 1
                corrected_rows.append(row_idx)

                sheet_details.append(
                    f"    Row {row_idx + 1}: shifted Part 2 left by {offset} col(s) "
                    f"(date was at col {actual_date_col}, expected col {expected_date_col})"
                )

                # Flag rows that have optional column values (for manual review)
                opt_parts = []
                for col in range(cost_col + 1, cost_col + 1 + len(config['optional_cols'])):
                    if col < num_cols:
                        val = df.iat[row_idx, col]
                        if not _is_empty(val):
                            col_name = optional_col_names.get(col, f"col {col}")
                            opt_parts.append(f"{col_name} = {val}")
                if opt_parts:
                    review_rows.append(
                        f"{sheet_name} Row {row_idx + 1}: {', '.join(opt_parts)}"
                    )

            if sheet_fixes > 0:
                any_corrections = True
                log.append(f"{sheet_name}: {sheet_fixes} rows corrected")
                log.extend(sheet_details)
            else:
                log.append(f"{sheet_name}: no corrections needed")

            total_fixes += sheet_fixes
            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

            # Highlight corrected rows in the output Excel
            if corrected_rows:
                ws = writer.sheets[sheet_name]
                for row_idx in corrected_rows:
                    # Highlight the date cell to mark corrected rows
                    ws.cell(row=row_idx + 1, column=expected_date_col + 1).fill = highlight_fill

    output.seek(0)

    return {
        'corrected_excel': output if any_corrections else None,
        'log': log,
        'total_fixes': total_fixes,
        'sheets_checked': len(xls.sheet_names),
        'review_rows': review_rows,
    }
