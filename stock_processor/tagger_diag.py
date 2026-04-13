"""
Tagger diagnostic — run this to inspect amount columns in your bank file.
Usage:
    python tagger_diag.py "path/to/your/file.xlsx" "Subtracted" "Added"

Arguments:
    file       — path to the Excel/CSV file
    debit_col  — name of the debit/subtracted column
    credit_col — name of the credit/added column (optional, pass "" to skip)
"""
import sys
import pandas as pd


def _parse_amount(val):
    s = str(val).strip().replace(',', '').replace('$', '').replace(' ', '')
    if s.startswith('(') and s.endswith(')'):
        try:
            return -abs(float(s[1:-1]))
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _load_file(filepath):
    if filepath.lower().endswith('.csv'):
        return pd.read_csv(filepath)
    xl = pd.ExcelFile(filepath)
    print(f"Sheets: {xl.sheet_names}")
    return xl.parse(xl.sheet_names[0])


def _inspect_col(df, col_name, label):
    series = df[col_name]
    parsed = series.apply(_parse_amount)
    print(f"--- {label}: '{col_name}' ---")
    print(f"  dtype         : {series.dtype}")
    print(f"  non-null count: {series.notna().sum()} / {len(series)}")
    print(f"  sample values : {series.dropna().head(5).tolist()}")
    print(f"  parsed sample : {parsed.dropna().head(5).tolist()}")
    print(f"  parse failures: {parsed.isna().sum()} rows returned None")


def _report_signed(debit_series, credit_series):
    safe = pd.to_numeric(debit_series.apply(_parse_amount), errors='coerce').fillna(0.0)
    safe_c = pd.to_numeric(credit_series.apply(_parse_amount), errors='coerce').fillna(0.0)
    signed = safe_c - safe
    print("\n--- _signed_amount result (with NaN fix applied) ---")
    print(f"  sample values     : {signed.head(10).tolist()}")
    print(f"  negative (expense): {(signed < 0).sum()} rows")
    print(f"  positive (income) : {(signed > 0).sum()} rows")
    print(f"  zero              : {(signed == 0).sum()} rows")
    print(f"  NaN               : {signed.isna().sum()} rows")
    if (signed < 0).sum() == 0:
        print("\n  *** STILL ALL ZERO/POSITIVE — check raw sample above for unexpected format ***")


def main():
    if len(sys.argv) < 3:
        print("Usage: python tagger_diag.py <file> <debit_col> [credit_col]")
        sys.exit(1)

    filepath   = sys.argv[1]
    debit_col  = sys.argv[2]
    credit_col = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None

    df = _load_file(filepath)
    print(f"\nTotal rows: {len(df)}")
    print(f"Columns: {df.columns.tolist()}\n")

    if debit_col not in df.columns:
        print(f"ERROR: debit column '{debit_col}' not found. Check column name above.")
        sys.exit(1)

    _inspect_col(df, debit_col, 'Debit column')

    credit_series = pd.Series(0.0, index=df.index)
    if credit_col:
        if credit_col not in df.columns:
            print(f"\nERROR: credit column '{credit_col}' not found.")
        else:
            _inspect_col(df, credit_col, '\nCredit column')
            credit_series = df[credit_col]

    _report_signed(df[debit_col], credit_series)


if __name__ == '__main__':
    main()
