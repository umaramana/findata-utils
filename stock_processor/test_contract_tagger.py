#!/usr/bin/env python3
"""
The tagger Contract (features/tagger/*.feature) run as tests with pytest-bdd.

Each step below drives the real code in tagger_page.py. Streamlit and the Claude API are
replaced by fakes (FakeSt, a stubbed _tag_batch or anthropic client); lookups are written to
a temp folder, never stock_processor/lookups. All names are invented (ACME, KLMN).

Usage (Windows python, from stock_processor):
  python -m pytest test_contract_tagger.py
"""
import io
import json
import re
import types

import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from test_tagger import tp

scenarios('features/tagger')

CLIENT = 'acme_contract'
Q = r'"(?P<{}>[^"]*)"'      # a quoted value in a step


def q(name):
    return Q.format(name)


# ── Fakes and shared helpers ─────────────────────────────────────────────────────

class FakeSt:
    """Stands in for streamlit: buttons in `clicks` are pressed, widgets return their
    default (or `answers[label]`), everything else is a no-op."""

    def __init__(self, clicks=(), answers=None):
        self.session_state = {}
        self.clicks = set(clicks)
        self.answers = answers or {}

    def button(self, label, *a, **k):
        return label in self.clicks

    def columns(self, spec, *a, **k):
        return [self] * (spec if isinstance(spec, int) else len(spec))

    def selectbox(self, label, options, index=0, **k):
        return self.answers.get(label, options[index])

    def radio(self, label, options, index=0, **k):
        return self.answers.get(label, options[index])

    def file_uploader(self, label, **k):
        return self.answers.get(label)

    def checkbox(self, label, **k):
        return self.answers.get(label, False)

    def progress(self, *a, **k):
        return self

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Prog:
    def progress(self, *a, **k):
        pass


@pytest.fixture
def ctx():
    return {}


@pytest.fixture(autouse=True)
def temp_lookups(tmp_path, monkeypatch):
    """Lookups and client Wave mappings go to a temp folder for every scenario."""
    monkeypatch.setattr(tp, '_LOOKUPS_DIR', str(tmp_path))
    return tmp_path


def _wave_map():
    return tp._load_wave_mapping(CLIENT)


def _empty_lookup():
    return pd.DataFrame(columns=['vendor_name', 'tag', 'subcategory', 'source', 'date_tagged'])


def _lookup_df(rows):
    return pd.DataFrame([{'vendor_name': v, 'tag': t, 'subcategory': s, 'source': 'manual',
                          'date_tagged': '2026-01-01'} for v, t, s in rows])


def _txn(vendor, amount, tag='', sub='', source='', date='2026-01-05', file='chk.pdf',
         desc=None, confidence=1.0):
    return {'Date': date, 'Description': desc or vendor, 'Amount': amount, 'Vendor': vendor,
            'Tag': tag, 'Subcategory': sub, 'Confidence': confidence, 'Reason': '',
            'Tag_Source': source, 'Filename': file}


def _contra(amount, file, date='2026-01-05', desc='ONLINE TRANSFER'):
    return _txn(desc, amount, tp._CONTRA_TAG, '', 'lookup', date, file, desc)


def _fake_claude(monkeypatch, answer):
    """Replace _tag_batch; answer(batch) gives Claude's items. Returns the batches sent."""
    sent = []

    def fake(batch, api_key, system_prompt):
        sent.append([dict(b) for b in batch])
        return answer(batch)
    monkeypatch.setattr(tp, '_tag_batch', fake)
    return sent


def _answer_all(tag='Supplies', subcategory='', confidence=0.9):
    return lambda batch: [{'id': i, 'tag': tag, 'subcategory': subcategory,
                           'confidence': confidence, 'reason': 'x'} for i in range(len(batch))]


def _tag_lines(prompt):
    block = prompt.split('Classify each vendor to exactly one tag from this list:\n', 1)[1]
    return [ln[2:] for ln in block.split('\n\n', 1)[0].split('\n')]


def _prompt(entity_type='S-Corp', primary='liquor store', specific=(), **kw):
    return tp._build_system_prompt(entity_type, primary, '', list(specific),
                                   tp._load_generic_tags(), **kw)


# Step 5 crashes (KeyError 'Subcategory') when no row has a Wave category, so runs that
# reach Step 5 carry one row with a mapped Wave category. Open defect, 22 Oct: see README.
_WAVE_ROW = dict(vendor='ACME PAPER', amount=-5.0, tag='Supplies', sub='Office Supplies', source='lookup')


def _show_step5(monkeypatch, df, clicks=()):
    fake = FakeSt(clicks)
    fake.session_state.update({'tagger_df': df, 'tagger_desc_col': 'Description',
                               'tagger_amount_col': 'Amount', 'tagger_date_col': 'Date',
                               'tagger_config': {'client_id': CLIENT}})
    monkeypatch.setattr(tp, 'st', fake)
    tp._render_step5()


def _apply(df, vendor_tbl, claude_results, lookup=None, threshold=0.75, pretag=None):
    lookup = _empty_lookup() if lookup is None else lookup
    return tp._apply_all_tags(df, 'Description', 'Amount', vendor_tbl, claude_results, threshold,
                              lookup, pretag, _wave_map())


def _pair(df, desc_col='Description'):
    return tp._pair_contras(df, 'Amount', 'Date', desc_col=desc_col)


def _xlsx(sheets):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        for name, d in sheets.items():
            d.to_excel(w, sheet_name=name, index=False)
    buf.seek(0)
    return buf


# ── 01 Vendor name ───────────────────────────────────────────────────────────────

@given(parsers.re('the bank description ' + q('desc')))
def _(ctx, desc):
    ctx['descs'] = [desc]


@given(parsers.re('the bank descriptions ' + q('a') + ' and ' + q('b')))
def _(ctx, a, b):
    ctx['descs'] = [a, b]


@given('a bank description of 120 letters with no noise')
def _(ctx):
    ctx['descs'] = ['ACMEKLMN' * 15]


@when('the vendor name is extracted')
@when('the vendor names are extracted')
def _(ctx):
    ctx['vendors'] = [tp._extract_vendor(d) for d in ctx['descs']]


@then(parsers.re('the vendor is ' + q('vendor')))
def _(ctx, vendor):
    assert ctx['vendors'] == [vendor]


@then(parsers.re('both vendors are ' + q('vendor')))
def _(ctx, vendor):
    assert ctx['vendors'] == [vendor, vendor]


@then(parsers.re('the bank description ' + q('desc') + ' gives the vendor ' + q('vendor')))
def _(desc, vendor):
    assert tp._extract_vendor(desc) == vendor


@then('the vendor is its first 80 characters')
def _(ctx):
    assert ctx['vendors'] == [ctx['descs'][0][:80]]


# ── 02 Money in or out ───────────────────────────────────────────────────────────

@given(parsers.re(r'an amount column holding (?P<amounts>.+)'))
def _(ctx, amounts):
    ctx['amounts'] = pd.DataFrame({'Amount': [a.strip() for a in amounts.split(',')]})


@when('the directions are read')
def _(ctx):
    ctx['directions'] = tp._row_directions(ctx['amounts'], 'Amount').tolist()


@then(parsers.re(r'the directions are (?P<directions>.+)'))
def _(ctx, directions):
    want = [d.strip().replace('(none)', '') for d in directions.split(',')]
    assert ctx['directions'] == want


@given(parsers.re(r'a row with Debit (?P<debit>[\d.]+) and a blank Credit'))
def _(ctx, debit):
    ctx.setdefault('dc_rows', []).append({'Description': 'ACME', 'Debit': debit, 'Credit': ''})


@given(parsers.re(r'a row with a blank Debit and Credit (?P<credit>[\d.]+)'))
def _(ctx, credit):
    ctx.setdefault('dc_rows', []).append({'Description': 'KLMN', 'Debit': '', 'Credit': credit})
    ctx['combine'] = dict(loaded=[('chk.csv', pd.DataFrame(ctx['dc_rows']), None, False)],
                          needed=['Description', 'Debit', 'Credit'],
                          amount_col='_signed_amount', debit_col='Debit', credit_col='Credit')


@given(parsers.re(r'a file marked as a credit card statement with a charge of (?P<charge>[\d.]+)'))
def _(ctx, charge):
    card = pd.DataFrame([{'Description': 'ACME HARDWARE', 'Amount': float(charge)}])
    ctx['combine'] = dict(loaded=[('card.csv', card, None, True)], needed=['Description', 'Amount'],
                          amount_col='Amount', debit_col=None, credit_col=None)


@given(parsers.re('an uploaded file ' + q('name') + ' with no Filename column'))
def _(ctx, name):
    d = pd.DataFrame([{'Description': 'ACME', 'Amount': -5.0}, {'Description': 'KLMN', 'Amount': 9.0}])
    ctx['combine'] = dict(loaded=[(name, d, None, False)], needed=['Description', 'Amount'],
                          amount_col='Amount', debit_col=None, credit_col=None)
    ctx['upload_name'] = name


@when('the files are combined')
def _(ctx):
    c = ctx['combine']
    ctx['combined'] = tp._combine_uploads(c['loaded'], c['needed'], c['amount_col'],
                                          c['debit_col'], c['credit_col'])


@then(parsers.re(r'the signed amounts are (?P<a>-?[\d.]+) and (?P<b>-?[\d.]+)'))
def _(ctx, a, b):
    assert ctx['combined']['_signed_amount'].tolist() == [float(a), float(b)]


@then(parsers.re(r'that charge is (?P<amount>-?[\d.]+)'))
def _(ctx, amount):
    assert ctx['combined']['Amount'].tolist() == [float(amount)]


@then(parsers.re('every row from it has Filename ' + q('name')))
def _(ctx, name):
    assert ctx['combined']['Filename'].tolist() == [name, name]


@given(parsers.re('a row whose amount is ' + q('amount')))
def _(ctx, amount):
    ctx['df'] = pd.DataFrame([_txn('KLMN DINER', amount), _txn('ACME PAPER', -10.0)])
    ctx['edits'] = {'ACME PAPER': ('Supplies', '')}


@then(parsers.re('its source is ' + q('source')))
def _(ctx, source):
    assert ctx['applied'].iloc[0]['Tag_Source'] == source


@then(parsers.re('the summary shows it only as a count on ' + q('label')))
def _(ctx, label):
    s = tp._build_summary(ctx['applied'], 'Amount')
    row = s[s['Tag'] == label].iloc[0]
    assert row['Count'] == 1 and pd.isna(row['Total'])
    assert s[s['Tag'].str.endswith('— TOTAL')]['Count'].sum() == 1   # only ACME PAPER is tagged


@given(parsers.re('a Master sheet whose first column has a "Reconciliation" line after the transactions'))
def _(ctx):
    master = pd.DataFrame({'Date': ['2026-01-02', '2026-01-03', None, 'Reconciliation', 'chk tab', 'Grand Total'],
                           'Amount': [-1.0, 2.0, None, None, 1.0, 1.0]})
    ctx['upload'] = _xlsx({'Master': master})
    ctx['upload'].name = 'master.xlsx'


@given(parsers.re('the uploaded workbook has a tab named like "Lookup" with a "Category" column'))
def _(ctx):
    ctx['upload'] = _xlsx({'Transactions': pd.DataFrame({'Description': ['ACME'], 'Amount': [-1.0]}),
                           'ACME Lookup': pd.DataFrame({'Vendor': ['ACME', 'KLMN'],
                                                        'Category': ['ACME Special Tag', 'Supplies']})})
    ctx['upload'].name = 'acme.xlsx'


@when('the file is loaded')
def _(ctx):
    xl = pd.ExcelFile(ctx['upload'])
    ctx['vocab'] = tp._load_lookup_tab_vocab(xl)
    if len(xl.sheet_names) == 1:
        ctx['upload'].seek(0)
        ctx['loaded_df'] = tp._load_upload_file(ctx['upload'])[0]


@then('only the rows above that line are kept')
def _(ctx):
    assert ctx['loaded_df']['Date'].tolist() == ['2026-01-02', '2026-01-03']


# ── 03 Rules and order ───────────────────────────────────────────────────────────

@given(parsers.re('vendor ' + q('vendor') + ' is in the client lookup as ' + q('tag')))
def _(ctx, vendor, tag):
    ctx['lookup'] = _lookup_df([(vendor, tag, '')])
    ctx['df'] = pd.DataFrame([_txn(vendor, -10.0)])


@given(parsers.re('a shared rule would tag ' + q('vendor') + ' as ' + q('tag')))
def _(vendor, tag, monkeypatch):
    monkeypatch.setattr(tp, '_AUTO_RULES', [(re.compile(re.escape(vendor), re.I), 'any', '', tag)]
                        + tp._AUTO_RULES)
    assert tp._get_auto_rule(vendor)['tag'] == tag


@when('the vendor table is built')
def _(ctx):
    ctx['tbl'] = tp._build_vendor_table(ctx['df'], 'Description', 'Amount', ctx['lookup'], {}, _wave_map())


@then(parsers.re(q('vendor') + ' is ' + q('tag') + ' with source ' + q('source')))
def _(ctx, vendor, tag, source):
    row = ctx['tbl'].set_index('Vendor').loc[vendor]
    assert row[tp._COL_CATEGORY] == tag and source in row['Source']


@given(parsers.re('vendor ' + q('vendor') + ' was suggested as ' + q('tag')))
def _(ctx, vendor, tag):
    ctx['vendor'] = vendor
    ctx['df'] = pd.DataFrame([_txn(vendor, -10.0)])
    ctx['pretag'] = {vendor: {'tag': tag, 'subcategory': '', 'confidence': 0.8, 'reason': 'x',
                              'source': '🤖 Claude'}}


@when(parsers.re('the preparer picks ' + q('tag')))
def _(ctx, tag):
    tbl = tp._build_vendor_table(ctx['df'], 'Description', 'Amount', _empty_lookup(), ctx['pretag'], _wave_map())
    edited = tbl.assign(**{tp._COL_CATEGORY: tag})
    merged = tp._merge_edits(tbl, edited, _wave_map())
    ctx['applied'] = _apply(ctx['df'], merged, {}, pretag=ctx['pretag'])


@then(parsers.re('the tag is ' + q('tag') + ' with source ' + q('source') + r' and confidence (?P<conf>[\d.]+)'))
def _(ctx, tag, source, conf):
    row = ctx['applied'].iloc[0]
    assert (row['Tag'], row['Tag_Source'], row['Confidence']) == (tag, source, float(conf))


@given(parsers.re('the vendor ' + q('vendor') + r' with direction (?P<direction>debit|credit)'))
def _(ctx, vendor, direction):
    ctx['rule_args'] = (vendor, direction)


@when('the shared rules are checked')
def _(ctx):
    ctx['rule'] = tp._get_auto_rule(*ctx['rule_args'])


@then(parsers.re('the tag is ' + q('tag')))
def _(ctx, tag):
    rule = ctx['rule']
    if tag == '(no rule)':
        assert rule is None
        return
    direction = ctx['rule_args'][1]
    assert (rule['tag'] or tp._wave_tag(rule['subcategory'], direction, _wave_map())) == tag


@then(parsers.re('the Wave category is ' + q('wave') + " and the rule's own tag is blank"))
def _(ctx, wave):
    assert ctx['rule'] == {'tag': '', 'subcategory': wave}


@then('an ATM credit gets no rule')
def _(ctx):
    assert tp._get_auto_rule(ctx['rule_args'][0], 'credit') is None


@given(parsers.re('the client has a rules file with the line ' + q('rule')))
def _(ctx, rule):
    with open(tp._rules_path(CLIENT), 'w', encoding='utf-8') as f:
        f.write(f'# a comment\n{rule}\n')
    ctx['rule_line'] = rule


@when('Claude is asked about vendors not in the lookup')
def _(ctx):
    ctx['prompt'] = _prompt(rules=tp._load_client_rules(CLIENT))
    ctx['prompt_no_file'] = _prompt(rules=tp._load_client_rules('klmn_no_rules'))


@then('the prompt lists that rule')
def _(ctx):
    assert f"- {ctx['rule_line']}" in ctx['prompt'] and 'a comment' not in ctx['prompt']


@then('tells Claude never to compute a split amount, but to use "Review with Client"')
def _(ctx):
    assert 'never compute' in ctx['prompt']
    assert 'use "Review with Client" instead' in ctx['prompt']


@then('with no rules file the prompt is unchanged')
def _(ctx):
    assert ctx['prompt_no_file'] == _prompt()


# ── 04 Lookup ────────────────────────────────────────────────────────────────────

@given('the client lookup has')
def _(ctx, datatable):
    header, *rows = datatable
    ctx['lookup'] = _lookup_df([(r[header.index('vendor_name')], r[header.index('tag')], '') for r in rows])


@when(parsers.re('the lookup is asked about ' + q('vendor')))
def _(ctx, vendor):
    ctx['answer'] = tp._lookup_matcher(ctx['lookup'])(vendor)


@then(parsers.re(r'the answer is (?P<answer>.+)'))
def _(ctx, answer):
    if answer.startswith('no match'):
        assert ctx['answer'] is None
    else:
        assert ctx['answer']['tag'] == answer.split(' (')[0]


@given(parsers.re('the lookup has ' + q('name') + ' as ' + q('tag')))
def _(ctx, name, tag):
    ctx['lookup'] = pd.concat([ctx['lookup'], _lookup_df([(name, tag, '')])], ignore_index=True)


@given(parsers.re('the lookup has ' + q('n1') + ' as ' + q('t1') + ' and ' + q('n2') + ' as ' + q('t2')))
def _(ctx, n1, t1, n2, t2):
    known = set(ctx['lookup']['vendor_name'])
    new = [(n, t, '') for n, t in ((n1, t1), (n2, t2)) if n not in known]
    ctx['lookup'] = pd.concat([ctx['lookup'], _lookup_df(new)], ignore_index=True)


@when(parsers.re('the vendor ' + q('vendor') + ' is tagged'))
def _(ctx, vendor, monkeypatch):
    lk = ctx['lookup']
    ctx['match'] = tp._lookup_matcher(lk)(vendor)
    ctx['stats'] = tp._with_similar_history({}, [vendor], lk)
    _fake_claude(monkeypatch, _answer_all(confidence=0.95))
    claude = tp._run_claude_on_vendors([vendor], 'key', 'prompt', _Prog(), ctx['stats'])
    df = pd.DataFrame([_txn(vendor, -10.0)])
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', lk, wave_map=_wave_map())
    ctx['applied'] = _apply(df, tbl, claude, lk)
    ctx['vendor'] = vendor


@then('the lookup gives no tag')
def _(ctx):
    assert ctx['match'] is None


@then(parsers.re('Claude gets "(?P<name>[^"=]+) = (?P<tag>[^"]+)" as similar history'))
def _(ctx, name, tag):
    hints = ctx['stats'][ctx['vendor']]['similar_history']
    assert {'name': name, 'tag': tag} in [{'name': h['name'], 'tag': h['tag']} for h in hints]


@then(parsers.re("Claude's answer is flagged for the preparer with the note " + q('note')))
def _(ctx, note):
    row = ctx['applied'].iloc[0]
    assert row['Tag_Source'] == 'flagged' and row['Reason'].startswith(note)


def _seed_lookup(ctx, extra=()):
    rows = [(r['vendor_name'], r['tag'], '') for _, r in ctx['lookup'].iterrows()] + list(extra)
    _lookup_df(rows).to_csv(tp._lookup_path(CLIENT), index=False)


@when(parsers.re('a run finishes without "Save tags to lookup"'))
def _(ctx, monkeypatch):
    _seed_lookup(ctx)
    before = open(tp._lookup_path(CLIENT), 'rb').read()
    df = pd.DataFrame([_txn('ACME NEW', -10.0, 'Supplies', '', 'claude'),
                       _txn('KLMN NEW', -20.0, 'Meals', '', 'preparer'), _txn(**_WAVE_ROW)])
    _show_step5(monkeypatch, df)
    ctx['lookup_changed'] = open(tp._lookup_path(CLIENT), 'rb').read() != before


@then('the lookup file is unchanged')
def _(ctx):
    assert not ctx['lookup_changed']


@given(parsers.re('a run where Claude tagged ' + q('vendor') + ' above the confidence threshold'))
def _(ctx, vendor):
    _seed_lookup(ctx, [(vendor, 'Rents', '')])          # an older row for the same vendor
    ctx['run_df'] = pd.DataFrame([_txn(vendor, -10.0, 'Supplies', '', 'claude', confidence=0.9),
                                  _txn(vendor, -12.0, 'Supplies', '', 'claude', confidence=0.9),
                                  _txn(**_WAVE_ROW)])


@given('the preparer did not touch it')
def _():
    pass


@given(parsers.re(q('vendor') + ' was tagged ' + q('tag') + ' and found no other side'))
def _(ctx, vendor, tag):
    ctx['run_df'] = pd.DataFrame([_txn(vendor, -300.0, tag, '', 'preparer', desc='ONLINE TRANSFER TO KLMN'),
                                  _txn(**_WAVE_ROW)])


@when('the preparer clicks "Save tags to lookup"')
@when('the preparer saves tags to the lookup')
def _(ctx, monkeypatch):
    _show_step5(monkeypatch, ctx['run_df'], clicks={'Save tags to lookup'})
    ctx['saved'] = pd.read_csv(tp._lookup_path(CLIENT))


@then(parsers.re(q('vendor') + ' is saved with source ' + q('source')))
def _(ctx, vendor, source):
    assert ctx['saved'].set_index('vendor_name').loc[vendor, 'source'] == source


@then('each vendor has one row, the newest one winning')
def _(ctx):
    saved = ctx['saved']
    assert saved['vendor_name'].is_unique
    assert saved.set_index('vendor_name').loc['ACME FUEL', 'tag'] == 'Supplies'


@then(parsers.re('the lookup row says ' + q('tag') + ', not ' + q('other')))
def _(ctx, tag, other):
    assert ctx['saved'].set_index('vendor_name').loc['Online Transfer', 'tag'] == tag != other


# ── 05 Claude ────────────────────────────────────────────────────────────────────

@given(parsers.re(r'(?P<n>\d+) vendors with no tag after the lookup, the rules and the preparer'))
def _(ctx, n):
    tbl = pd.DataFrame({'Vendor': [f'ACME {i}' for i in range(int(n))] + ['KLMN A', 'KLMN B'],
                        tp._COL_CATEGORY: [''] * int(n) + ['Supplies', 'Meals'],
                        tp._COL_SUBCATEGORY: ''})
    ctx['tbl'] = tbl


@when('Claude is run')
def _(ctx, monkeypatch):
    sent = _fake_claude(monkeypatch, _answer_all())
    names = tp._pending_vendors(ctx['tbl'])['Vendor'].tolist()
    tp._run_claude_on_vendors(names, 'key', 'prompt', _Prog())
    ctx['sent'] = sent


@then(parsers.re(r'(?P<calls>\d+) calls are made with (?P<sizes>.+) vendors'))
def _(ctx, calls, sizes):
    want = [int(s) for s in re.split(r',\s*|\s+and\s+', sizes)]
    assert [len(b) for b in ctx['sent']] == want and len(want) == int(calls)
    assert not any(v['vendor'].startswith('KLMN') for b in ctx['sent'] for v in b)


@when('a vendor is sent to Claude')
def _(ctx, monkeypatch):
    calls = []

    class _Client:
        def __init__(self, api_key):
            self.messages = self

        def create(self, **kw):
            calls.append(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(text='[]')])
    monkeypatch.setattr(tp, 'anthropic', types.SimpleNamespace(Anthropic=_Client))
    df = pd.DataFrame([_txn('ACME FUEL', -40.0, date='2026-01-05', desc='CARD 4455 ACME FUEL ACCT 123456789'),
                       _txn('ACME FUEL', -60.0, date='2026-02-05', desc='CARD 4455 ACME FUEL ACCT 123456789'),
                       _txn('KLMN DEPOSIT', 900.0, date='2026-01-07', desc='KLMN DEPOSIT ACCT 123456789')])
    lk = _lookup_df([('Acme Fuell', 'Fuel', '')])
    names = ['ACME FUEL', 'KLMN DEPOSIT']
    stats = tp._with_similar_history(tp._vendor_stats(df, 'Amount', 'Date'), names, lk)
    tp._run_claude_on_vendors(names, 'key', 'prompt', _Prog(), stats)
    content = calls[0]['messages'][0]['content']
    ctx['payload_text'] = content
    ctx['items'] = {i['vendor']: i for i in json.loads(content.split('\n', 1)[1])}


@then('its item holds only: id, vendor, amount_total, txn_count, amount_sample, date_span, and similar_history when there is one')
def _(ctx):
    base = {'id', 'vendor', 'amount_total', 'txn_count', 'amount_sample', 'date_span'}
    assert set(ctx['items']['ACME FUEL']) == base | {'similar_history'}
    assert set(ctx['items']['KLMN DEPOSIT']) == base
    assert '123456789' not in ctx['payload_text'] and 'CARD 4455' not in ctx['payload_text']


@then('amount_total is negative for money out and positive for money in')
def _(ctx):
    assert ctx['items']['ACME FUEL']['amount_total'] == -100.0
    assert ctx['items']['KLMN DEPOSIT']['amount_total'] == 900.0


@given(parsers.re('the client is an ' + q('entity') + ' whose primary activity is ' + q('activity')))
def _(ctx, entity, activity):
    ctx['client'] = (entity, activity)


@when('the prompt is built')
def _(ctx):
    ctx['specific'] = ['ACME Lookup Tab Tag', 'Supplies']
    ctx['prompt'] = _prompt(*ctx['client'], specific=ctx['specific'])


@then('it names the entity type and the activity')
def _(ctx):
    entity, activity = ctx['client']
    assert f'Entity type: {entity}. Primary activity: {activity}.' in ctx['prompt']


@then("it lists every tag, the file's Lookup-tab tags first")
def _(ctx):
    generic = tp._load_generic_tags()
    assert _tag_lines(ctx['prompt']) == ctx['specific'] + [t for t in generic if t not in ctx['specific']]


@then('Claude must pick "tag" from that list only')
def _(ctx):
    assert 'Select only from the tag list above for "tag".' in ctx['prompt']


@given(parsers.re(r'the confidence threshold is (?P<pct>\d+)%'))
def _(ctx, pct):
    cfg = tp._build_tagger_config('', CLIENT, 'S-Corp', 'liquor store', '', int(pct), [], 'review_first', {})
    ctx['threshold'] = cfg['threshold']


@when(parsers.re(r'Claude answers with confidence (?P<conf>[\d.]+)(?P<extra>.*)'))
def _(ctx, conf, extra, monkeypatch):
    vendor = 'ACME FUEL'
    sub = 'ACME Brand New Wave' if 'Wave category not in the mapping' in extra else ''
    stats = {}
    if 'lookup conflict' in extra:
        stats = {vendor: {'lookup_conflict': [{'name': 'Acme', 'tag': 'Supplies', 'subcategory': ''},
                                              {'name': 'Acme Fuels', 'tag': 'Fuel', 'subcategory': ''}]}}
    _fake_claude(monkeypatch, _answer_all(subcategory=sub, confidence=float(conf)))
    claude = tp._run_claude_on_vendors([vendor], 'key', 'prompt', _Prog(), stats)
    df = pd.DataFrame([_txn(vendor, -10.0)])
    tbl = pd.DataFrame([{'Vendor': vendor, tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''}])
    ctx['applied'] = _apply(df, tbl, claude, threshold=ctx['threshold'])


@then(parsers.re("the row's source is " + q('source')))
def _(ctx, source):
    assert ctx['applied'].iloc[0]['Tag_Source'] == source


@when('a Claude call fails')
def _(ctx, monkeypatch):
    def boom(batch):
        raise RuntimeError('boom')
    _fake_claude(monkeypatch, boom)
    ctx['results'] = tp._run_claude_on_vendors(['ACME A', 'ACME B', 'KLMN C'], 'key', 'prompt', _Prog())


@then(parsers.re(r'every vendor in that batch is "Review with Client" with confidence 0'))
def _(ctx):
    assert len(ctx['results']) == 3
    assert all(r['tag'] == 'Review with Client' and r['confidence'] == 0 for r in ctx['results'].values())


@then(parsers.re('the reason starts with ' + q('prefix')))
def _(ctx, prefix):
    assert all(r['reason'].startswith(prefix) for r in ctx['results'].values())


@when(parsers.re("Claude's answer has no item for " + q('vendor')))
def _(ctx, vendor, monkeypatch):
    _fake_claude(monkeypatch, lambda batch: [{'id': 0, 'tag': 'Meals', 'subcategory': '',
                                              'confidence': 0.9, 'reason': 'x'}])
    names = ['KLMN DINER', vendor]
    claude = tp._run_claude_on_vendors(names, 'key', 'prompt', _Prog())
    df = pd.DataFrame([_txn(v, -10.0) for v in names])
    tbl = pd.DataFrame({'Vendor': names, tp._COL_CATEGORY: '', tp._COL_SUBCATEGORY: ''})
    ctx['applied'] = _apply(df, tbl, claude)


@then(parsers.re(q('vendor') + r' is "Review with Client", confidence 0, source ' + q('source')))
def _(ctx, vendor, source):
    row = ctx['applied'].set_index('Vendor').loc[vendor]
    assert (row['Tag'], row['Confidence'], row['Tag_Source']) == ('Review with Client', 0.0, source)


@when('the prompt is built with a Wave category list')
def _(ctx):
    ctx['prompt'] = _prompt(subcategory_vocab=['Office Supplies', 'Bank Service Charges'])


@then('it asks for a Wave category in "subcategory"')
def _(ctx):
    assert '"subcategory" = the Wave category' in ctx['prompt']
    assert 'Wave categories (the bookkeeping categories this client posts to)' in ctx['prompt']


@given('pre-tag mode')
def _(ctx):
    ctx['cfg'] = tp._build_tagger_config('key', CLIENT, 'S-Corp', 'liquor store', '', 75,
                                         tp._load_generic_tags(), 'pretag', {})


@when('the file is uploaded')
def _(ctx, monkeypatch):
    _lookup_df([('Acme', 'Supplies', '')]).to_csv(tp._lookup_path(CLIENT), index=False)
    csv = pd.DataFrame([{'Date': '2026-01-05', 'Description': 'ACME STORE 22', 'Amount': -10.0},
                        {'Date': '2026-01-06', 'Description': 'KLMN DINER', 'Amount': -20.0},
                        {'Date': '2026-01-07', 'Description': 'ATM WITHDRAWAL 1 MAIN ST', 'Amount': -40.0}]
                       ).to_csv(index=False).encode()
    upload = io.BytesIO(csv)
    upload.name = 'chk.csv'
    fake = FakeSt(clicks={'Next →'}, answers={'Amount column': 'Amount', 'tagger_upload': None})
    fake.file_uploader = lambda label, **k: [upload]
    fake.session_state['tagger_config'] = ctx['cfg']
    monkeypatch.setattr(tp, 'st', fake)
    ctx['sent'] = _fake_claude(monkeypatch, _answer_all())
    tp._render_step2()


@then('Claude is asked about every vendor the lookup does not know')
def _(ctx):
    assert [v['vendor'] for b in ctx['sent'] for v in b] == ['KLMN DINER', 'ATM Withdrawal']


# ── 06 / 10 Contras ──────────────────────────────────────────────────────────────

@given('these contra rows')
def _(ctx, datatable):
    header, *rows = datatable
    recs = [dict(zip(header, r)) for r in rows]
    ctx['contra'] = {'rows': pd.DataFrame([_contra(float(r['amount']), r['file'], r['date'],
                                                   r.get('description', 'ONLINE TRANSFER')) for r in recs])}


@given(parsers.re(r'a (?P<a>-[\d.]+) and a (?P<b>[\d.]+) contra on the same day in the same file'))
def _(ctx, a, b):
    ctx['contra'] = {'rows': pd.DataFrame([_contra(float(a), 'chk'), _contra(float(b), 'chk')])}


@given('a contra with no other side')
def _(ctx):
    ctx['contra'] = {'rows': pd.DataFrame([_contra(-300.0, 'chk'), _txn('ACME', -300.0, 'Supplies', '', 'lookup', file='sav')])}


@given(parsers.re(r'a (?P<a>-[\d.]+) and a (?P<b>[\d.]+) row in the same file, both with ref ' + q('ref')))
def _(ctx, a, b, ref):
    ctx['contra'] = {'rows': pd.DataFrame([_contra(float(a), 'chk', desc=f'EB to Savings Ref# {ref}'),
                                           _contra(float(b), 'chk', desc=f'EB From Checking Ref# {ref}')])}


@given(parsers.re(r'a (?P<a>-[\d.]+) row and a (?P<b>[\d.]+) row, both with ref ' + q('ref')))
def _(ctx, a, b, ref):
    ctx['contra'] = {'rows': pd.DataFrame([_contra(float(a), 'chk', desc=f'EB to Savings Ref# {ref}'),
                                           _contra(float(b), 'sav', desc=f'EB From Checking Ref# {ref}')])}


@given(parsers.re('the description ' + q('desc')))
def _(ctx, desc):
    ctx['desc'] = desc


_TODAYS_RULE_CASES = {   # partner of a -75.00 checking row dated 2026-01-02 → paired?
    '3 days later, other file':  (_contra(75.0, 'sav', '2026-01-05'), True),
    '4 days later, other file':  (_contra(75.0, 'sav', '2026-01-06'), False),
    'same file':                 (_contra(75.0, 'chk', '2026-01-03'), False),
    'same sign':                 (_contra(-75.0, 'sav', '2026-01-03'), False),
    'other amount':              (_contra(70.0, 'sav', '2026-01-03'), False),
}


@given('a contra row with no ref no in its description')
def _(ctx):
    base = _contra(-75.0, 'chk', '2026-01-02', 'ONLINE TRANSFER TO SAVINGS')
    ctx['contra'] = {name: pd.DataFrame([base, other]) for name, (other, _) in _TODAYS_RULE_CASES.items()}


@given('a contra row from a credit card statement')
def _(ctx):
    card = pd.DataFrame([{'Date': '2026-01-04', 'Description': 'PAYMENT - THANK YOU', 'Amount': -500.0}])
    card_far = card.assign(Date='2026-01-20')
    chk = pd.DataFrame([{'Date': '2026-01-02', 'Description': 'ONLINE PAYMENT TO ACME CARD Ref# 000000 0001028',
                         'Amount': -500.0, 'Filename': 'chk.pdf'}])
    ctx['contra'] = {}
    for name, c in (('near', card), ('far', card_far)):
        d = tp._combine_uploads([('chk.xlsx', chk, None, False), ('card.xlsx', c, None, True)],
                                ['Date', 'Description', 'Amount'], 'Amount', None, None)
        ctx['contra'][name] = d.assign(Tag=tp._CONTRA_TAG, Tag_Source='lookup', Reason='', Subcategory='',
                                       Vendor=d['Description'], Confidence=1.0)


@when('contras are paired')
def _(ctx):
    if 'desc' in ctx:
        ctx['ref'] = tp._transfer_ref(ctx['desc'])
    ctx['paired'] = {name: _pair(d) for name, d in ctx.get('contra', {}).items()}


def _pairs(ctx, name='rows'):
    return ctx['paired'][name]


@then(parsers.re(r'the two (?P<amount>[\d.]+) rows share pair number (?P<n>\d+)'))
def _(ctx, amount, n):
    out = _pairs(ctx)
    assert out.loc[out['Amount'].abs() == float(amount), 'Contra Pair'].tolist() == [int(n), int(n)]


@then(parsers.re(r'the two (?P<amount>[\d.]+) rows are ' + q('tag') + ' with reason ' + q('reason')))
def _(ctx, amount, tag, reason):
    rows = _pairs(ctx)[_pairs(ctx)['Amount'].abs() == float(amount)]
    assert len(rows) == 2 and (rows['Tag'] == tag).all() and (rows['Reason'] == reason).all()
    assert (rows['Tag_Source'] == 'rwc').all() and rows['Contra Pair'].isna().all()


@then('neither is paired')
@then('they are not paired')
@then('they are not paired by ref no')
def _(ctx):
    assert _pairs(ctx)['Contra Pair'].isna().all()


@then('it goes to Review with Client and nothing else is tried')
def _(ctx):
    before, out = ctx['contra']['rows'], _pairs(ctx)
    assert (out.loc[0, 'Tag'], out.loc[0, 'Tag_Source'], out.loc[0, 'Reason']) == \
        ('Review with Client', 'rwc', 'Contra with no matching other side')
    assert out['Contra Pair'].isna().all()
    same = [c for c in before.columns if c not in ('Tag', 'Tag_Source', 'Reason')]
    assert out[same].equals(before[same]) and out.loc[1, 'Tag'] == 'Supplies'


@then(parsers.re('the ref no used is ' + q('ref')))
def _(ctx, ref):
    assert ctx['ref'] == ('' if ref.startswith('(none') else ref)


@then('the two rows share a pair number')
def _(ctx):
    pairs = _pairs(ctx)['Contra Pair']
    assert pairs.notna().all() and pairs.nunique() == 1


@then("it uses today's rule: same amount, opposite sign, another file, within 3 days")
def _(ctx):
    got = {name: _pairs(ctx, name)['Contra Pair'].notna().all() for name in _TODAYS_RULE_CASES}
    assert got == {name: want for name, (_, want) in _TODAYS_RULE_CASES.items()}


@then('it pairs by today\'s rule only')
def _(ctx):
    assert tp._transfer_ref('PAYMENT - THANK YOU') == ''
    assert _pairs(ctx, 'near')['Contra Pair'].tolist() == [1, 1]
    assert _pairs(ctx, 'far')['Contra Pair'].isna().all()


@when('the run finishes')
def _(ctx):
    df = pd.DataFrame([_contra(-500.0, 'chk', '2026-01-02', 'EB to Savings Ref# 000000 0001028'),
                       _contra(500.0, 'sav', '2026-01-03', 'KLMN DEPOSIT'),
                       _contra(500.0, 'sav', '2026-01-04', 'EB From Checking Ref# 000000 0001028'),
                       _contra(-500.0, 'chk', '2026-01-05', 'ONLINE TRANSFER')])
    ctx['input'] = df
    ctx['before'] = _pair(df, desc_col=None)     # pairing before ref nos were read
    ctx['after'] = _pair(df)


@then('Vendor and Description are the same as before this change')
def _(ctx):
    for col in ('Vendor', 'Description'):
        assert ctx['after'][col].equals(ctx['input'][col]) and ctx['before'][col].equals(ctx['input'][col])


@then('the only difference is which rows share a Contra Pair number')
def _(ctx):
    before, after = ctx['before'], ctx['after']
    rest = [c for c in after.columns if c != 'Contra Pair']
    assert after[rest].equals(before[rest])
    assert before['Contra Pair'].tolist() == [1, 1, 2, 2]
    assert after['Contra Pair'].tolist() == [1, 2, 1, 2]


# ── 07 Output ────────────────────────────────────────────────────────────────────

def _output_df():
    return pd.DataFrame([_txn('ACME PAPER', -20.0, 'Supplies', 'Office Supplies', 'lookup', '12/05/2025'),
                         _txn('KLMN HOLD', -15.0, 'Review with Client', '', 'rwc', '12/09/2025'),
                         _txn('ACME GYM', -30.0, 'Personal - Not Deductible', '', 'rule', '01/04/2026'),
                         _txn('KLMN SALES', 500.0, 'Gross Receipts or Sales', 'Sales', 'lookup', '01/06/2026'),
                         _contra(-100.0, 'chk', '01/10/2026'),
                         _contra(100.0, 'sav', '01/11/2026')])


@when('the output is written')
def _(ctx):
    df = ctx.get('df', _output_df())
    ctx['df'] = df
    ctx['book'] = pd.read_excel(tp._write_output_excel(df, 'Description', 'Amount', 'Date',
                                                       {'client_id': CLIENT}), sheet_name=None)


@then('it has sheets "Tagged", "Personal", "Review with Client" and, when there are tags, "Summary"')
def _(ctx):
    assert list(ctx['book']) == ['Tagged', 'Personal', 'Review with Client', 'Summary']
    untagged = ctx['df'].assign(Tag='')
    book = pd.read_excel(tp._write_output_excel(untagged, 'Description', 'Amount', 'Date',
                                                {'client_id': CLIENT}), sheet_name=None)
    assert list(book) == ['Tagged', 'Personal', 'Review with Client']


@then('"Review with Client" rows are not on "Tagged"')
def _(ctx):
    assert ctx['book']['Review with Client']['Vendor'].tolist() == ['KLMN HOLD']
    assert 'KLMN HOLD' not in ctx['book']['Tagged']['Vendor'].tolist()


@then('"Personal - ..." rows are on both "Personal" and "Tagged"')
def _(ctx):
    assert ctx['book']['Personal']['Vendor'].tolist() == ['ACME GYM']
    assert 'ACME GYM' in ctx['book']['Tagged']['Vendor'].tolist()


@then('"Wave Category" sits just left of "Tax Tag" and Filename is the last column')
def _(ctx):
    cols = list(ctx['book']['Tagged'].columns)
    assert cols.index('Wave Category') + 1 == cols.index('Tax Tag') and cols[-1] == 'Filename'


@given(parsers.re(r'rows dated Dec 2025 to Feb 2026'))
def _(ctx):
    ctx['df'] = pd.DataFrame([_txn('ACME PAPER', -20.0, 'Supplies', 'Office Supplies', 'lookup', '12/05/2025'),
                              _txn('ACME SHOP', -10.0, 'Supplies', 'Shop Supplies', 'lookup', '01/10/2026'),
                              _txn('KLMN DINER', -15.0, 'Meals', '', 'lookup', '02/03/2026')])


@when('the summary is built')
def _(ctx):
    ctx['summary'] = tp._build_summary(ctx.get('df', _output_df()), 'Amount', 'Date')


def _section_of(s, tag):
    return s.loc[s['Tag'] == tag, 'Section'].tolist()


@then('"Contra / Transfer" rows are in "Contra / Transfers"')
def _(ctx):
    assert _section_of(ctx['summary'], tp._CONTRA_TAG) == ['Contra / Transfers']


@then('tags starting "Personal -" are in "Personal"')
def _(ctx):
    assert _section_of(ctx['summary'], 'Personal - Not Deductible') == ['Personal']


@then('other money in is in "Income" and other money out in "Expenses"')
def _(ctx):
    s = ctx['summary']
    assert _section_of(s, 'Gross Receipts or Sales') == ['Income']
    assert _section_of(s, 'Supplies') == ['Expenses'] and _section_of(s, 'Review with Client') == ['Expenses']


@then('each section has a TOTAL row')
def _(ctx):
    tags = ctx['summary']['Tag'].tolist()
    for block in ('INCOME', 'EXPENSES', 'PERSONAL', 'CONTRA / TRANSFERS'):
        assert f'{block} — TOTAL' in tags


@then('a "NET (Income − Expenses)" row adds the signed Income and Expenses amounts')
def _(ctx):
    totals = dict(zip(ctx['summary']['Tag'], ctx['summary']['Total']))
    assert totals['NET (Income − Expenses)'] == totals['INCOME — TOTAL'] + totals['EXPENSES — TOTAL'] == 465.0


@then('there is one row per tag and subcategory, plus a SUBTOTAL when a tag has 2+ subcategories')
def _(ctx):
    s = ctx['summary']
    rows = list(zip(s['Tag'], s['Subcategory']))
    assert rows[:4] == [('Meals', '(unspecified)'), ('Supplies', 'Office Supplies'),
                        ('Supplies', 'Shop Supplies'), ('Supplies — SUBTOTAL', '')]


@then('the month columns are "Dec 2025", "Jan 2026", "Feb 2026" in date order, then Total')
def _(ctx):
    cols = list(ctx['summary'].columns)
    assert cols[cols.index('Count') + 1:] == ['Dec 2025', 'Jan 2026', 'Feb 2026', 'Total']


# ── 08 Tag list ──────────────────────────────────────────────────────────────────

@then('the tag list holds "Review with Client", "Contra / Transfer" and "Personal - Not Deductible"')
def _():
    tags = tp._load_generic_tags()
    assert {'Review with Client', tp._CONTRA_TAG, 'Personal - Not Deductible'} <= set(tags)


@then('any tag starting "Personal -" is treated as personal in the output')
def _():
    df = pd.DataFrame([_txn('ACME TOYS', -9.0, 'Personal - ACME Other', '', 'preparer'),
                       _txn('ACME PAPER', -5.0, 'Supplies', '', 'lookup')])
    book = pd.read_excel(tp._write_output_excel(df, 'Description', 'Amount', 'Date', {'client_id': CLIENT}),
                         sheet_name=None)
    assert book['Personal']['Vendor'].tolist() == ['ACME TOYS']
    assert _section_of(tp._build_summary(df, 'Amount'), 'Personal - ACME Other') == ['Personal']


@given(parsers.re('the entity type ' + q('entity')))
def _(ctx, entity):
    ctx['entity'] = entity


@when('the tag list is loaded')
def _(ctx):
    cfg = tp._build_tagger_config('', CLIENT, ctx['entity'], 'p', '', 75, tp._load_generic_tags(), 'review_first', {})
    ctx['tags'] = _tag_lines(_prompt(ctx['entity'], specific=cfg['specific_tags']))


@then(parsers.re('it is the same list as for ' + q('entity')))
def _(ctx, entity):
    assert ctx['tags'] == _tag_lines(_prompt(entity))


@then('its Category values are added to the tag dropdown and listed first to Claude')
def _(ctx):
    cats, _, warn = ctx['vocab']
    assert cats == ['ACME Special Tag', 'Supplies'] and warn is None
    assert 'ACME Special Tag' in tp._get_category_options(tp._load_generic_tags(), cats)
    assert _tag_lines(_prompt(specific=cats))[:2] == cats


@then('a Lookup tab without a Category column gives a warning, not an error')
def _():
    xl = pd.ExcelFile(_xlsx({'Lookup': pd.DataFrame({'Vendor': ['ACME'], 'Thing': ['x']})}))
    cats, subs, warn = tp._load_lookup_tab_vocab(xl)
    assert (cats, subs) == ([], []) and 'no Category column' in warn


# ── 09 Wave (parked) ─────────────────────────────────────────────────────────────

@given(parsers.re('the Wave category ' + q('wave') + r' on a (?P<direction>debit|credit) row'))
def _(ctx, wave, direction):
    amount = -10.0 if direction == 'debit' else 10.0
    # a negative row keeps the column signed, so a positive amount reads as money in
    ctx['df'] = pd.DataFrame([_txn('ACME V', amount), _txn('KLMN FILLER', -1.0)])
    ctx['edits'] = {'ACME V': ('', wave)}


@when('tags are applied')
def _(ctx):
    df = ctx['df']
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', _empty_lookup(), wave_map=_wave_map())
    edited = pd.DataFrame([{'Vendor': v, tp._COL_CATEGORY: c, tp._COL_SUBCATEGORY: s}
                           for v, (c, s) in ctx['edits'].items()])
    tbl = tp._merge_edits(tbl, edited, _wave_map())
    ctx['applied'] = _apply(df, tbl, {})


@then(parsers.re('the tax tag is ' + q('tag')))
def _(ctx, tag):
    assert ctx['applied'].iloc[0]['Tag'] == tag


@given(parsers.re('a lookup row tagged ' + q('tag') + ' with no Wave category'))
def _(ctx, tag):
    _lookup_df([('ACME X', tag, '')]).to_csv(tp._lookup_path(CLIENT), index=False)


@when('the lookup is loaded')
def _(ctx):
    lk = tp._load_lookup_with_wave(CLIENT)
    ctx['lookup_wave'] = lk.loc[0, 'subcategory']
    df = pd.DataFrame([_txn('ACME X', -10.0)])
    tbl = tp._build_vendor_table(df, 'Description', 'Amount', lk, wave_map=_wave_map())
    ctx['applied'] = _apply(df, tbl, {}, lk)


@then(parsers.re('its Wave category is ' + q('wave') + r' \(.+\)'))
def _(ctx, wave):
    assert ctx['lookup_wave'] == wave


@then(parsers.re(r'it is flagged with the choices listed \((?P<n>\d+) Wave categories\)'))
def _(ctx, n):
    row = ctx['applied'].iloc[0]
    assert ctx['lookup_wave'] == '' and row['Tag_Source'] == 'flagged'
    assert len(row['Reason'].split('pick one: ')[1].split(' / ')) == int(n)


@then('it stays blank and is not flagged')
def _(ctx):
    assert ctx['lookup_wave'] == '' and ctx['applied'].iloc[0]['Tag_Source'] != 'flagged'


@given(parsers.re('the output uses a Wave category the mapping does not know, tagged ' + q('tag')))
def _(ctx, tag):
    ctx['run_df'] = pd.DataFrame([_txn('ACME A', -10.0, tag, 'ACME Brand New Wave', 'preparer'),
                                  _txn('ACME B', -11.0, tag, 'ACME Brand New Wave', 'preparer'),
                                  _txn('KLMN C', -12.0, 'Meals', 'ACME Brand New Wave', 'preparer')])
    ctx['new_tag'] = tag


@when('Step 5 is shown')
def _(ctx, monkeypatch):
    _show_step5(monkeypatch, ctx['run_df'])


@then(parsers.re("it is added to the client's Wave mapping with direction " + q('direction')
                 + ' and its most common tag'))
def _(ctx, direction):
    saved = pd.read_csv(tp._wave_mapping_path(CLIENT))
    assert saved.to_dict('records') == [{'wave_category': 'ACME Brand New Wave', 'direction': direction,
                                         'tax_category': ctx['new_tag']}]
