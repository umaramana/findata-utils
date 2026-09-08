"""
Reusable synthetic 1099-B sheet builders for edge-case regression testing.

Why this exists: hand-typing raw row lists for every new edge case (as was
done ad hoc for the "--" bugs found 2026-09-08) is slow and error-prone —
column-index mistakes silently produce a wrong-but-plausible baseline. These
builders place values by role (date, proceeds, cost, ...) so the caller never
counts columns by hand, and the resulting sheet always matches a broker's
real structural layout.

Add a builder here for each broker as its edge-case matrix is built out (see
test_edge_case_matrix.py for Schwab's). This module produces in-memory
DataFrames only — callers decide whether to write them to disk as permanent
regression fixtures or use them as throwaway inputs for an inline-assertion
test.
"""

import pandas as pd


def schwab_date_cols(num_cols):
    """Return (date_col, proceeds_col, cost_col, accrued_wash_col, gain_loss_col)
    for a Schwab sheet of the given width, using the same formula as
    brokers/schwab.py's _date_col_idx (the financial block is always the
    last 5 columns: Date, Proceeds, Cost, Accrued/Wash, Gain/Loss)."""
    date_col = min(max(num_cols - 5, 2), 4)
    return date_col, date_col + 1, date_col + 2, date_col + 3, date_col + 4


def _schwab_boilerplate_header(num_cols, date_col=None):
    rows = [
        [None] * num_cols,
        [None, None, None, 'TAX YEAR 2025\nFORM 1099 COMPOSITE'] + [None] * (num_cols - 4),
        ['Proceeds from Broker Transactions __ 2025', 'Form 1099-B'] + [None] * (num_cols - 2),
        ['Department of the Treasury-Internal Revenue Service',
         'Copy B for Recipient (OMB No. 1545-0715)'] + [None] * (num_cols - 2),
        ['SHORT-TERM TRANSACTIONS FOR WHICH BASIS IS REPORTED TO THE IRS - '
         'Report on Form 8949, Part I, with Box A checked.'] + [None] * (num_cols - 1),
    ]
    if date_col is None:
        date_col, proceeds_col, cost_col, aw_col, gl_col = schwab_date_cols(num_cols)
    else:
        proceeds_col, cost_col, aw_col, gl_col = date_col + 1, date_col + 2, date_col + 3, date_col + 4
    h1 = [None] * num_cols
    h1[date_col] = '1b-Date acquired'
    h1[aw_col] = '1f-Accrued'
    h2 = [None] * num_cols
    h2[0] = '1a-Description of property'
    h2[date_col] = '1c-Date sold\nor disposed'
    h2[proceeds_col] = '1d-Proceeds'
    h2[cost_col] = '1e-Cost or\nother basis'
    h2[aw_col] = '1g-Wash Sale\nLoss Disallowed'
    h2[gl_col] = 'Realized\nGain or (Loss)'
    rows.extend([h1, h2])
    return rows


def _schwab_boilerplate_footer(num_cols):
    return [
        ['FATCA Filing Requirement '] + [None] * (num_cols - 1),
        ['Please see the "Notes for Your Form 1099-B" section for additional '
         'explanation of this Form 1099-B report. '] + [None] * (num_cols - 1),
    ]


def _schwab_txn_rows(tx, i, num_cols, cols):
    """Build the primary/secondary(/subtotal/spacer) raw rows for one
    transaction dict. See build_schwab_sheet() for the tx dict's keys."""
    date_col, proceeds_col, cost_col, aw_col, gl_col = cols
    desc = tx.get('desc', f'{i + 1} SYNTHETIC SECURITY {i + 1}')
    cusip = tx.get('cusip', f'00000000{i} / SYN{i}')
    proceeds, cost = tx.get('proceeds', '$100.00'), tx.get('cost', '$80.00')
    accrued, wash = tx.get('accrued', '--'), tx.get('wash', '--')
    gain_loss = tx.get('gain_loss', '$20.00')

    primary = [None] * num_cols
    primary[0], primary[date_col] = desc, tx.get('date_acq', '01/17/2025')
    primary[proceeds_col], primary[cost_col] = proceeds, cost
    primary[aw_col], primary[gl_col] = accrued, gain_loss

    secondary = [None] * num_cols
    secondary[0], secondary[date_col] = cusip, tx.get('date_sold', '12/26/2025')
    secondary[aw_col] = wash

    rows = [primary, secondary]
    if tx.get('subtotal', True):
        subtotal = [None] * num_cols
        subtotal[0] = 'Security Subtotal'
        subtotal[proceeds_col], subtotal[cost_col] = proceeds, cost
        subtotal[aw_col], subtotal[gl_col] = accrued, gain_loss
        spacer = [None] * num_cols
        spacer[aw_col] = '--'
        rows += [subtotal, spacer]
    return rows


def _preserve_trailing_col(rows, num_cols):
    """pandas' to_excel/read_excel round-trip silently drops trailing columns
    that are empty in EVERY row -- a real broker-generated xlsx keeps them
    (PDF24 renders a fixed table grid regardless of blank cells), so a
    synthetic sheet must too, or num_cols silently shrinks on write/read and
    a date_col override meant to leave a trailing gap gets masked. Stamp a
    page-footer-style marker (matches real scanned-page artifacts, e.g.
    "Page 1 of 16") in the last column if nothing else already reaches it."""
    last_col = num_cols - 1
    if not any(row[last_col] is not None for row in rows):
        rows.append(['Page 1 of 1'] + [None] * (num_cols - 1))
        rows[-1][last_col] = '(0126-K1P3)'


def build_schwab_sheet(num_cols, transactions, header=True, footer=True, date_col=None):
    """
    Build a synthetic Schwab sheet (as a raw, header=None-style DataFrame).

    transactions: list of dicts, each may set desc/cusip, date_acq/date_sold
      (default real dates), proceeds (default '$100.00'), cost (default
      '$80.00' -- pass '' or non-dollar text like 'Not Reported' freely),
      accrued/wash (default '--'/'--'), gain_loss (default '$20.00'), and
      subtotal (include a Security Subtotal + blank-dash spacer row after
      this transaction, default True, matches real broker output).

    date_col: override the date column's position, decoupling it from
      num_cols. Omit to use the same formula schwab.py's _date_col_idx uses
      (a "textbook" sheet, which can never exercise a wrong formula guess --
      it would tautologically always agree with the code under test). Pass
      an explicit value to build an ADVERSARIAL sheet where the formula
      guesses wrong for this num_cols (e.g. an extra padding column) -- the
      shape of the real client bug found 2026-09-08 (8-col sheet, real date
      column 2, formula guessed 3).

    Returns a DataFrame with no header row consumed (matches how the app
    reads Schwab files: header=None).
    """
    cols = schwab_date_cols(num_cols) if date_col is None else (
        date_col, date_col + 1, date_col + 2, date_col + 3, date_col + 4)
    date_col = cols[0]

    rows = _schwab_boilerplate_header(num_cols, date_col=date_col) if header else []
    for i, tx in enumerate(transactions):
        rows.extend(_schwab_txn_rows(tx, i, num_cols, cols))
    if footer:
        rows.extend(_schwab_boilerplate_footer(num_cols))

    _preserve_trailing_col(rows, num_cols)
    return pd.DataFrame(rows)
