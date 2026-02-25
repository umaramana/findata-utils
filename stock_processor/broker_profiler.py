"""
Broker Profiler — Quick analysis tool for new broker files.

Usage:
    python broker_profiler.py <file.xlsx|file.csv> [sheet_name]
    python broker_profiler.py <file.xlsx|file.csv> --broker <broker_key>
    python broker_profiler.py <file.xlsx|file.csv> --broker jpmorgan [sheet_name]

Without --broker:
    - File dimensions and sheet list
    - First 5 raw rows
    - Per-column type profile (date / numeric / text / empty %)
    - Row type distribution
    - Detected anchor columns (Date Acquired, Cost)
    - Similarity ranking against existing broker configs

With --broker <key>:
    All of the above, PLUS (using BROKER_CONFIG for precise column positions):
    - Optional zone analysis: NaN vs $0.00 vs non-zero per optional column
    - Right-of-Gain/Loss scan: what's in each column beyond Gain/Loss on txn rows
    - Shift detection: are there numeric values beyond Gain/Loss (potential shifted optionals)
    - Financial totals: Proceeds, Cost, Accrued, Wash Sale sums from transaction rows
"""

import sys
import re
import os
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from pdf_qc import BROKER_CONFIG


_DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')

_HEADER_KEYWORDS = [
    'proceeds', 'cost', 'basis', 'gain', 'loss', 'quantity',
    'date', 'acquired', 'sold', '1a', '1b', '1c', '1d', '1e',
    '1f', '1g', 'wash', 'accrued', 'discount', 'description', 'action'
]


# ── Cell & row classifiers ────────────────────────────────────────────────────

def _classify_cell(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 'empty'
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', ''):
        return 'empty'
    if _DATE_RE.match(s) or s.upper() == 'VARIOUS':
        return 'date'
    cleaned = s.replace('$', '').replace(',', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        float(cleaned)
        return 'numeric'
    except (ValueError, TypeError):
        pass
    return 'text'


def _classify_row(row):
    vals = [str(v).strip() if pd.notna(v) else '' for v in row]
    non_empty = [v for v in vals if v]

    if not non_empty:
        return 'empty'
    if len(non_empty) == 1:
        return 'single-cell'

    row_text = ' '.join(vals).lower()
    if sum(1 for kw in _HEADER_KEYWORDS if kw in row_text) >= 3:
        return 'header-like'

    types = [_classify_cell(v) for v in row]
    date_count = types.count('date')
    if date_count >= 2:
        return 'transaction-like'
    if date_count == 1 and types.count('numeric') >= 2:
        return 'transaction-like'

    return 'other'


def _is_empty(val):
    """Check if a cell value is empty/NaN."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return True
    s = str(val).strip()
    return s == '' or s.lower() in ('nan', 'none')


def _parse_numeric(val):
    """Parse a cell value to float, or return None if not numeric."""
    if _is_empty(val):
        return None
    cleaned = str(val).replace('$', '').replace(',', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# ── Column profiler ───────────────────────────────────────────────────────────

def _profile_columns(df):
    profiles = []
    for col_idx in range(len(df.columns)):
        col_vals = df.iloc[:, col_idx]
        total = len(col_vals)
        counts = {'empty': 0, 'date': 0, 'numeric': 0, 'text': 0}
        for v in col_vals:
            counts[_classify_cell(v)] += 1

        dominant = max(counts, key=counts.get)
        dominant_pct = counts[dominant] / total * 100 if total > 0 else 0

        samples = []
        for v in col_vals:
            if _classify_cell(v) != 'empty' and len(samples) < 3:
                samples.append(str(v).strip()[:25])

        profiles.append({
            'col_idx':      col_idx,
            'dominant':     dominant,
            'dominant_pct': dominant_pct,
            'empty_pct':    counts['empty']   / total * 100,
            'date_pct':     counts['date']    / total * 100,
            'numeric_pct':  counts['numeric'] / total * 100,
            'text_pct':     counts['text']    / total * 100,
            'samples':      samples,
        })
    return profiles


# ── Anchor detection ──────────────────────────────────────────────────────────

def _detect_anchors(col_profiles):
    """
    Detect likely Date Acquired and Cost column indices from column type profiles.

    Date Acquired: first column with significant date content (>20%).
    Cost: second numeric column that appears after Date Acquired
          (first numeric after dates = Proceeds, second = Cost).
    """
    date_cols    = [p['col_idx'] for p in col_profiles if p['date_pct']    > 20]
    numeric_cols = [p['col_idx'] for p in col_profiles if p['numeric_pct'] > 20]

    date_acq_col = date_cols[0] if date_cols else None

    cost_col = None
    if date_acq_col is not None:
        numeric_after_dates = [c for c in numeric_cols if c > date_acq_col]
        if len(numeric_after_dates) >= 2:
            cost_col = numeric_after_dates[1]   # Proceeds=first, Cost=second
        elif len(numeric_after_dates) == 1:
            cost_col = numeric_after_dates[0]

    return date_acq_col, cost_col


# ── Broker similarity ─────────────────────────────────────────────────────────

def _broker_similarity(detected_date_col, detected_cost_col):
    """
    Score each known broker config against the detected anchor columns.

    Scoring (max 100):
      40 pts — Date Acquired col exact match
      20 pts — Date Acquired col off by 1
      40 pts — Cost col exact match
      20 pts — Cost col off by 1
    """
    scores = {}
    for broker, config in BROKER_CONFIG.items():
        score = 0
        reasons = []

        exp_date = config.get('date_acq_col_idx')
        exp_cost = config.get('cost_col_idx')

        # Date Acquired
        if exp_date is not None and detected_date_col is not None:
            diff = abs(detected_date_col - exp_date)
            if diff == 0:
                score += 40
                reasons.append(f"Date Acquired col exact match (col {exp_date})")
            elif diff == 1:
                score += 20
                reasons.append(f"Date Acquired col off by 1 (detected {detected_date_col}, expected {exp_date})")
            else:
                reasons.append(f"Date Acquired col mismatch (detected {detected_date_col}, expected {exp_date})")
        elif exp_date is None:
            reasons.append("Date Acquired col: auto-detect (no fixed config)")

        # Cost
        if exp_cost is not None and detected_cost_col is not None:
            diff = abs(detected_cost_col - exp_cost)
            if diff == 0:
                score += 40
                reasons.append(f"Cost col exact match (col {exp_cost})")
            elif diff == 1:
                score += 20
                reasons.append(f"Cost col off by 1 (detected {detected_cost_col}, expected {exp_cost})")
            else:
                reasons.append(f"Cost col mismatch (detected {detected_cost_col}, expected {exp_cost})")
        elif exp_cost is None:
            reasons.append("Cost col: auto-detect (no fixed config)")

        opt_count = len(config.get('optional_cols', []))
        reasons.append(f"Optional cols in config: {opt_count} ({', '.join(config['optional_cols']) or 'none'})")

        scores[broker] = {'score': score, 'reasons': reasons}

    return sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)


# ── Broker-specific deep analysis ────────────────────────────────────────────

def _get_transaction_rows(df, config):
    """
    Identify transaction row indices using the broker config's date column.
    A transaction row has a date pattern in the Date Acquired column.
    """
    date_col = config.get('date_acq_col_idx')
    if date_col is None or date_col >= len(df.columns):
        return []

    txn_rows = []
    for idx in range(len(df)):
        val = df.iat[idx, date_col]
        if not _is_empty(val) and _DATE_RE.match(str(val).strip()):
            txn_rows.append(idx)
    return txn_rows


def _analyze_optional_zone(df, config, txn_rows):
    """
    Analyze the optional columns (between Cost and Gain/Loss) on transaction rows.

    Reports per optional column:
    - How many are NaN/empty (truly absent)
    - How many are zero ($0.00, 0, ' 0.00', etc.)
    - How many have non-zero values
    - Sample values for each category
    """
    cost_col = config['cost_col_idx']
    gain_loss_col = config.get('gain_loss_col_idx')
    optional_names = config.get('optional_cols', [])

    if cost_col is None or gain_loss_col is None:
        return None

    results = []
    for i, name in enumerate(optional_names):
        col_idx = cost_col + 1 + i
        if col_idx >= gain_loss_col or col_idx >= len(df.columns):
            break

        nan_count = 0
        zero_count = 0
        nonzero_count = 0
        nan_samples = []
        zero_samples = []
        nonzero_samples = []

        for row_idx in txn_rows:
            val = df.iat[row_idx, col_idx]
            if _is_empty(val):
                nan_count += 1
            else:
                num = _parse_numeric(val)
                raw = str(val).strip()
                if num is not None and num == 0:
                    zero_count += 1
                    if len(zero_samples) < 3:
                        zero_samples.append(raw)
                elif num is not None and num != 0:
                    nonzero_count += 1
                    if len(nonzero_samples) < 3:
                        nonzero_samples.append(raw)
                else:
                    # Non-numeric text in optional column (placeholder like "...")
                    nan_count += 1
                    if len(nan_samples) < 3:
                        nan_samples.append(raw)

        results.append({
            'name': name,
            'col_idx': col_idx,
            'nan_count': nan_count,
            'zero_count': zero_count,
            'nonzero_count': nonzero_count,
            'zero_samples': zero_samples,
            'nonzero_samples': nonzero_samples,
            'nan_samples': nan_samples,
        })

    return results


def _analyze_right_of_gain_loss(df, config, txn_rows):
    """
    Scan columns RIGHT of Gain/Loss on transaction rows.

    For each column beyond Gain/Loss (up to end of DataFrame):
    - Count how many txn rows have non-empty values
    - Classify content type (numeric, text, empty)
    - Collect sample values
    - Flag potential shifted optionals (numeric values in otherwise-empty zones)
    """
    gain_loss_col = config.get('gain_loss_col_idx')
    fed_tax_col = config.get('fed_tax_col_idx')

    if gain_loss_col is None:
        return None

    num_cols = len(df.columns)
    results = []

    for col_idx in range(gain_loss_col + 1, num_cols):
        empty_count = 0
        numeric_count = 0
        text_count = 0
        numeric_samples = []
        text_samples = []
        numeric_total = 0.0

        for row_idx in txn_rows:
            val = df.iat[row_idx, col_idx]
            if _is_empty(val):
                empty_count += 1
            else:
                cell_type = _classify_cell(val)
                if cell_type == 'numeric':
                    numeric_count += 1
                    raw = str(val).strip()
                    if len(numeric_samples) < 3:
                        numeric_samples.append(raw)
                    num = _parse_numeric(val)
                    if num is not None:
                        numeric_total += abs(num)
                else:
                    text_count += 1
                    if len(text_samples) < 3:
                        text_samples.append(str(val).strip()[:25])

        # Skip columns that are 100% empty on txn rows
        if empty_count == len(txn_rows):
            continue

        is_fed_tax = (fed_tax_col is not None and col_idx == fed_tax_col)

        results.append({
            'col_idx': col_idx,
            'empty_count': empty_count,
            'numeric_count': numeric_count,
            'text_count': text_count,
            'numeric_samples': numeric_samples,
            'text_samples': text_samples,
            'numeric_total': round(numeric_total, 2),
            'is_fed_tax': is_fed_tax,
            'total_txn_rows': len(txn_rows),
        })

    return results


def _analyze_shift_pattern(df, config, txn_rows):
    """
    Detect optional right-shift pattern: rows where optional zone is empty
    but numeric values exist right of Gain/Loss.

    Returns summary of normal vs shifted rows and totals for each.
    """
    cost_col = config['cost_col_idx']
    gain_loss_col = config.get('gain_loss_col_idx')
    fed_tax_col = config.get('fed_tax_col_idx')
    optional_names = config.get('optional_cols', [])

    if cost_col is None or gain_loss_col is None or not optional_names:
        return None

    num_cols = len(df.columns)
    normal_rows = 0
    shifted_rows = 0
    normal_totals = {name: 0.0 for name in optional_names}
    shifted_totals = {name: 0.0 for name in optional_names}
    shift_positions = Counter()  # Track where shifted values land

    for row_idx in txn_rows:
        # Check optional zone (between Cost and Gain/Loss)
        opt_values = []
        all_empty = True
        for i in range(len(optional_names)):
            col_idx = cost_col + 1 + i
            if col_idx >= gain_loss_col or col_idx >= num_cols:
                opt_values.append(None)
                continue
            val = df.iat[row_idx, col_idx]
            num = _parse_numeric(val)
            opt_values.append(num)
            if not _is_empty(val):
                all_empty = False

        if not all_empty:
            # Normal row — optionals are in expected position
            normal_rows += 1
            for i, name in enumerate(optional_names):
                if opt_values[i] is not None:
                    normal_totals[name] += abs(opt_values[i])
        else:
            # Optional zone empty — scan right of Gain/Loss for shifted values
            # Stop before fed_tax_col if configured
            scan_limit = fed_tax_col if fed_tax_col is not None else num_cols
            found_values = []
            for col_idx in range(gain_loss_col + 1, scan_limit):
                if col_idx >= num_cols:
                    break
                val = df.iat[row_idx, col_idx]
                num = _parse_numeric(val)
                if num is not None:
                    found_values.append((col_idx, num))

            if found_values:
                shifted_rows += 1
                for idx_in_list, (col_idx, num) in enumerate(found_values):
                    shift_positions[col_idx] += 1
                    if idx_in_list < len(optional_names):
                        shifted_totals[optional_names[idx_in_list]] += abs(num)
            else:
                # Genuinely empty optionals (no values found anywhere)
                normal_rows += 1

    return {
        'normal_rows': normal_rows,
        'shifted_rows': shifted_rows,
        'normal_totals': {k: round(v, 2) for k, v in normal_totals.items()},
        'shifted_totals': {k: round(v, 2) for k, v in shifted_totals.items()},
        'shift_positions': dict(shift_positions),
    }


def _compute_financial_totals(df, config, txn_rows):
    """
    Compute Proceeds, Cost, Accrued, Wash Sale, Gain/Loss totals from transaction rows.
    Uses broker config for column positions.
    """
    cost_col = config['cost_col_idx']
    gain_loss_col = config.get('gain_loss_col_idx')
    optional_names = config.get('optional_cols', [])
    num_cols = len(df.columns)

    # Map column names to indices
    # Proceeds is always cost_col - 1 for most brokers; detect from profile
    # Use a simpler approach: Proceeds = cost_col - 1 (common pattern)
    proceeds_col = cost_col - 1 if cost_col is not None and cost_col > 0 else None

    totals = {
        'Proceeds': 0.0,
        'Cost': 0.0,
        'Gain/Loss': 0.0,
    }
    for name in optional_names:
        totals[name] = 0.0

    for row_idx in txn_rows:
        # Proceeds
        if proceeds_col is not None and proceeds_col < num_cols:
            num = _parse_numeric(df.iat[row_idx, proceeds_col])
            if num is not None:
                totals['Proceeds'] += num

        # Cost
        if cost_col < num_cols:
            num = _parse_numeric(df.iat[row_idx, cost_col])
            if num is not None:
                totals['Cost'] += num

        # Gain/Loss
        if gain_loss_col is not None and gain_loss_col < num_cols:
            num = _parse_numeric(df.iat[row_idx, gain_loss_col])
            if num is not None:
                totals['Gain/Loss'] += num

        # Optionals (normal position)
        for i, name in enumerate(optional_names):
            col_idx = cost_col + 1 + i
            if col_idx < gain_loss_col and col_idx < num_cols:
                num = _parse_numeric(df.iat[row_idx, col_idx])
                if num is not None:
                    totals[name] += num

    return {k: round(v, 2) for k, v in totals.items()}


def _print_deep_analysis(df, broker_key):
    """Run and print the broker-specific deep analysis sections."""
    config = BROKER_CONFIG.get(broker_key)
    if config is None:
        print(f"\n  ERROR: No BROKER_CONFIG entry for '{broker_key}'")
        print(f"  Available: {', '.join(BROKER_CONFIG.keys())}")
        return

    print(f"\n{'='*65}")
    print(f"  DEEP ANALYSIS (broker: {broker_key})")
    print(f"{'='*65}")

    # Show config being used
    print(f"\n── BROKER CONFIG {'─'*47}")
    print(f"  Date Acquired col : {config['date_acq_col_idx']}")
    print(f"  Cost col          : {config['cost_col_idx']}")
    print(f"  Gain/Loss col     : {config.get('gain_loss_col_idx', 'not configured')}")
    print(f"  Fed Tax col       : {config.get('fed_tax_col_idx', 'not configured')}")
    print(f"  Optional cols     : {config.get('optional_cols', [])}")

    # Find transaction rows
    txn_rows = _get_transaction_rows(df, config)
    print(f"\n  Transaction rows found: {len(txn_rows)}")

    if not txn_rows:
        print("  No transaction rows found — cannot run deep analysis.")
        return

    # ── Financial totals (normal positions only) ─────────────────────────
    print(f"\n── FINANCIAL TOTALS (normal col positions) {'─'*21}")
    totals = _compute_financial_totals(df, config, txn_rows)
    for name, val in totals.items():
        print(f"  {name:<30} ${val:>14,.2f}")

    # ── Optional zone analysis ───────────────────────────────────────────
    print(f"\n── OPTIONAL ZONE ANALYSIS {'─'*38}")
    opt_results = _analyze_optional_zone(df, config, txn_rows)
    if opt_results:
        for opt in opt_results:
            total = opt['nan_count'] + opt['zero_count'] + opt['nonzero_count']
            print(f"\n  {opt['name']} (col {opt['col_idx']}):")
            print(f"    NaN/empty  : {opt['nan_count']:>4}  ({opt['nan_count']/total*100:.0f}%)"
                  f"  {opt['nan_samples'][:2] if opt['nan_samples'] else ''}")
            print(f"    Zero       : {opt['zero_count']:>4}  ({opt['zero_count']/total*100:.0f}%)"
                  f"  {opt['zero_samples'][:2] if opt['zero_samples'] else ''}")
            print(f"    Non-zero   : {opt['nonzero_count']:>4}  ({opt['nonzero_count']/total*100:.0f}%)"
                  f"  {opt['nonzero_samples'][:2] if opt['nonzero_samples'] else ''}")

            if opt['nan_count'] > 0:
                print(f"    ⚠ {opt['nan_count']} rows have truly empty optionals — Pass 3 would trigger on these")
    else:
        print("  No optional columns configured or detected.")

    # ── Right-of-Gain/Loss scan ──────────────────────────────────────────
    print(f"\n── RIGHT OF GAIN/LOSS SCAN {'─'*37}")
    right_results = _analyze_right_of_gain_loss(df, config, txn_rows)
    if right_results:
        gl_col = config.get('gain_loss_col_idx')
        print(f"  Gain/Loss at col {gl_col}. Non-empty columns beyond it on txn rows:\n")
        print(f"  {'Col':<5} {'Numeric':>8} {'Text':>6} {'Empty':>6} {'$Total':>12}  {'Flag':<15} Samples")
        print(f"  {'─'*75}")
        for r in right_results:
            flag = ''
            if r['is_fed_tax']:
                flag = 'FED TAX'
            elif r['numeric_count'] > 0 and r['numeric_count'] < r['total_txn_rows']:
                flag = 'PARTIAL SHIFT?'
            elif r['numeric_count'] == r['total_txn_rows']:
                flag = 'FULL COL'

            samples = r['numeric_samples'][:2] or r['text_samples'][:2]
            sample_str = ' | '.join(samples)
            print(f"  {r['col_idx']:<5} {r['numeric_count']:>8} {r['text_count']:>6} "
                  f"{r['empty_count']:>6} ${r['numeric_total']:>11,.2f}  {flag:<15} {sample_str}")
    else:
        print("  No non-empty columns found right of Gain/Loss on transaction rows.")

    # ── Shift pattern detection ──────────────────────────────────────────
    print(f"\n── SHIFT PATTERN DETECTION {'─'*37}")
    shift = _analyze_shift_pattern(df, config, txn_rows)
    if shift:
        print(f"  Normal rows (optionals in place) : {shift['normal_rows']}")
        print(f"  Shifted rows (optionals moved)   : {shift['shifted_rows']}")

        if shift['shifted_rows'] > 0:
            print(f"\n  Normal position totals:")
            for name, val in shift['normal_totals'].items():
                print(f"    {name:<30} ${val:>12,.2f}")
            print(f"\n  Shifted position totals:")
            for name, val in shift['shifted_totals'].items():
                print(f"    {name:<30} ${val:>12,.2f}")
            print(f"\n  Combined totals:")
            all_names = list(shift['normal_totals'].keys())
            for name in all_names:
                combined = shift['normal_totals'].get(name, 0) + shift['shifted_totals'].get(name, 0)
                print(f"    {name:<30} ${combined:>12,.2f}")
            print(f"\n  Shift destination columns: {shift['shift_positions']}")
        else:
            print("  No shifted optionals detected.")
    else:
        print("  No optional columns configured — shift detection skipped.")

    print(f"\n{'='*65}\n")


# ── Main profiler ─────────────────────────────────────────────────────────────

def profile_file(filepath, sheet_name=None, broker_key=None):
    ext = os.path.splitext(filepath)[1].lower()

    print(f"\n{'='*65}")
    print(f"  BROKER PROFILER")
    print(f"  File : {os.path.basename(filepath)}")
    print(f"{'='*65}")

    # Load
    if ext == '.csv':
        df = pd.read_csv(filepath, header=None, dtype=str)
        print(f"  Format : CSV")
        print(f"  Dims   : {len(df)} rows × {len(df.columns)} columns")
    else:
        xls = pd.ExcelFile(filepath)
        print(f"  Format : Excel")
        print(f"  Sheets : {xls.sheet_names}")
        target = sheet_name or xls.sheet_names[0]
        df = xls.parse(target, header=None, dtype=str)
        print(f"  Sheet  : {target}")
        print(f"  Dims   : {len(df)} rows × {len(df.columns)} columns")

    # ── First 5 rows ──────────────────────────────────────────────────────────
    print(f"\n── FIRST 5 ROWS (raw) {'─'*43}")
    for i in range(min(5, len(df))):
        vals = [str(v)[:22] if pd.notna(v) else '' for v in df.iloc[i]]
        print(f"  Row {i:2d}: {vals}")

    # ── Row type distribution ─────────────────────────────────────────────────
    print(f"\n── ROW TYPE DISTRIBUTION {'─'*39}")
    row_types = [_classify_row(df.iloc[i]) for i in range(len(df))]
    counts = Counter(row_types)
    total = len(row_types)
    for rtype, count in sorted(counts.items(), key=lambda x: -x[1]):
        bar = '█' * int(count / total * 30)
        print(f"  {rtype:<20} {count:>4}  ({count/total*100:>4.0f}%)  {bar}")

    # ── Column profiles ───────────────────────────────────────────────────────
    print(f"\n── COLUMN PROFILES {'─'*45}")
    col_profiles = _profile_columns(df)
    print(f"  {'Col':<5} {'Dominant':<10} {'Date%':>6} {'Num%':>6} {'Text%':>6} {'Empty%':>7}  Samples")
    print(f"  {'─'*63}")
    for p in col_profiles:
        sample_str = ' | '.join(p['samples'][:2]) if p['samples'] else '—'
        print(f"  {p['col_idx']:<5} {p['dominant']:<10} "
              f"{p['date_pct']:>5.0f}% {p['numeric_pct']:>5.0f}% "
              f"{p['text_pct']:>5.0f}% {p['empty_pct']:>6.0f}%  {sample_str}")

    # ── Anchor detection ──────────────────────────────────────────────────────
    date_acq_col, cost_col = _detect_anchors(col_profiles)
    print(f"\n── DETECTED ANCHORS {'─'*44}")
    print(f"  Date Acquired col : {date_acq_col if date_acq_col is not None else 'not detected'}")
    print(f"  Cost col          : {cost_col if cost_col is not None else 'not detected'}")

    # ── Broker similarity ─────────────────────────────────────────────────────
    print(f"\n── BROKER SIMILARITY RANKING {'─'*35}")
    ranked = _broker_similarity(date_acq_col, cost_col)
    for broker, info in ranked:
        bar = '█' * (info['score'] // 5)
        print(f"  [{info['score']:>3}/80] {broker:<20} {bar}")
        for reason in info['reasons']:
            print(f"           • {reason}")
        print()

    print(f"{'='*65}\n")

    # ── Deep analysis (if broker specified) ───────────────────────────────────
    if broker_key:
        _print_deep_analysis(df, broker_key)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python broker_profiler.py <file.xlsx|file.csv> [sheet_name]")
        print("       python broker_profiler.py <file.xlsx|file.csv> --broker <key> [sheet_name]")
        sys.exit(1)

    args = sys.argv[1:]
    filepath = args[0]
    broker_key = None
    sheet_name = None

    # Parse --broker flag
    remaining = args[1:]
    if '--broker' in remaining:
        idx = remaining.index('--broker')
        if idx + 1 < len(remaining):
            broker_key = remaining[idx + 1]
            remaining = remaining[:idx] + remaining[idx + 2:]
        else:
            print("ERROR: --broker requires a broker key argument")
            sys.exit(1)

    # Remaining arg is sheet name
    if remaining:
        sheet_name = remaining[0]

    profile_file(filepath, sheet_name, broker_key)
