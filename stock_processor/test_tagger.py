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
import re
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


def test_get_auto_rule():
    assert tp._get_auto_rule('ATM WITHDRAWAL FEE')['tag'] == 'Personal - Not Deductible'
    assert tp._get_auto_rule('MONTHLY SERVICE CHARGE')['subcategory'] == 'Bank Service Charges'
    assert tp._get_auto_rule('ACME COFFEE') is None
    # Debit-only rule must not fire on money in
    assert tp._get_auto_rule('ATM DEPOSIT', 'credit') is None


def test_overdraft_protection_transfer_is_contra_not_bank_charge():
    """A transfer from savings to cover an overdraft moves the client's own money;
    the plain OVERDRAFT fee rule must not catch it."""
    assert tp._get_auto_rule('Overdraft Protection Transfer')['tag'] == 'Personal - Contra'
    assert tp._get_auto_rule('OVERDRAFT FEE')['subcategory'] == 'Bank Service Charges'


def test_rule_and_mapping_tags_are_in_tag_list():
    tags = set(tp._load_generic_tags())
    assert all(t in tags for _, _, _, t in tp._AUTO_RULES if t)
    wave_map = tp._load_wave_mapping()
    assert all(t in tags for t in wave_map.values())
    assert all(w in tp._wave_categories(wave_map) for _, _, w, _ in tp._AUTO_RULES if w)


def test_load_generic_tags_includes_always_tags():
    tags = tp._load_generic_tags()
    assert 'Insurance - General' in tags
    assert 'Personal - Not Deductible' in tags
    assert 'Review with Client' in tags
    assert len(tags) >= 52


# ── Claude system prompt: subcategory vocabulary hinting (2026-07-14) ───────

def test_subcategory_vocab_for_prompt_is_wave_categories_plus_lookup_tab():
    """Claude picks from Wave categories, not from old free-text lookup history."""
    def _run():
        tp._save_lookup('testclient', [{'vendor_name': 'ACME Insurance', 'tag': 'Insurance - General',
                                        'subcategory': 'Old Free Label', 'source': 'preparer',
                                        'date_tagged': '2026-01-01'}])
        vocab = tp._subcategory_vocab_for_prompt('testclient', ['Office Supplies', 'Client Extra'])
        assert vocab.count('Office Supplies') == 1   # in shared mapping and Lookup tab
        assert 'Client Extra' in vocab and 'Utilities' in vocab
        assert 'Old Free Label' not in vocab
        assert '' not in vocab
    _with_temp_lookups_dir(_run)


def test_build_system_prompt_includes_wave_categories_when_present():
    prompt = tp._build_system_prompt('Sole Prop / SMLLC', 'Consulting', '', [], ['Supplies'],
                                     subcategory_vocab=['Office Supplies'])
    assert '- Office Supplies' in prompt
    assert 'Wave categories' in prompt
    assert 'propose' in prompt


def test_build_system_prompt_omits_wave_note_when_empty():
    prompt = tp._build_system_prompt('Sole Prop / SMLLC', 'Consulting', '', [], ['Supplies'])
    assert 'Wave categories (' not in prompt


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
        {'Vendor': 'B', 'Tag': 'Supplies', 'Subcategory': '', 'Tag_Source': 'claude'},
        {'Vendor': 'C', 'Tag': 'Review with Client', 'Subcategory': '', 'Tag_Source': 'flagged'},
        {'Vendor': 'D', 'Tag': '', 'Subcategory': '', 'Tag_Source': 'skipped'},
    ])
    entries = tp._collect_lookup_entries(df, 'Vendor')
    vendors = {e['vendor_name'] for e in entries}
    assert vendors == {'A', 'B'}


def test_collect_lookup_entries_uses_extracted_vendor_not_raw_description():
    """Card 1.1 regression: real-world evidence was 238300_lookup.csv keys like
    'Debit Card Purchase 04/25 07:30p #5800 WINGSTOP 1779 ALDEN M' — date/time/card
    embedded because df had no Vendor column when lookup entries were collected.
    Vendor is now set on df at Step 2 upload time (before any tagging), so
    _collect_lookup_entries must key on it instead of falling back to desc_col."""
    raw = 'Debit Card Purchase 04/25 07:30p #5800 WINGSTOP 1779 ALDEN M'
    df = pd.DataFrame([{'Description': raw, 'Vendor': tp._extract_vendor(raw),
                         'Tag': 'Meals', 'Subcategory': '', 'Tag_Source': 'preparer'}])
    entries = tp._collect_lookup_entries(df, 'Description')
    assert len(entries) == 1
    vendor_name = entries[0]['vendor_name']
    assert vendor_name == df.iloc[0]['Vendor']
    assert not re.search(r'\d{2}/\d{2}', vendor_name)
    assert not re.search(r'\d{1,2}:\d{2}[ap]', vendor_name)
    assert not re.search(r'#\d+', vendor_name)


def test_vendor_hit_rate_line_counts_unique_vendors():
    df = pd.DataFrame([
        {'Vendor': 'A', 'Tag_Source': 'lookup'},
        {'Vendor': 'A', 'Tag_Source': 'lookup'},  # repeat row for same vendor — should not double count
        {'Vendor': 'B', 'Tag_Source': 'lookup'},
        {'Vendor': 'C', 'Tag_Source': 'claude'},
        {'Vendor': 'D', 'Tag_Source': 'preparer'},
        {'Vendor': 'E', 'Tag_Source': 'rwc'},
        {'Vendor': 'F', 'Tag_Source': 'skipped'},  # no amount: excluded entirely
    ])
    line = tp._vendor_hit_rate_line(df)
    assert line == 'Memory: 2/5 vendors (40%) · Claude: 1 · Preparer: 2'


def test_vendor_hit_rate_line_handles_no_expense_vendors():
    df = pd.DataFrame([{'Vendor': 'A', 'Tag_Source': 'skipped'}])
    assert tp._vendor_hit_rate_line(df) == 'Memory: 0/0 vendors (0%) · Claude: 0 · Preparer: 0'


def test_load_lookup_migrates_auto_source_to_claude():
    def _run():
        entries = [{'vendor_name': 'OldVendor', 'tag': 'Supplies', 'subcategory': '',
                    'source': 'auto', 'date_tagged': '2026-01-01'}]
        tp._save_lookup('client_x', entries)
        loaded = tp._load_lookup('client_x')
        assert loaded.iloc[0]['source'] == 'claude'
    _with_temp_lookups_dir(_run)


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
    assert applied.iloc[0]['Tag_Source'] == 'claude'


def test_apply_all_tags_low_confidence_flagged():
    df = pd.DataFrame([{'Description': 'X', 'Amount': -10.0, 'Vendor': 'Unknown Vendor'}])
    vendor_tbl = pd.DataFrame([
        {'Vendor': 'Unknown Vendor', tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''},
    ])
    claude_results = {'Unknown Vendor': {'tag': 'Review with Client', 'subcategory': '',
                                         'confidence': 0.2, 'reason': 'unsure'}}
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, claude_results, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag_Source'] == 'flagged'


def test_apply_all_tags_credit_rows_are_tagged():
    df = pd.DataFrame([{'Description': 'DEPOSIT', 'Amount': 2000.0, 'Vendor': 'Card Deposit'}])
    vendor_tbl = pd.DataFrame([{'Vendor': 'Card Deposit', tp._COL_CATEGORY: 'SALES INCOME',
                                tp._COL_SUBCATEGORY: ''}])
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag'] == 'SALES INCOME'
    assert applied.iloc[0]['Tag_Source'] == 'preparer'


def test_apply_all_tags_row_without_amount_skipped():
    df = pd.DataFrame([{'Description': 'NOTE', 'Amount': '', 'Vendor': 'Note'},
                       {'Description': 'X', 'Amount': -5.0, 'Vendor': 'X'}])
    vendor_tbl = pd.DataFrame(columns=['Vendor', tp._COL_CATEGORY, tp._COL_SUBCATEGORY])
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag_Source'] == 'skipped'
    assert applied.iloc[0]['Tag'] == ''


# ── Wave mapping (2026-10-09) ────────────────────────────────────────────────

_WAVE_MAP = {('Office Supplies', 'any'): 'Supplies',
             ('Bank Interest', 'credit'): 'OTHER INCOME - ITEMIZE',
             ('Bank Interest', 'debit'): 'Interest Expense'}


def test_wave_tag_uses_direction_then_any():
    assert tp._wave_tag('Bank Interest', 'credit', _WAVE_MAP) == 'OTHER INCOME - ITEMIZE'
    assert tp._wave_tag('Bank Interest', 'debit', _WAVE_MAP) == 'Interest Expense'
    assert tp._wave_tag('Office Supplies', 'credit', _WAVE_MAP) == 'Supplies'
    assert tp._wave_tag('Unmapped', 'debit', _WAVE_MAP) == ''


def test_row_directions_signed_and_debit_only_columns():
    signed = pd.DataFrame({'Amount': [-5.0, 7.0, '']})
    assert list(tp._row_directions(signed, 'Amount')) == ['debit', 'credit', '']
    # A Subtracted-style column has no negatives: every row is money out
    debit_only = pd.DataFrame({'Subtracted': [5.0, 7.0]})
    assert list(tp._row_directions(debit_only, 'Subtracted')) == ['debit', 'debit']


def test_vendor_table_includes_credits_with_direction():
    df = pd.DataFrame([{'Description': 'a', 'Amount': -10.0, 'Vendor': 'ACME'},
                       {'Description': 'b', 'Amount': 500.0, 'Vendor': 'Card Deposit'}])
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', _empty_lookup_df())
    dirs = dict(zip(tbl['Vendor'], tbl[tp._COL_DIRECTION]))
    assert dirs == {'ACME': 'debit', 'Card Deposit': 'credit'}


def test_merge_edits_fills_category_from_wave_category():
    full = pd.DataFrame([{'Vendor': 'ACME', tp._COL_DIRECTION: 'debit',
                          tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''}])
    edited = full.copy()
    edited[tp._COL_SUBCATEGORY] = 'Office Supplies'
    merged = tp._merge_edits(full, edited, _WAVE_MAP)
    assert merged.iloc[0][tp._COL_CATEGORY] == 'Supplies'
    assert len(tp._pending_vendors(merged)) == 0


def test_apply_all_tags_wave_category_tag_follows_row_direction():
    df = pd.DataFrame([{'Description': 'i', 'Amount': 3.0, 'Vendor': 'Bank Interest'},
                       {'Description': 'i', 'Amount': -2.0, 'Vendor': 'Bank Interest'}])
    vendor_tbl = pd.DataFrame([{'Vendor': 'Bank Interest', tp._COL_DIRECTION: 'credit',
                                tp._COL_CATEGORY: 'OTHER INCOME - ITEMIZE',
                                tp._COL_SUBCATEGORY: 'Bank Interest'}])
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75,
                                 _empty_lookup_df(), wave_map=_WAVE_MAP)
    assert list(applied['Tag']) == ['OTHER INCOME - ITEMIZE', 'Interest Expense']


def _manual_lookup_df(rows):
    return pd.DataFrame([{'vendor_name': n, 'tag': t, 'subcategory': w, 'source': 'manual',
                          'date_tagged': '2026-10-09'} for n, t, w in rows])


def test_lookup_matches_hand_typed_name_inside_bank_vendor():
    match = tp._lookup_matcher(_manual_lookup_df([('Acme Pest', 'Repairs and Maintenance', 'Repairs & Maintenance')]))
    assert match('Recurring Card Transaction ACME PEST LLC 002 7342')['tag'] == 'Repairs and Maintenance'
    assert match('Recurring Card Transaction ACME  PEST LLC')['tag'] == 'Repairs and Maintenance'  # spacing
    assert match('KLMN Supply') is None


def test_lookup_longest_name_wins_and_exact_first():
    match = tp._lookup_matcher(_manual_lookup_df([
        ('Acme', 'Supplies', 'Office Supplies'),
        ('Acme Power', 'Utilities', 'Utilities'),
        ('Acme Power Online Pmt 123', 'Rents', 'Rent Expense')]))
    assert match('ACME POWER Online Pmt 999')['tag'] == 'Utilities'
    assert match('Acme Power Online Pmt 123')['tag'] == 'Rents'
    assert match('Acme Store')['tag'] == 'Supplies'


def test_lookup_name_needs_whole_words_and_min_length():
    match = tp._lookup_matcher(_manual_lookup_df([('IRS', 'Taxes and Licenses', ''),
                                                  ('Ab', 'Supplies', '')]))
    assert match('IRS USATAXPYMT')['tag'] == 'Taxes and Licenses'
    assert match('FIRST BANK') is None       # 'irs' inside a word
    assert match('Ab Store') is None         # 2-letter name ignored (exact still works)
    assert match('Ab')['tag'] == 'Supplies'


def test_vendor_table_uses_contained_lookup_match():
    df = pd.DataFrame([{'Description': 'x', 'Amount': -5.0, 'Vendor': 'Card Transaction ACME PEST 4899'}])
    lk = _manual_lookup_df([('Acme Pest', 'Repairs and Maintenance', 'Repairs & Maintenance')])
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', lk, {}, _WAVE_MAP)
    assert tbl.iloc[0][tp._COL_CATEGORY] == 'Repairs and Maintenance'
    assert tbl.iloc[0]['Source'] == '📋 Lookup'
    applied = tp._apply_all_tags(df, 'Description', 'Amount', tbl, {}, 0.75, lk, wave_map=_WAVE_MAP)
    assert applied.iloc[0]['Tag_Source'] == 'lookup'


def test_claude_new_wave_name_is_flagged_for_review():
    df = pd.DataFrame([{'Description': 'x', 'Amount': -10.0, 'Vendor': 'KLMN Spirits'}])
    vendor_tbl = pd.DataFrame([{'Vendor': 'KLMN Spirits', tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''}])
    claude = {'KLMN Spirits': {'tag': 'Cost of Goods Sold', 'subcategory': 'Cost of Goods Sold - Beverages',
                               'confidence': 0.95, 'reason': ''}}
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, claude, 0.75,
                                 _empty_lookup_df(), wave_map=_WAVE_MAP)
    assert applied.iloc[0]['Tag_Source'] == 'flagged'
    assert applied.iloc[0]['Tag'] == 'Cost of Goods Sold'


def test_pretag_new_wave_name_marked_in_source():
    df = pd.DataFrame([{'Description': 'x', 'Amount': -10.0, 'Vendor': 'KLMN Spirits'},
                       {'Description': 'y', 'Amount': -5.0, 'Vendor': 'ACME Paper'}])
    pretag = {'KLMN Spirits': {'tag': 'Cost of Goods Sold', 'subcategory': 'COGS - Beverages',
                               'confidence': 0.9, 'source': '🤖 Claude'},
              'ACME Paper': {'tag': 'Supplies', 'subcategory': 'Office Supplies',
                             'confidence': 0.9, 'source': '🤖 Claude'}}
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', _empty_lookup_df(), pretag, _WAVE_MAP)
    src = dict(zip(tbl['Vendor'], tbl['Source']))
    assert src == {'KLMN Spirits': '🤖 Claude 🆕', 'ACME Paper': '🤖 Claude'}


def test_add_client_wave_categories_appends_and_skips_known():
    def _run():
        added = tp._add_client_wave_categories('addtest', [('COGS - Beverages', 'Cost of Goods Sold'),
                                                           ('office supplies', 'Supplies'),
                                                           ('', 'Supplies')])
        assert added == ['COGS - Beverages']
        m = tp._load_wave_mapping('addtest')
        assert m[('COGS - Beverages', 'any')] == 'Cost of Goods Sold'
        assert tp._add_client_wave_categories('addtest', [('COGS - Beverages', 'Cost of Goods Sold')]) == []
    _with_temp_lookups_dir(_run)


def test_new_wave_rows_from_output_uses_most_common_tag():
    df = pd.DataFrame([
        {'Tag': 'Cost of Goods Sold', 'Subcategory': 'COGS - Beverages'},
        {'Tag': 'Cost of Goods Sold', 'Subcategory': 'COGS - Beverages'},
        {'Tag': 'Supplies', 'Subcategory': 'COGS - Beverages'},
        {'Tag': 'Supplies', 'Subcategory': 'Office Supplies'},          # already mapped
        {'Tag': 'Review with Client', 'Subcategory': 'Unsure Thing'},   # not accepted
        {'Tag': 'Supplies', 'Subcategory': ''}])
    assert tp._new_wave_rows_from_output(df, _WAVE_MAP) == [('COGS - Beverages', 'Cost of Goods Sold')]


def test_client_wave_mapping_adds_and_overrides_shared():
    def _run():
        pd.DataFrame([{'wave_category': 'ACME CHECKING (123)', 'direction': 'any', 'tag': 'Personal - Contra'},
                      {'wave_category': 'Office Supplies', 'direction': 'any', 'tag': 'Tools'}]
                     ).to_csv(tp._wave_mapping_path('wavetest'), index=False)
        m = tp._load_wave_mapping('wavetest')
        assert m[('ACME CHECKING (123)', 'any')] == 'Personal - Contra'
        assert m[('Office Supplies', 'any')] == 'Tools'
        assert tp._load_wave_mapping()[('Office Supplies', 'any')] == 'Supplies'
    _with_temp_lookups_dir(_run)


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


# ── Card 1.4a — attribution overwrite regression ─────────────────────────────

def test_apply_all_tags_untouched_pretag_vendor_gets_claude_source():
    """Pre-tag mode: a vendor Claude tagged and the preparer never edited must be
    labeled 'claude' with Claude's own confidence — the W1 bug had ALL such rows
    mislabeled 'preparer' at confidence 1.0 because _build_prep_map only compared
    against lookup history, never against the pretag suggestion itself."""
    df = pd.DataFrame([{'Description': 'NEWCO PURCHASE', 'Amount': -50.0, 'Vendor': 'NewCo'}])
    pretag_results = {'NewCo': {'tag': 'Supplies', 'subcategory': 'Office Supplies',
                                 'confidence': 0.82, 'reason': 'x', 'source': '🤖 Claude'}}
    vendor_tbl = tp._build_vendor_table(df, 'Description', 'Amount', _empty_lookup_df(), pretag_results)
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75,
                                  _empty_lookup_df(), pretag_results)
    row = applied.iloc[0]
    assert row['Tag_Source'] == 'claude'
    assert row['Confidence'] == 0.82


def test_apply_all_tags_edited_pretag_vendor_gets_preparer_source():
    """If the preparer changes a vendor away from Claude's pretag suggestion,
    that's a genuine decision this session — source must be 'preparer' at confidence 1.0."""
    df = pd.DataFrame([{'Description': 'NEWCO PURCHASE', 'Amount': -50.0, 'Vendor': 'NewCo'}])
    pretag_results = {'NewCo': {'tag': 'Supplies', 'subcategory': 'Office Supplies',
                                 'confidence': 0.82, 'reason': 'x', 'source': '🤖 Claude'}}
    vendor_tbl = tp._build_vendor_table(df, 'Description', 'Amount', _empty_lookup_df(), pretag_results)
    vendor_tbl.loc[vendor_tbl['Vendor'] == 'NewCo', tp._COL_CATEGORY] = 'Meals'
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75,
                                  _empty_lookup_df(), pretag_results)
    row = applied.iloc[0]
    assert row['Tag'] == 'Meals'
    assert row['Tag_Source'] == 'preparer'
    assert row['Confidence'] == 1.0


def test_apply_all_tags_untouched_rule_vendor_gets_rule_source_not_preparer():
    """A vendor tagged by the deterministic personal-tag engine (⚡ Auto) and never
    touched by the preparer must not be miscounted as a preparer decision — same
    attribution bug class as 1.4a, caught for the rule engine while fixing Claude's."""
    df = pd.DataFrame([{'Description': 'ATM FEE', 'Amount': -3.0, 'Vendor': 'ATM WITHDRAWAL FEE'}])
    vendor_tbl = tp._build_vendor_table(df, 'Description', 'Amount', _empty_lookup_df())
    applied = tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, {}, 0.75, _empty_lookup_df())
    assert applied.iloc[0]['Tag_Source'] == 'rule'


# ── Card 1.4b — Review with Client routing regression ────────────────────────

def test_write_output_excel_routes_pretag_rwc_to_rwc_sheet_and_out_of_tagged():
    """Pre-tag mode: Claude/preparer can set Category directly to 'Review with Client'
    via the dropdown, which never sets Tag_Source='rwc' (that value only comes from the
    review-first flagged-vendor-correction path). RWC routing must key off Tag itself,
    not just Tag_Source, and RWC rows must not also appear on the Tagged sheet."""
    df = pd.DataFrame([
        {'Description': 'X', 'Amount': -10.0, 'Vendor': 'X', 'Tag': 'Review with Client',
         'Subcategory': '', 'Confidence': 0.82, 'Reason': '', 'Tag_Source': 'claude'},
        {'Description': 'Y', 'Amount': -20.0, 'Vendor': 'Y', 'Tag': 'Supplies',
         'Subcategory': '', 'Confidence': 1.0, 'Reason': '', 'Tag_Source': 'preparer'},
    ])
    buf = tp._write_output_excel(df, 'Description', 'Amount', None, {'client_id': 'rwc_test'})
    tagged = pd.read_excel(buf, sheet_name='Tagged')
    buf.seek(0)
    rwc = pd.read_excel(buf, sheet_name='Review with Client')
    assert list(rwc['Vendor']) == ['X']
    assert list(tagged['Vendor']) == ['Y']


def test_render_step5_rwc_metric_counts_pretag_rwc_rows():
    """Dashboard RWC count must match the RWC sheet — must catch Tag=='Review with
    Client' rows regardless of which code path set Tag_Source."""
    df = pd.DataFrame([
        {'Vendor': 'X', 'Tag': 'Review with Client', 'Tag_Source': 'claude'},
        {'Vendor': 'Y', 'Tag': 'Supplies', 'Tag_Source': 'preparer'},
    ])
    rwc = ((df['Tag'] == 'Review with Client') | (df['Tag_Source'] == 'rwc')).sum()
    assert rwc == 1


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
