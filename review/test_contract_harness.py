#!/usr/bin/env python3
"""
The harness Contract (features/harness/*.feature) run as tests with pytest-bdd.

Each step drives the real harness.main(). extract.extract_local is a fake that returns what the
scenario says (no Ollama, no PDF read). All names are invented (ACME, KLMN).

Usage (WSL, from review/):
  .venv/bin/python -m pytest test_contract_harness.py
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

import extract
import harness

scenarios('features/harness')

# Invented truth values per form type; a fake run returns these unless a scenario says otherwise.
_TRUTH = {
    "W-2": {"__form_type__": "W-2", "box_1_wages": "75000.00", "box_2_federal_withheld": "12000.00"},
    "1099-INT": {"__form_type__": "1099-INT", "box_1_interest_income": "1200.00"},
}


def _list(s):
    return [x.strip() for x in s.split(',') if x.strip()]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return {'docs': [], 'truths': [], 'model': 'acme-text:1b', 'field_runs': {}, 'seconds': None,
            'unread': set(), 'missing': set(), 'no_text': set(), 'locked': set(), 'raises': {},
            'tmp': tmp_path}


# ── Given ────────────────────────────────────────────────────────────────────────

@given(parsers.parse('the documents "{names}"'))
def documents(ctx, names):
    ctx['docs'] = _list(names)


@given(parsers.parse('the truth files for "{forms}"'))
def truth_files(ctx, forms):
    for form in _list(forms):
        path = ctx['tmp'] / f"truth_{form}.json"
        path.write_text(json.dumps(_TRUTH[form]), encoding='utf-8')
        ctx['truths'].append(str(path))


@given('every run returns the truth values')
@given('every run returns the same values')
def same_values(ctx):
    pass


@given(parsers.parse('the model "{model}"'))
def model(ctx, model):
    ctx['model'] = model


@given(parsers.parse('{field} comes back {a}, {b}, {c} on the 3 runs'))
def field_varies(ctx, field, a, b, c):
    ctx['field_runs'][field] = [json.loads(v) for v in (a, b, c)]


@given(parsers.parse('the 3 runs take {a:d}, {b:d} and {c:d} seconds'))
def run_seconds(ctx, a, b, c):
    ctx['seconds'] = [a, b, c]


@given(parsers.parse('{doc} has a page with no text layer'))
def no_text_layer(ctx, doc):
    ctx['unread'].add(doc)


@given(parsers.parse('{doc} has a required field missing'))
def required_missing(ctx, doc):
    ctx['missing'].add(doc)


@given(parsers.parse('{doc} has no text layer on any page'))
def no_text_anywhere(ctx, doc):
    ctx['no_text'].add(doc)


@given(parsers.parse('{doc} will not open'))
def will_not_open(ctx, doc):
    ctx['locked'].add(doc)


@given(parsers.parse('run {n:d} of {doc} raises ExtractionFailed'))
def run_of_doc_raises(ctx, n, doc):
    ctx['raises'][(doc, n)] = True


@given(parsers.parse('run {n:d} raises ExtractionFailed'))
def run_raises(ctx, n):
    ctx['raises'][(ctx['docs'][0], n)] = True


# ── When ─────────────────────────────────────────────────────────────────────────

@when(parsers.parse('the harness runs {runs:d} times per document'))
def run(ctx, runs, monkeypatch, capsys):
    docs_dir = ctx['tmp'] / 'docs'
    docs_dir.mkdir()
    for name in ctx['docs']:
        (docs_dir / name).write_bytes(b'')
    calls = {}

    def fake_extract_local(pdf_path, ollama_url=None, model=None, form_hint=None):
        name = Path(pdf_path).name
        calls[name] = calls.get(name, 0) + 1
        i = calls[name]
        if name in ctx['locked']:
            raise extract.UnreadableDocument('acme file will not open')
        if ctx['raises'].get((name, i)):
            raise extract.ExtractionFailed('acme reply was not JSON')
        form = form_hint or 'UNKNOWN'
        fields = {k: v for k, v in _TRUTH.get(form, {"box_1": "10.00"}).items() if k != '__form_type__'}
        for field, values in ctx['field_runs'].items():
            fields[field] = values[i - 1]
        seconds = ctx['seconds'][i - 1] if ctx['seconds'] else 1
        routes = ['text', 'image'] if name in ctx['unread'] else ['text']
        if name in ctx['no_text']:
            routes = ['image', 'image']
        unread = [{"source_file": name, "page": n, "reason": "no text layer"}
                  for n, r in enumerate(routes, 1) if r == 'image']
        missing = ['box_1_wages'] if name in ctx['missing'] or name in ctx['no_text'] else []
        return SimpleNamespace(form_type=form, fields=fields, extraction_time_ms=seconds * 1000,
                               unread_pages=unread, page_routes=routes, missing_required=missing)

    monkeypatch.setattr(extract, 'extract_local', fake_extract_local)
    argv = ['--docs', str(docs_dir), '--runs', str(runs), '--model', ctx['model']]
    if ctx['truths']:
        argv += ['--truth', ','.join(ctx['truths'])]
    with pytest.raises(SystemExit) as exit_info:
        harness.main(argv)
    ctx['exit'] = exit_info.value.code
    ctx['console'] = capsys.readouterr().out
    reports = list((ctx['tmp'] / 'diag_output').glob('*'))
    ctx['report_files'] = reports
    ctx['report'] = reports[0].read_text(encoding='utf-8') if len(reports) == 1 else ''


# ── Then ─────────────────────────────────────────────────────────────────────────

def _section_names(report):
    return re.findall(r'^=== (.+) ===$', report, re.M)


@then(parsers.parse('the report has the sections "{names}"'))
def has_sections(ctx, names):
    assert _section_names(ctx['report']) == _list(names)


@then(parsers.parse('every truth field is "{verdict}"'))
def every_truth_field(ctx, verdict):
    for form in _section_names(ctx['report']):
        for field in _TRUTH[form]:
            assert f"  {field}: {verdict}\n" in ctx['report'], (field, ctx['report'])


@then(parsers.parse('the report shows "{text}"'))
@then(parsers.parse('the report says "{text}"'))
def report_shows(ctx, text):
    assert text in ctx['report'], ctx['report']


@then(parsers.parse('the report header is "{header}"'))
def report_header(ctx, header):
    assert ctx['report'].splitlines()[0] == header


@then(parsers.parse('neither {a:g} nor {b:g} appears in the report, in any format'))
def values_masked(ctx, a, b):
    for v in (a, b):
        for shape in (f'{v:.0f}', f'{v:,.0f}', f'{v:.1f}', f'{v:,.2f}'):
            assert shape not in ctx['report'], shape


@then(parsers.parse('a report file is written under "{folder}"'))
def report_file(ctx, folder):
    assert len(ctx['report_files']) == 1
    assert ctx['report_files'][0].parent == ctx['tmp'] / folder.rstrip('/')


@then(parsers.parse('the console shows "{verdict}" and the report file path'))
def console(ctx, verdict):
    rel = ctx['report_files'][0].relative_to(ctx['tmp'])
    assert ctx['console'].strip() == f"{verdict} - report: {rel}"


@then(parsers.parse('the harness exits with {code:d}'))
def exits_with(ctx, code):
    assert ctx['exit'] == code
