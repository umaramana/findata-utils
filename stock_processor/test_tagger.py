#!/usr/bin/env python3
"""
Regression test suite for the Transaction Tagger (tagger_page.py).

All-synthetic data only — no client files, no live Claude API calls. Covers vendor
extraction, amount parsing, lookup CSV persistence, Lookup-tab vocabulary reading,
and the Category/Subcategory redesign (2026-07-14), including an explicit regression
test for the subcategory-erasure bug that redesign fixed.

Usage:
  python test_tagger.py              # run all tests
  python test_tagger.py -v           # verbose: print extra detail on pass
  python test_tagger.py vendor       # run only tests whose name contains 'vendor'
"""
import os
import sys
import tempfile
import types

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_tagger_module():
    """Import tagger_page.py without executing its module-level render() call.
    render() drives Streamlit UI and requires a live ScriptRunContext — it can't run
    in a plain script. Every other top-level statement in the file is a def/import,
    safe to exec directly."""
    src = open(os.path.join(_SCRIPT_DIR, 'tagger_page.py'), encoding='utf-8').read()
    src = src.replace('\nrender()\n', '\n')
    mod = types.ModuleType('tagger_page_under_test')
    mod.__file__ = os.path.join(_SCRIPT_DIR, 'tagger_page.py')
    exec(compile(src, 'tagger_page.py', 'exec'), mod.__dict__)
    return mod


tp = _load_tagger_module()


# ── Test cases: (name, callable) ─────────────────────────────────────────────
# Each test function takes no args, returns None on pass, raises AssertionError on fail.

def test_parse_amount():
    assert tp._parse_amount('-250.00') == -250.0
    assert tp._parse_amount('$1,234.56') == 1234.56
    assert tp._parse_amount('(100.00)') == -100.0
    assert tp._parse_amount('not a number') is None
    assert tp._parse_amount('') is None


def test_is_expense():
    assert tp._is_expense(-50) is True
    assert tp._is_expense(50) is False
    assert tp._is_expense('(50.00)') is True
    assert tp._is_expense('bad') is False


def test_extract_vendor_purchase_formats():
    # Capital One: "Card Purchase - MERCHANT CITY, STATE"
    assert 'STARBUCKS' in tp._extract_vendor('Card Purchase - STARBUCKS SEATTLE WA')
    # Citibank: abbrev + date/time + #card ref + | MERCHANT | Category
    result = tp._extract_vendor('Card Purchase 01/15 12:34 #1234 | TARGET STORE | Retail')
    assert 'TARGET STORE' in result


def test_extract_vendor_transfer_patterns():
    assert tp._extract_vendor('ZELLE PAYMENT TO JOHN SMITH REF123456') == 'Zelle: JOHN SMITH'
    assert tp._extract_vendor('ATM WITHDRAWAL AT MAIN ST') == 'ATM Withdrawal'
    assert tp._extract_vendor('ONLINE TRANSFER TO SAVINGS') == 'Online Transfer'
    assert tp._extract_vendor('CHECK #1042') == 'Check'
    assert 'Amazon' in tp._extract_vendor('AMAZON.COM*AB12CDE34')


def test_get_auto_personal_tag():
    assert tp._get_auto_personal_tag('ATM WITHDRAWAL FEE') == 'Personal - ATM'
    assert tp._get_auto_personal_tag('MONTHLY SERVICE CHARGE') == 'Personal - Bank Charges'
    assert tp._get_auto_personal_tag('STARBUCKS COFFEE') == ''


def test_load_generic_tags_includes_always_tags():
    tags = tp._load_generic_tags()
    assert 'Insurance - General' in tags
    assert 'Personal - Not Deductible' in tags
    assert 'Review with Client' in tags
    assert len(tags) >= 52


# ── Claude system prompt: subcategory vocabulary hinting (2026-07-14) ───────

def test_subcategory_vocab_for_prompt_combines_history_and_lookup_tab():
    def _run():
        tp._save_lookup('testclient', [{'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
                                        'subcategory': 'Health Insurance', 'source': 'preparer',
                                        'date_tagged': '2026-01-01'}])
        vocab = tp._subcategory_vocab_for_prompt('testclient', ['Office Supplies', 'Health Insurance'])
        # Deduped: 'Health Insurance' appears in both sources but only once in output.
        assert vocab.count('Health Insurance') == 1
        assert 'Office Supplies' in vocab
        assert '' not in vocab
    _with_temp_lookups_dir(_run)


def test_subcategory_vocab_for_prompt_empty_when_no_history():
    def _run():
        vocab = tp._subcategory_vocab_for_prompt('brand_new_client', [])
        assert vocab == []
    _with_temp_lookups_dir(_run)


def test_build_system_prompt_includes_subcategory_vocab_when_present():
    prompt = tp._build_system_prompt('Sole Prop / SMLLC', 'Consulting', '', [], ['Supplies'],
                                     subcategory_vocab=['Health Insurance'])
    assert 'Health Insurance' in prompt
    assert 'used these subcategory labels before' in prompt


def test_build_system_prompt_omits_subcategory_note_when_empty():
    prompt = tp._build_system_prompt('Sole Prop / SMLLC', 'Consulting', '', [], ['Supplies'])
    assert 'used these subcategory labels before' not in prompt


# ── Lookup tab vocabulary (in-file, optional) ────────────────────────────────

def _make_upload_with_lookup_tab(category_col='Category', subcategory_col='Subcategory',
                                  include_subcat=True):
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        pd.DataFrame({'Description': ['x'], 'Amount': [-1]}).to_excel(
            w, sheet_name='Master', index=False)
        lookup_data = {category_col: ['Insurance - General', 'Supplies']}
        if include_subcat:
            lookup_data[subcategory_col] = ['Health Insurance', 'Office Supplies']
        pd.DataFrame(lookup_data).to_excel(w, sheet_name='Lookup', index=False)
    buf.seek(0)
    return pd.ExcelFile(buf)


def test_load_lookup_tab_vocab_category_and_subcategory():
    xl = _make_upload_with_lookup_tab()
    cats, subcats, warn = tp._load_lookup_tab_vocab(xl)
    assert cats == ['Insurance - General', 'Supplies']
    assert subcats == ['Health Insurance', 'Office Supplies']
    assert warn is None


def test_load_lookup_tab_vocab_category_only():
    """Subcategory column is optional in the Lookup tab — no warning if absent."""
    xl = _make_upload_with_lookup_tab(include_subcat=False)
    cats, subcats, warn = tp._load_lookup_tab_vocab(xl)
    assert cats == ['Insurance - General', 'Supplies']
    assert subcats == []
    assert warn is None


def test_load_lookup_tab_vocab_no_lookup_tab():
    """No Lookup tab at all — optional, not an error."""
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        pd.DataFrame({'Description': ['x']}).to_excel(w, sheet_name='Master', index=False)
    buf.seek(0)
    xl = pd.ExcelFile(buf)
    cats, subcats, warn = tp._load_lookup_tab_vocab(xl)
    assert cats == [] and subcats == [] and warn is None


def test_load_lookup_tab_vocab_unrecognized_column_warns():
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        pd.DataFrame({'Description': ['x']}).to_excel(w, sheet_name='Master', index=False)
        pd.DataFrame({'NotesColumn': ['abc']}).to_excel(w, sheet_name='Lookup', index=False)
    buf.seek(0)
    xl = pd.ExcelFile(buf)
    cats, subcats, warn = tp._load_lookup_tab_vocab(xl)
    assert cats == [] and subcats == []
    assert warn is not None and 'Category' in warn


def test_load_lookup_tab_vocab_no_vendor_mapping():
    """Lookup tab is vocabulary-only — even if a vendor-like column is present,
    it must not be read as a vendor mapping (confirms the design boundary)."""
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        pd.DataFrame({'Description': ['x']}).to_excel(w, sheet_name='Master', index=False)
        pd.DataFrame({
            'Vendor': ['BlueCross', 'Staples'],
            'Category': ['Insurance - General', 'Supplies'],
        }).to_excel(w, sheet_name='Lookup', index=False)
    buf.seek(0)
    xl = pd.ExcelFile(buf)
    cats, subcats, warn = tp._load_lookup_tab_vocab(xl)
    # Only the Category vocabulary comes back — no per-vendor structure survives.
    assert cats == ['Insurance - General', 'Supplies']
    assert warn is None


def test_get_category_options_dedup():
    opts = tp._get_category_options(['Supplies', 'Insurance - General'], ['Supplies', 'New One'])
    assert opts[0] == ''
    assert opts.count('Supplies') == 1
    assert 'New One' in opts


def test_get_subcategory_options_dedup_and_blank_first():
    opts = tp._get_subcategory_options(['Health Insurance'], ['Health Insurance', 'Office Supplies'])
    assert opts[0] == ''
    assert opts.count('Health Insurance') == 1
    assert 'Office Supplies' in opts


# ── Lookup CSV persistence (uses a temp dir, never the real client lookups/) ──

def _with_temp_lookups_dir(fn):
    """Run fn with tp._LOOKUPS_DIR redirected to a temp dir, then restore it.
    Guarantees tests never touch stock_processor/lookups/ (real client data)."""
    orig = tp._LOOKUPS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        tp._LOOKUPS_DIR = tmp
        try:
            fn()
        finally:
            tp._LOOKUPS_DIR = orig


def test_lookup_csv_round_trip():
    def _run():
        entries = [{'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
                    'subcategory': 'Health Insurance', 'source': 'preparer',
                    'date_tagged': '2026-01-01'}]
        tp._save_lookup('testclient', entries)
        loaded = tp._load_lookup('testclient')
        assert len(loaded) == 1
        assert loaded.iloc[0]['tag'] == 'Insurance - General'
        assert loaded.iloc[0]['subcategory'] == 'Health Insurance'
    _with_temp_lookups_dir(_run)


def test_lookup_csv_overwrite_keeps_latest():
    def _run():
        tp._save_lookup('testclient', [{'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
                                        'subcategory': 'Health Insurance', 'source': 'preparer',
                                        'date_tagged': '2026-01-01'}])
        tp._save_lookup('testclient', [{'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
                                        'subcategory': 'Medical', 'source': 'preparer',
                                        'date_tagged': '2026-02-01'}])
        loaded = tp._load_lookup('testclient')
        assert len(loaded) == 1
        assert loaded.iloc[0]['subcategory'] == 'Medical'
    _with_temp_lookups_dir(_run)


def test_load_lookup_missing_file_returns_empty_frame():
    def _run():
        loaded = tp._load_lookup('nonexistent_client')
        assert loaded.empty
        assert list(loaded.columns) == ['vendor_name', 'tag', 'subcategory', 'source', 'date_tagged']
    _with_temp_lookups_dir(_run)


def test_collect_lookup_entries_only_auto_and_preparer():
    df = pd.DataFrame([
        {'Vendor': 'A', 'Tag': 'Supplies', 'Subcategory': '', 'Tag_Source': 'preparer'},
        {'Vendor': 'B', 'Tag': 'Supplies', 'Subcategory': '', 'Tag_Source': 'auto'},
        {'Vendor': 'C', 'Tag': 'Review with Client', 'Subcategory': '', 'Tag_Source': 'flagged'},
        {'Vendor': 'D', 'Tag': '', 'Subcategory': '', 'Tag_Source': 'income'},
    ])
    entries = tp._collect_lookup_entries(df, 'Vendor')
    vendors = {e['vendor_name'] for e in entries}
    assert vendors == {'A', 'B'}


# ── Category/Subcategory redesign (2026-07-14) — core behavior ──────────────

def _sample_txn_df():
    return pd.DataFrame([
        {'Description': 'BLUECROSS PREMIUM', 'Amount': -300.0, 'Vendor': 'BlueCross'},
        {'Description': 'BLUECROSS PREMIUM', 'Amount': -300.0, 'Vendor': 'BlueCross'},
        {'Description': 'STAPLES OFFICE', 'Amount': -45.0, 'Vendor': 'Staples'},
    ])


def test_build_vendor_table_prefills_category_and_subcategory_from_lookup():
    lookup_df = pd.DataFrame([
        {'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
         'subcategory': 'Health Insurance', 'source': 'preparer', 'date_tagged': '2026-01-01'},
    ])
    tbl = tp._build_vendor_table(_sample_txn_df(), 'Description', 'Amount', lookup_df)
    row = tbl[tbl['Vendor'] == 'BlueCross'].iloc[0]
    assert row[tp._COL_CATEGORY] == 'Insurance - General'
    assert row[tp._COL_SUBCATEGORY] == 'Health Insurance'
    # Unknown vendor: both blank, goes to Claude
    other = tbl[tbl['Vendor'] == 'Staples'].iloc[0]
    assert other[tp._COL_CATEGORY] == ''
    assert other[tp._COL_SUBCATEGORY] == ''


def _empty_lookup_df():
    return pd.DataFrame(columns=['vendor_name', 'tag', 'subcategory', 'source', 'date_tagged'])


def test_subcategory_erasure_bug_regression():
    """Regression test for the bug fixed 2026-07-14: a known vendor's Category
    auto-resolving from lookup history must NOT blank out its Subcategory, and
    the save-back to the lookup CSV must not silently overwrite it with a blank."""
    def _run():
        tp._save_lookup('erasure_test_client', [{
            'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
            'subcategory': 'Health Insurance', 'source': 'preparer', 'date_tagged': '2026-01-01'}])
        lookup_df = tp._load_lookup('erasure_test_client')
        df = _sample_txn_df()
        vendor_tbl = tp._build_vendor_table(df, 'Description', 'Amount', lookup_df)
        # Preparer touches nothing — simulates a repeat run where the vendor auto-resolves.
        applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, lookup_df)
        bluecross_rows = applied[applied['Vendor'] == 'BlueCross']
        assert (bluecross_rows['Tag'] == 'Insurance - General').all()
        assert (bluecross_rows['Subcategory'] == 'Health Insurance').all(), \
            'Subcategory was erased — the pre-redesign bug has regressed'
        # Untouched 'lookup' rows are not re-collected for saving (avoids bumping
        # date_tagged for vendors nobody acted on) — confirm the pre-existing CSV
        # entry survives a save cycle untouched, rather than being blanked out.
        entries = tp._collect_lookup_entries(applied, 'Description')
        assert not any(e['vendor_name'] == 'BlueCross' for e in entries), \
            'untouched lookup vendor should not be re-collected for saving'
        tp._save_lookup('erasure_test_client', entries)
        reloaded = tp._load_lookup('erasure_test_client')
        bc_row = reloaded[reloaded['vendor_name'] == 'BlueCross'].iloc[0]
        assert bc_row['subcategory'] == 'Health Insurance', \
            'Subcategory was erased on save-back — the pre-redesign bug has regressed'
    _with_temp_lookups_dir(_run)


def test_apply_all_tags_untouched_lookup_vendor_gets_lookup_source():
    """A vendor whose Category/Subcategory exactly match lookup CSV history —
    i.e. the preparer never touched it this session — must be labeled 'lookup',
    not 'preparer'. This is the fix for the previously-overloaded 'preparer' source."""
    lookup_df = pd.DataFrame([
        {'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
         'subcategory': 'Health Insurance', 'source': 'preparer', 'date_tagged': '2026-01-01'},
    ])
    df = _sample_txn_df()
    vendor_tbl = tp._build_vendor_table(df, 'Description', 'Amount', lookup_df)
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, lookup_df)
    bluecross_rows = applied[applied['Vendor'] == 'BlueCross']
    assert (bluecross_rows['Tag_Source'] == 'lookup').all()


def test_apply_all_tags_overriding_lookup_value_gets_preparer_source():
    """If the preparer changes a vendor away from its lookup-suggested value,
    that's a genuine decision this session — source must be 'preparer', not 'lookup'."""
    lookup_df = pd.DataFrame([
        {'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
         'subcategory': 'Health Insurance', 'source': 'preparer', 'date_tagged': '2026-01-01'},
    ])
    df = _sample_txn_df()
    vendor_tbl = tp._build_vendor_table(df, 'Description', 'Amount', lookup_df)
    # Preparer overrides the Category for BlueCross to something different.
    vendor_tbl.loc[vendor_tbl['Vendor'] == 'BlueCross', tp._COL_CATEGORY] = 'Insurance - Liability'
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, lookup_df)
    bluecross_rows = applied[applied['Vendor'] == 'BlueCross']
    assert (bluecross_rows['Tag'] == 'Insurance - Liability').all()
    assert (bluecross_rows['Tag_Source'] == 'preparer').all()


def test_apply_all_tags_category_and_subcategory_independent():
    """Category-only (no Subcategory) must not force any fallback value —
    this is the behavior that replaced the old Quick-Tag-derives-Subcategory logic."""
    df = pd.DataFrame([{'Description': 'X', 'Amount': -10.0, 'Vendor': 'X'}])
    vendor_tbl = pd.DataFrame([
        {'Vendor': 'X', tp._COL_CATEGORY: 'Supplies', tp._COL_SUBCATEGORY: ''},
    ])
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag'] == 'Supplies'
    assert applied.iloc[0]['Subcategory'] == ''
    assert applied.iloc[0]['Tag_Source'] == 'preparer'


def test_apply_all_tags_falls_back_to_claude_result():
    df = pd.DataFrame([{'Description': 'X', 'Amount': -10.0, 'Vendor': 'Unknown Vendor'}])
    vendor_tbl = pd.DataFrame([
        {'Vendor': 'Unknown Vendor', tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''},
    ])
    claude_results = {'Unknown Vendor': {'tag': 'Supplies', 'subcategory': 'Office Supplies',
                                         'confidence': 0.9, 'reason': 'looks like supplies'}}
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, claude_results, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag'] == 'Supplies'
    assert applied.iloc[0]['Subcategory'] == 'Office Supplies'
    assert applied.iloc[0]['Tag_Source'] == 'auto'


def test_apply_all_tags_low_confidence_flagged():
    df = pd.DataFrame([{'Description': 'X', 'Amount': -10.0, 'Vendor': 'Unknown Vendor'}])
    vendor_tbl = pd.DataFrame([
        {'Vendor': 'Unknown Vendor', tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''},
    ])
    claude_results = {'Unknown Vendor': {'tag': 'Review with Client', 'subcategory': '',
                                         'confidence': 0.2, 'reason': 'unsure'}}
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, claude_results, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag_Source'] == 'flagged'


def test_apply_all_tags_income_rows_skipped():
    df = pd.DataFrame([{'Description': 'PAYCHECK', 'Amount': 2000.0, 'Vendor': 'Employer'}])
    vendor_tbl = pd.DataFrame(columns=['Vendor', tp._COL_CATEGORY, tp._COL_SUBCATEGORY])
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag_Source'] == 'income'
    assert applied.iloc[0]['Tag'] == ''


def test_pending_vendors_gated_by_category_only():
    """Subcategory being blank must NOT make a vendor 'pending' — only Category does."""
    tbl = pd.DataFrame({
        'Vendor': ['A', 'B', 'C'],
        tp._COL_CATEGORY: ['Insurance - General', '', ''],
        tp._COL_SUBCATEGORY: ['', 'Some Subcat', ''],
    })
    pending = tp._pending_vendors(tbl)
    assert sorted(pending['Vendor'].tolist()) == ['B', 'C']


def test_merge_edits_writes_back_both_columns():
    full_tbl = pd.DataFrame({
        'Vendor': ['A', 'B'],
        tp._COL_CATEGORY: ['', ''],
        tp._COL_SUBCATEGORY: ['', ''],
    })
    edited = pd.DataFrame({
        'Vendor': ['A'],
        tp._COL_CATEGORY: ['Supplies'],
        tp._COL_SUBCATEGORY: ['Office Supplies'],
    })
    merged = tp._merge_edits(full_tbl, edited)
    row_a = merged[merged['Vendor'] == 'A'].iloc[0]
    assert row_a[tp._COL_CATEGORY] == 'Supplies'
    assert row_a[tp._COL_SUBCATEGORY] == 'Office Supplies'
    row_b = merged[merged['Vendor'] == 'B'].iloc[0]
    assert row_b[tp._COL_CATEGORY] == ''


def test_build_vendor_table_pretag_mode_source_labels():
    lookup_df = pd.DataFrame([
        {'vendor_name': 'BlueCross', 'tag': 'Insurance - General',
         'subcategory': 'Health Insurance', 'source': 'preparer', 'date_tagged': '2026-01-01'},
    ])
    df = pd.DataFrame([
        {'Description': 'BLUECROSS', 'Amount': -1.0, 'Vendor': 'BlueCross'},
        {'Description': 'ATM FEE', 'Amount': -3.0, 'Vendor': 'ATM WITHDRAWAL FEE'},
        {'Description': 'NEWCO', 'Amount': -5.0, 'Vendor': 'NewCo'},
    ])
    pretag_results = {'NewCo': {'tag': 'Supplies', 'subcategory': 'Office Supplies',
                                'confidence': 0.8, 'reason': 'x', 'source': '🤖 Claude'}}
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', lookup_df, pretag_results)
    src = dict(zip(tbl['Vendor'], tbl['Source']))
    assert src['BlueCross'] == '📋 Lookup'
    assert src['ATM WITHDRAWAL FEE'] == '⚡ Auto'
    assert src['NewCo'] == '🤖 Claude'


# ── Test runner (mirrors test_regression.py style) ───────────────────────────
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

    print(f"\nRunning {len(tests)} tagger test(s)...\n")
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
