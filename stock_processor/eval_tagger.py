#!/usr/bin/env python3
"""
Card 4.2 — Vendor-Level Eval Harness

Runs the tagger's real classification pipeline (tagger_page._build_system_prompt +
_run_claude_on_vendors — the same functions the Streamlit app calls, imported
directly so the eval measures actual production behavior, never a re-implementation)
against a known answer key and reports accuracy. Prerequisite for Card A: an
enriched-prompt change is only kept if this harness shows a real, stable win over
the bare-vendor baseline.

No writes to Vendor Memory, lookups, or any production artifact — read-only over
inputs, aside from its own report files under stock_processor/evals/.

Usage:
  python eval_tagger.py <client_id> <vendor_data_file> <answer_key.csv>
      [--config bare|enriched|persona-off|persona-on]
      [--compare configA,configB]
      [--api-key KEY] [--year YYYY] [--out-dir DIR]
      [--entity-type TYPE] [--primary TEXT] [--secondary TEXT]
"""
import argparse
import os
import sys
import types
from datetime import datetime

import pandas as pd

from tag_compare import compare_vendor_tags, load_truth_csv, score_accuracy

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_EVALS_DIR = os.path.join(_SCRIPT_DIR, 'evals')


def _load_tagger_module():
    """Import tagger_page.py without its trailing module-level render() call —
    render() drives Streamlit UI and needs a live ScriptRunContext, which this CLI
    doesn't have. Same trick test_tagger.py uses; the harness reuses tagger_page's
    real classification functions rather than re-implementing them."""
    src = open(os.path.join(_SCRIPT_DIR, 'tagger_page.py'), encoding='utf-8').read()
    src = src.replace('\nrender()\n', '\n')
    mod = types.ModuleType('tagger_page_under_eval')
    mod.__file__ = os.path.join(_SCRIPT_DIR, 'tagger_page.py')
    exec(compile(src, 'tagger_page.py', 'exec'), mod.__dict__)
    return mod


tp = _load_tagger_module()

# config name -> (send amount/date/recurrence context, include persona in system prompt)
CONFIGS = {
    'bare':        {'enriched': False, 'persona': True},
    'enriched':    {'enriched': True,  'persona': True},
    'persona-off': {'enriched': False, 'persona': False},
    'persona-on':  {'enriched': False, 'persona': True},
}


class _NullProgress:
    """Stand-in for the Streamlit progress bar tagger_page's functions expect —
    the CLI harness has no UI to update."""
    def progress(self, *_a, **_k):
        pass


def load_vendor_transactions(path, vendor_col='Vendor', amount_col='Amount', date_col='Date'):
    """Read a prior tagged workbook's Tagged sheet, or a raw consolidated file, for
    its Vendor/Amount/Date rows. Only these columns are used — the harness re-derives
    tags itself per config, it never trusts a prior run's Tag column as ground truth."""
    if path.lower().endswith(('.xlsx', '.xls')):
        xl = pd.ExcelFile(path)
        sheet = 'Tagged' if 'Tagged' in xl.sheet_names else xl.sheet_names[0]
        df = xl.parse(sheet)
    else:
        df = pd.read_csv(path)
    missing = [c for c in (vendor_col, amount_col) if c not in df.columns]
    if missing:
        raise ValueError(f'{path} missing required column(s): {missing}')
    if date_col not in df.columns:
        date_col = None
    return df, date_col


def amount_count_map(df, vendor_col, amount_col):
    """Vendor -> (summed amount, transaction count), for scoring's Amount/Count cols."""
    amounts = df[amount_col].apply(tp._parse_amount).fillna(0.0)
    grp = pd.DataFrame({'Vendor': df[vendor_col], 'Amount': amounts}).groupby('Vendor')
    return grp['Amount'].sum().to_dict(), grp.size().to_dict()


def build_client_context(client_id, entity_type, primary, secondary):
    """Same real inputs production tagging uses: full generic tag list, this
    client's subcategory history, and Card A's client rules file (if any)."""
    return {
        'entity_type': entity_type, 'primary': primary, 'secondary': secondary,
        'generic_tags': tp._load_generic_tags(),
        'subcategory_vocab': tp._subcategory_vocab_for_prompt(client_id, []),
        'rules': tp._load_client_rules(client_id),
    }


def tag_vendors_under_config(vendor_names, df, date_col, amount_col, ctx, api_key, config_name):
    """One pass of the real tagging pipeline under a given config. Returns {vendor: tag}."""
    cfg = CONFIGS[config_name]
    sys_prompt = tp._build_system_prompt(
        ctx['entity_type'], ctx['primary'], ctx['secondary'], [], ctx['generic_tags'],
        ctx['subcategory_vocab'], ctx['rules'], include_persona=cfg['persona'])
    vendor_stats = tp._vendor_stats(df, amount_col, date_col) if cfg['enriched'] else None
    results = tp._run_claude_on_vendors(vendor_names, api_key, sys_prompt, _NullProgress(), vendor_stats)
    return {v: r.get('tag', 'Review with Client') for v, r in results.items()}


def compute_drift(tags_run1, tags_run2):
    """Run-to-run drift: fraction of vendors whose tag changed between two identical
    passes of the same config. Guards against 'accuracy gain via instability'."""
    vendors = set(tags_run1) & set(tags_run2)
    if not vendors:
        return 0.0, []
    changed = [v for v in vendors if tags_run1[v] != tags_run2[v]]
    return len(changed) / len(vendors), sorted(changed)


def score_config(vendor_names, tags_map, amount_map, count_map, truth_df):
    """Pure scoring — no API calls. tags_map: {vendor: tag} from one pass.
    Returns (score_dict from tag_compare.score_accuracy, full compared DataFrame)."""
    vendor_df = pd.DataFrame([
        {'Vendor': v, 'Tag': tags_map.get(v, 'Review with Client'),
         'Amount': amount_map.get(v, 0.0), 'Count': count_map.get(v, 0)}
        for v in vendor_names
    ])
    compared = compare_vendor_tags(vendor_df, truth_df)
    return score_accuracy(compared), compared


def run_config(config_name, vendor_names, df, date_col, amount_col, amt_map, cnt_map,
                truth_df, ctx, api_key):
    """Run one config twice (consistency check), score the second pass, report drift."""
    run1 = tag_vendors_under_config(vendor_names, df, date_col, amount_col, ctx, api_key, config_name)
    run2 = tag_vendors_under_config(vendor_names, df, date_col, amount_col, ctx, api_key, config_name)
    drift_pct, drifted = compute_drift(run1, run2)
    score, compared = score_config(vendor_names, run2, amt_map, cnt_map, truth_df)
    return {'config': config_name, 'score': score, 'compared': compared,
            'drift_pct': drift_pct, 'drifted_vendors': drifted}


def build_compare_table(results, baseline_config=None):
    """Console side-by-side summary. baseline_config (defaults to first result)
    is used for the '+N correct, M regressions' delta note."""
    baseline = baseline_config or results[0]['config']
    base = next(r for r in results if r['config'] == baseline)
    base_match = dict(zip(base['compared']['Vendor'], base['compared']['match']))

    lines = [f"{'Config':<14}{'Accuracy(vendor-scope)':<26}{'Misses':<8}{'Drift':<8}Notes"]
    for r in results:
        s = r['score']
        acc = f"{s['accuracy']*100:.0f}% ({s['n_correct']}/{s['n_total']})"
        note = ''
        if r['config'] != baseline:
            note = _delta_note(r['compared'], base_match)
        lines.append(f"{r['config']:<14}{acc:<26}{len(s['misses']):<8}{r['drift_pct']*100:.0f}%     {note}")
    return '\n'.join(lines)


def _delta_note(compared, base_match):
    cur_match = dict(zip(compared['Vendor'], compared['match']))
    shared = set(cur_match) & set(base_match)
    new_correct = sum(1 for v in shared if cur_match[v] and not base_match[v])
    regressions = sum(1 for v in shared if not cur_match[v] and base_match[v])
    return f'+{new_correct} correct, {regressions} regressions'


def write_eval_csv(results, client_id, year, out_dir):
    frames = []
    for r in results:
        c = r['compared'].copy()
        c.insert(0, 'Config', r['config'])
        frames.append(c)
    out = pd.concat(frames, ignore_index=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(out_dir, f'{client_id}_{year}_eval_{ts}.csv')
    out.to_csv(path, index=False)
    return path


def _infer_year(path, explicit_year):
    if explicit_year:
        return explicit_year
    import re
    m = re.search(r'(20\d{2})', os.path.basename(path))
    return m.group(1) if m else datetime.now().strftime('%Y')


def run(client_id, vendor_data_path, answer_key_path, config_names, api_key,
        entity_type='', primary='', secondary='', year=None, out_dir=None):
    out_dir = out_dir or _DEFAULT_EVALS_DIR
    os.makedirs(out_dir, exist_ok=True)
    year = _infer_year(answer_key_path, year)

    df, date_col = load_vendor_transactions(vendor_data_path)
    amt_map, cnt_map = amount_count_map(df, 'Vendor', 'Amount')
    vendor_names = df['Vendor'].dropna().unique().tolist()
    truth_df = load_truth_csv(answer_key_path)
    ctx = build_client_context(client_id, entity_type, primary, secondary)

    results = [
        run_config(cfg, vendor_names, df, date_col, 'Amount', amt_map, cnt_map, truth_df, ctx, api_key)
        for cfg in config_names
    ]
    print(build_compare_table(results))
    for r in results:
        print(f"  {r['config']}: {r['score']['structural_count']} structural (out of tagger scope), "
              f"{len(r['drifted_vendors'])} vendor(s) drifted between runs")
    csv_path = write_eval_csv(results, client_id, year, out_dir)
    print(f'\nFull per-vendor detail → {csv_path}')
    return results


def main():
    p = argparse.ArgumentParser(description='Card 4.2 — vendor-level tagging eval harness')
    p.add_argument('client_id')
    p.add_argument('vendor_data_file', help='Prior tagged workbook (.xlsx) or raw consolidated file with Vendor/Amount/Date')
    p.add_argument('answer_key_csv', help='vendor_name, correct_category[, scope]')
    p.add_argument('--config', default='bare', help='Single config to run (default: bare)')
    p.add_argument('--compare', help='Comma-separated configs to run side-by-side, e.g. bare,enriched')
    p.add_argument('--api-key', default=os.environ.get('ANTHROPIC_API_KEY', ''))
    p.add_argument('--year')
    p.add_argument('--out-dir')
    p.add_argument('--entity-type', default='')
    p.add_argument('--primary', default='')
    p.add_argument('--secondary', default='')
    args = p.parse_args()

    config_names = args.compare.split(',') if args.compare else [args.config]
    bad = [c for c in config_names if c not in CONFIGS]
    if bad:
        print(f'Error: unknown config(s) {bad} — choose from {list(CONFIGS)}', file=sys.stderr)
        sys.exit(1)
    if not args.api_key:
        print('Error: --api-key or ANTHROPIC_API_KEY env var required', file=sys.stderr)
        sys.exit(1)

    try:
        run(args.client_id, args.vendor_data_file, args.answer_key_csv, config_names, args.api_key,
            args.entity_type, args.primary, args.secondary, args.year, args.out_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
