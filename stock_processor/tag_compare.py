"""
Shared vendor-tag-vs-truth comparison core.

Used by vendor_diff.py (Card 3.5, disagreement report + seed + proposed rules)
and eval_tagger.py (Card 4.2, scored multi-config eval harness). Both cards'
specs call for this comparison logic to live in one place so scoring behavior
never drifts between the two tools.

No writes, no client-data assumptions beyond the two input shapes below.
"""
import pandas as pd

TRUTH_COLUMNS = ['vendor_name', 'correct_category', 'scope']


def load_truth_csv(path):
    """Load a truth/answer-key CSV (vendor_name, correct_category[, scope]).
    scope defaults to 'vendor' (scorable) when the column is absent or blank —
    only 'structural' rows are excluded from scoring."""
    df = pd.read_csv(path, dtype=str)
    df['vendor_name'] = df['vendor_name'].str.strip()
    df['correct_category'] = df['correct_category'].str.strip()
    if 'scope' not in df.columns:
        df['scope'] = 'vendor'
    df['scope'] = df['scope'].fillna('vendor').str.strip().replace('', 'vendor')
    return df[TRUTH_COLUMNS]


def aggregate_tagged_output(tagged_df, vendor_col='Vendor', tag_col='Tag', amount_col='Amount'):
    """Collapse a per-transaction Tagged-sheet DataFrame to one row per vendor:
    the vendor's assigned Tag (first seen — a vendor's Tag is consistent across
    its rows by construction, see _apply_all_tags), summed Amount, and transaction
    Count (needed to detect class-level remap patterns across many vendors)."""
    df = tagged_df[[vendor_col, tag_col, amount_col]].copy()
    df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce').fillna(0.0)
    grp = df.groupby(vendor_col, sort=False).agg(
        Tag=(tag_col, 'first'),
        Amount=(amount_col, 'sum'),
        Count=(amount_col, 'size'),
    ).reset_index()
    grp.columns = ['Vendor', 'Tag', 'Amount', 'Count']
    return grp


def compare_vendor_tags(vendor_df, truth_df):
    """vendor_df: columns Vendor, Tag, Amount, Count (one row per vendor — see
    aggregate_tagged_output). truth_df: columns vendor_name, correct_category, scope.
    Inner-joins on vendor name — comparison is bounded by what the truth covers;
    vendors absent from truth are neither scored nor reported here.
    Returns: Vendor, Tag, correct_category, Amount, Count, scope, match (bool)."""
    merged = vendor_df.merge(truth_df, left_on='Vendor', right_on='vendor_name', how='inner')
    merged['match'] = merged['Tag'] == merged['correct_category']
    return merged[['Vendor', 'Tag', 'correct_category', 'Amount', 'Count', 'scope', 'match']]


def score_accuracy(compared_df):
    """Score only scope=='vendor' rows (the tagger-scorable set). scope=='structural'
    rows are excluded from the denominator and reported separately — see the
    'Exclusion rule' in Card 4.2's spec: measure the tagger only on what it could
    possibly get right."""
    scorable = compared_df[compared_df['scope'] != 'structural']
    structural = compared_df[compared_df['scope'] == 'structural']
    n_total = len(scorable)
    n_correct = int(scorable['match'].sum())
    misses = scorable[~scorable['match']][['Vendor', 'Tag', 'correct_category', 'Amount']]
    return {
        'accuracy': (n_correct / n_total) if n_total else 0.0,
        'n_correct': n_correct,
        'n_total': n_total,
        'misses': misses.reset_index(drop=True),
        'structural_count': len(structural),
    }
