#!/usr/bin/env python3
"""
Regression tests for Cards 3.5 (vendor_diff.py), 4.2 (eval_tagger.py), and A
(tagger_page.py enrichment additions).

All-synthetic data only — no client files, no live Claude API calls. Mirrors
test_tagger.py / test_regression.py's runner style.

Usage:
  python test_cards.py              # run all tests
  python test_cards.py -v           # verbose: print traceback on error
  python test_cards.py drift        # run only tests whose name contains 'drift'
"""
import os
import sys
import tempfile

import pandas as pd

import eval_tagger as ev
import tag_compare as tc
import vendor_diff as vd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
tp = ev.tp  # reuse eval_tagger's already-loaded (render()-stripped) tagger_page module


# ── tag_compare.py — shared core ─────────────────────────────────────────────

def test_load_truth_csv_defaults_scope_to_vendor():
    with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, newline='') as f:
        f.write('vendor_name,correct_category\nACME,Supplies\n')
        path = f.name
    try:
        df = tc.load_truth_csv(path)
        assert df.iloc[0]['scope'] == 'vendor'
    finally:
        os.unlink(path)


def test_compare_vendor_tags_bounded_by_truth_coverage():
    vendor_df = pd.DataFrame([
        {'Vendor': 'A', 'Tag': 'Supplies', 'Amount': -10.0, 'Count': 1},
        {'Vendor': 'B', 'Tag': 'Meals', 'Amount': -20.0, 'Count': 1},
    ])
    truth_df = pd.DataFrame([{'vendor_name': 'A', 'correct_category': 'Supplies', 'scope': 'vendor'}])
    compared = tc.compare_vendor_tags(vendor_df, truth_df)
    assert list(compared['Vendor']) == ['A']  # B absent from truth, excluded
    assert compared.iloc[0]['match'] is True or compared.iloc[0]['match'] == True


def test_score_accuracy_excludes_structural_from_denominator():
    compared = pd.DataFrame([
        {'Vendor': 'A', 'Tag': 'Supplies', 'correct_category': 'Supplies', 'Amount': -10.0,
         'Count': 1, 'scope': 'vendor', 'match': True},
        {'Vendor': 'B', 'Tag': 'Meals', 'correct_category': 'Travel', 'Amount': -10.0,
         'Count': 1, 'scope': 'vendor', 'match': False},
        {'Vendor': 'C', 'Tag': 'Wages', 'correct_category': 'Wages Split', 'Amount': -10.0,
         'Count': 1, 'scope': 'structural', 'match': False},
    ])
    score = tc.score_accuracy(compared)
    assert score['n_total'] == 2  # structural excluded
    assert score['n_correct'] == 1
    assert score['accuracy'] == 0.5
    assert score['structural_count'] == 1
    assert list(score['misses']['Vendor']) == ['B']


def test_aggregate_tagged_output_sums_amount_and_counts_txns():
    df = pd.DataFrame([
        {'Vendor': 'A', 'Tag': 'Supplies', 'Amount': -10.0},
        {'Vendor': 'A', 'Tag': 'Supplies', 'Amount': -5.0},
    ])
    agg = tc.aggregate_tagged_output(df)
    row = agg[agg['Vendor'] == 'A'].iloc[0]
    assert row['Amount'] == -15.0
    assert row['Count'] == 2


# ── Card 3.5 — vendor_diff.py ────────────────────────────────────────────────

def _card35_fixture():
    """6 vendors mistagged identically (class remap, >=5 threshold) + 1 one-off
    + 1 already-correct + 1 ambiguous-truth vendor (excluded, not seeded)."""
    cc_vendors = [f'CARD PMT {i}' for i in range(6)]
    rows = [{'Vendor': v, 'Tag': 'Bank Charges', 'Amount': -100.0} for v in cc_vendors]
    rows.append({'Vendor': 'RANDOM VENDOR', 'Tag': 'Supplies', 'Amount': -50.0})
    rows.append({'Vendor': 'CORRECT VENDOR', 'Tag': 'Meals', 'Amount': -20.0})
    rows.append({'Vendor': 'AMBIGUOUS', 'Tag': 'Personal - Not Deductible', 'Amount': -30.0})
    tagged_df = pd.DataFrame(rows)

    truth_rows = [{'vendor_name': v, 'correct_category': 'Cost of Goods Sold', 'scope': 'vendor'}
                  for v in cc_vendors]
    truth_rows.append({'vendor_name': 'RANDOM VENDOR', 'correct_category': 'Meals', 'scope': 'vendor'})
    truth_rows.append({'vendor_name': 'CORRECT VENDOR', 'correct_category': 'Meals', 'scope': 'vendor'})
    truth_rows.append({'vendor_name': 'AMBIGUOUS', 'correct_category': 'Cost of Goods Sold', 'scope': 'vendor'})
    truth_rows.append({'vendor_name': 'AMBIGUOUS', 'correct_category': 'Rents', 'scope': 'vendor'})
    truth_df = pd.DataFrame(truth_rows)

    vendor_agg = tc.aggregate_tagged_output(tagged_df)
    compared = tc.compare_vendor_tags(vendor_agg, truth_df)
    return compared, truth_df


def test_class_remap_becomes_proposed_rule_not_seed():
    compared, truth_df = _card35_fixture()
    rule_rows, seed_rows, excluded = vd.classify_disagreements(compared, truth_df)
    assert set(rule_rows['Vendor']) == {f'CARD PMT {i}' for i in range(6)}
    assert 'CARD PMT 0' not in set(seed_rows['Vendor'])


def test_one_off_disagreement_becomes_seed_row():
    compared, truth_df = _card35_fixture()
    _, seed_rows, _ = vd.classify_disagreements(compared, truth_df)
    seed = vd.build_seed(seed_rows)
    assert dict(zip(seed['Vendor'], seed['Category'])) == {'RANDOM VENDOR': 'Meals'}


def test_ambiguous_truth_vendor_excluded_never_seeded():
    compared, truth_df = _card35_fixture()
    _, seed_rows, excluded = vd.classify_disagreements(compared, truth_df)
    assert 'AMBIGUOUS' not in set(seed_rows['Vendor'])
    assert 'AMBIGUOUS' in set(excluded['Vendor'])


def test_already_correct_vendor_not_in_disagreement_report():
    compared, _ = _card35_fixture()
    diff = vd.build_disagreement_report(compared)
    assert 'CORRECT VENDOR' not in set(diff['Vendor'])


def test_proposed_rules_text_names_the_observed_tag_pair():
    compared, truth_df = _card35_fixture()
    rule_rows, _, _ = vd.classify_disagreements(compared, truth_df)
    text = vd.build_proposed_rules(rule_rows)
    assert 'Bank Charges' in text and 'Cost of Goods Sold' in text
    assert 'CONFIRM' in text  # never auto-promoted


# ── Card 4.2 — eval_tagger.py ─────────────────────────────────────────────────

def test_compute_drift_counts_changed_vendors_only():
    run1 = {'A': 'Supplies', 'B': 'Meals'}
    run2 = {'A': 'Supplies', 'B': 'Travel'}
    drift_pct, drifted = ev.compute_drift(run1, run2)
    assert drift_pct == 0.5
    assert drifted == ['B']


def test_score_config_matches_tag_compare_math():
    truth_df = pd.DataFrame([
        {'vendor_name': 'A', 'correct_category': 'Supplies', 'scope': 'vendor'},
        {'vendor_name': 'B', 'correct_category': 'Meals', 'scope': 'vendor'},
    ])
    tags_map = {'A': 'Supplies', 'B': 'Travel'}
    score, compared = ev.score_config(['A', 'B'], tags_map, {'A': -10, 'B': -20}, {'A': 1, 'B': 1}, truth_df)
    assert score['n_correct'] == 1 and score['n_total'] == 2
    assert len(compared) == 2


def test_delta_note_reports_new_correct_and_regressions():
    base = pd.DataFrame([{'Vendor': 'A', 'match': True}, {'Vendor': 'B', 'match': False}])
    cur = pd.DataFrame([{'Vendor': 'A', 'match': False}, {'Vendor': 'B', 'match': True}])
    base_match = dict(zip(base['Vendor'], base['match']))
    note = ev._delta_note(cur, base_match)
    assert note == '+1 correct, 1 regressions'


def test_amount_count_map_aggregates_per_vendor():
    df = pd.DataFrame([{'Vendor': 'A', 'Amount': '-10.00'}, {'Vendor': 'A', 'Amount': '-5.00'}])
    amt_map, cnt_map = ev.amount_count_map(df, 'Vendor', 'Amount')
    assert amt_map['A'] == -15.0 and cnt_map['A'] == 2


# ── Card A — tagger_page.py enrichment ───────────────────────────────────────

def test_vendor_stats_includes_recurrence_and_amount_signal():
    df = pd.DataFrame([
        {'Vendor': 'A', 'Amount': '-10.00', 'Date': '01/05/2025'},
        {'Vendor': 'A', 'Amount': '-12.00', 'Date': '02/05/2025'},
    ])
    stats = tp._vendor_stats(df, 'Amount', 'Date')
    assert stats['A']['txn_count'] == 2
    assert stats['A']['amount_total'] == -22.0
    assert stats['A']['amount_sample'] == '-12.0 to -10.0'
    assert stats['A']['date_span'] == 'Jan-Feb'


def test_tag_batch_payload_carries_stats_but_not_extra_keys():
    batch = [{'vendor': 'A', 'amount_total': -22.0, 'txn_count': 2, 'junk': 'nope'}]
    import json
    captured = {}

    class _FakeMsg:
        content = [type('C', (), {'text': '[]'})()]

    class _FakeMessages:
        def create(self, **kwargs):
            captured['system'] = kwargs['system']
            captured['payload'] = kwargs['messages'][0]['content']
            return _FakeMsg()

    class _FakeClient:
        def __init__(self, api_key):
            self.messages = _FakeMessages()

    real_anthropic = tp.anthropic
    tp.anthropic = type('M', (), {'Anthropic': _FakeClient})
    try:
        tp._tag_batch(batch, 'fake-key', 'sys prompt')
    finally:
        tp.anthropic = real_anthropic
    payload_json = captured['payload'].split('\n', 1)[1]
    parsed = json.loads(payload_json)
    assert parsed[0]['amount_total'] == -22.0
    assert parsed[0]['txn_count'] == 2
    assert 'junk' not in parsed[0]


def test_load_client_rules_absent_file_returns_empty():
    assert tp._load_client_rules('__no_such_client_id__') == []


def test_load_client_rules_skips_comments_and_blanks():
    path = tp._rules_path('__test_rules_client__')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('# comment\n\nCredit-card payments are COGS.\n')
    try:
        rules = tp._load_client_rules('__test_rules_client__')
        assert rules == ['Credit-card payments are COGS.']
    finally:
        os.unlink(path)


def test_build_system_prompt_persona_off_omits_persona():
    prompt_on = tp._build_system_prompt('Sole Prop', 'Consulting', '', [], ['Supplies'],
                                         include_persona=True)
    prompt_off = tp._build_system_prompt('Sole Prop', 'Consulting', '', [], ['Supplies'],
                                          include_persona=False)
    assert 'Consulting' in prompt_on
    assert 'Consulting' not in prompt_off


def test_build_system_prompt_injects_client_rules():
    prompt = tp._build_system_prompt('Sole Prop', 'Consulting', '', [], ['Supplies'],
                                      rules=['Credit-card payments are COGS.'])
    assert 'Credit-card payments are COGS.' in prompt
    assert 'Client-specific rules' in prompt


def test_build_system_prompt_absent_rules_matches_prior_behavior():
    prompt = tp._build_system_prompt('Sole Prop', 'Consulting', '', [], ['Supplies'])
    assert 'Client-specific rules' not in prompt


# ── Test runner (mirrors test_tagger.py style) ────────────────────────────────
_TESTS = [(name, fn) for name, fn in list(globals().items())
          if name.startswith('test_') and callable(fn)]


def main():
    args = sys.argv[1:]
    verbose = '-v' in args
    filter_name = next((a for a in args if not a.startswith('-')), None)

    tests = _TESTS
    if filter_name:
        tests = [(n, f) for n, f in _TESTS if filter_name.lower() in n.lower()]
        if not tests:
            print(f"No test cases match '{filter_name}'")
            sys.exit(1)

    print(f"\nRunning {len(tests)} card test(s)...\n")
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}")
            print(f"  {e}")
            failed += 1
        except Exception as e:
            print(f"FAIL  {name}")
            print(f"  ERROR: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            failed += 1

    print(f"\n{'─' * 42}")
    print(f"  {passed} passed  |  {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
