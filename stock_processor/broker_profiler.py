"""
Broker Profiler — Quick analysis tool for new broker files.

Usage:
    python broker_profiler.py <file.xlsx|file.csv> [sheet_name]

Output:
    - File dimensions and sheet list
    - First 5 raw rows
    - Per-column type profile (date / numeric / text / empty %)
    - Row type distribution
    - Detected anchor columns (Date Acquired, Cost)
    - Similarity ranking against existing broker configs
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


# ── Main profiler ─────────────────────────────────────────────────────────────

def profile_file(filepath, sheet_name=None):
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


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python broker_profiler.py <file.xlsx|file.csv> [sheet_name]")
        sys.exit(1)

    profile_file(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
