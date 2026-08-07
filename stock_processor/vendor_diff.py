#!/usr/bin/env python3
"""
Card 3.5 — Vendor-Level Diff (seed + rules generator)

Compares the tagger's per-vendor tags against a trusted per-vendor truth
(finalized/filed categories). Produces a disagreement report plus two reusable
artifacts: a Vendor→Category seed (for the P1 vendor-memory importer) and a
proposed client-rules file (for Card A's rules block).

Never fabricates a mapping or rule the truth doesn't support. Structural items
(the truth CSV's scope=='structural' rows — 941-derived splits, apportionments,
etc.) are reported as out-of-tagger-scope, never seeded or ruled.

Usage:
  python vendor_diff.py <client_id> <tagged-output.xlsx> <truth.csv> [--year YYYY] [--out-dir DIR]
"""
import argparse
import os
import re
import sys

import pandas as pd

from tag_compare import aggregate_tagged_output, compare_vendor_tags, load_truth_csv

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_EVALS_DIR = os.path.join(_SCRIPT_DIR, 'evals')
REMAP_RULE_THRESHOLD = 5  # transactions remapped identically → propose a class rule


def _infer_year(truth_path, explicit_year):
    if explicit_year:
        return explicit_year
    m = re.search(r'(20\d{2})', os.path.basename(truth_path))
    if m:
        return m.group(1)
    raise ValueError(
        f'Could not infer year from "{truth_path}" — pass --year explicitly.')


def load_tagged_workbook(xlsx_path):
    """Read the Tagged sheet and aggregate to one row per vendor."""
    df = pd.read_excel(xlsx_path, sheet_name='Tagged')
    return aggregate_tagged_output(df)


def build_disagreement_report(compared_df):
    """Mismatched vendors, sorted by dollar impact (largest absolute amount first).
    Includes structural (out-of-scope) mismatches too — reported, never actioned."""
    mism = compared_df[~compared_df['match']].copy()
    mism['dollar_impact'] = mism['Amount'].abs()
    mism = mism.sort_values('dollar_impact', ascending=False)
    out = mism.rename(columns={'Tag': 'Tagger_Tag', 'correct_category': 'Truth_Category'})
    return out[['Vendor', 'Amount', 'Count', 'Tagger_Tag', 'Truth_Category', 'scope']]


def _ambiguous_vendors(truth_df):
    """Vendor names the truth CSV itself maps to more than one category —
    genuinely unresolved (e.g. person-to-person transfers used for many purposes).
    Never seeded; logged as excluded instead."""
    counts = truth_df.groupby('vendor_name')['correct_category'].nunique()
    return set(counts[counts > 1].index)


def classify_disagreements(compared_df, truth_df, threshold=REMAP_RULE_THRESHOLD):
    """Split vendor-scope disagreements into class-remap rules vs. one-off seeds.
    Returns (rule_rows, seed_rows, excluded_rows) — each a DataFrame."""
    ambiguous = _ambiguous_vendors(truth_df)
    disagree = compared_df[(~compared_df['match']) & (compared_df['scope'] != 'structural')].copy()

    excluded = disagree[disagree['Vendor'].isin(ambiguous)]
    resolvable = disagree[~disagree['Vendor'].isin(ambiguous)]

    class_counts = resolvable.groupby(['Tag', 'correct_category'])['Count'].sum()
    rule_pairs = set(class_counts[class_counts >= threshold].index)

    is_rule_class = resolvable.apply(lambda r: (r['Tag'], r['correct_category']) in rule_pairs, axis=1)
    rule_rows = resolvable[is_rule_class]
    seed_rows = resolvable[~is_rule_class]
    return rule_rows, seed_rows, excluded


def build_seed(seed_rows):
    """Vendor,Category — confirmed one-off mappings, ready for the P1 importer."""
    seed = seed_rows[['Vendor', 'correct_category']].drop_duplicates(subset='Vendor')
    return seed.rename(columns={'correct_category': 'Category'})


def build_proposed_rules(rule_rows):
    """One proposed plain-English rule per (Tag, correct_category) class, with the
    supporting evidence so the preparer can confirm or reword before promoting it
    to {client_id}_rules.txt. Never asserts semantics (e.g. 'credit-card') the data
    doesn't literally show — states the observed tag pair, preparer adds nuance."""
    lines = []
    for (tag, truth), grp in rule_rows.groupby(['Tag', 'correct_category']):
        n_txns = int(grp['Count'].sum())
        n_vendors = grp['Vendor'].nunique()
        examples = ', '.join(sorted(grp['Vendor'].unique())[:5])
        lines.append(
            f'# Pattern: {n_txns} transactions across {n_vendors} vendors tagged "{tag}", '
            f'truth says "{truth}". Examples: {examples}\n'
            f'# CONFIRM before promoting to {{client_id}}_rules.txt:\n'
            f'{tag} vendors are {truth} for this client.\n'
        )
    return '\n'.join(lines)


def run(client_id, tagged_path, truth_path, year=None, out_dir=None):
    out_dir = out_dir or _DEFAULT_EVALS_DIR
    os.makedirs(out_dir, exist_ok=True)
    year = _infer_year(truth_path, year)

    vendor_agg = load_tagged_workbook(tagged_path)
    truth_df = load_truth_csv(truth_path)
    compared = compare_vendor_tags(vendor_agg, truth_df)

    diff_report = build_disagreement_report(compared)
    rule_rows, seed_rows, excluded = classify_disagreements(compared, truth_df)
    seed = build_seed(seed_rows)
    proposed_rules_text = build_proposed_rules(rule_rows)

    diff_path = os.path.join(out_dir, f'{client_id}_diff_{year}.csv')
    seed_path = os.path.join(out_dir, f'{client_id}_seed_{year}.csv')
    rules_path = os.path.join(out_dir, f'{client_id}_rules_PROPOSED.txt')

    diff_report.to_csv(diff_path, index=False)
    seed.to_csv(seed_path, index=False)
    with open(rules_path, 'w', encoding='utf-8') as f:
        f.write(proposed_rules_text)

    scored = compared[compared['scope'] != 'structural']
    print(f'Disagreements: {len(diff_report)} ({diff_report["scope"].eq("structural").sum()} structural, '
          f'out of tagger scope) → {diff_path}')
    print(f'Seed (one-off confirmed mappings): {len(seed)} vendors '
          f'({len(excluded)} excluded as ambiguous) → {seed_path}')
    print(f'Proposed rule classes (>= {REMAP_RULE_THRESHOLD} txns remapped identically): '
          f'{rule_rows.groupby(["Tag", "correct_category"]).ngroups} → {rules_path}')
    print(f'Vendor-scope agreement (informational, not a Card 4.2 accuracy score): '
          f'{int(scored["match"].sum())}/{len(scored)}')
    return diff_report, seed, proposed_rules_text, excluded


def main():
    p = argparse.ArgumentParser(description='Card 3.5 — vendor-level tag diff, seed + rules generator')
    p.add_argument('client_id')
    p.add_argument('tagged_output', help='Tagger output workbook (.xlsx) with a Tagged sheet')
    p.add_argument('truth_csv', help='vendor_name, correct_category[, scope] answer key')
    p.add_argument('--year', help='Override year inferred from the truth filename')
    p.add_argument('--out-dir', help=f'Output dir (default: {_DEFAULT_EVALS_DIR})')
    args = p.parse_args()
    try:
        run(args.client_id, args.tagged_output, args.truth_csv, args.year, args.out_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
