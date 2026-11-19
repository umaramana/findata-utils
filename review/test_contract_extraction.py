#!/usr/bin/env python3
"""
The extraction Contract (features/extraction/*.feature) run as tests with pytest-bdd.

Each step below drives the real extract_local() in extract.py. Ollama is a fake (requests.get
and requests.post are replaced, no live model call); the page text layer is faked unless a
scenario needs the real PDF reader. All names are invented (ACME, KLMN).

Usage (WSL, from review/):
  .venv/bin/python -m pytest test_contract_extraction.py
"""
import json
import math
import re

import pytest
import requests
from pytest_bdd import given, parsers, scenarios, then, when

import extract

scenarios('features/extraction')

_json = json      # fake_post's `json=` argument shadows the module


def _list(s):
    """'a, b' -> ['a', 'b']; '(none)' or '' -> []."""
    return [] if s in ('', '(none)') else [x.strip() for x in s.split(',')]


def _tokens(text):
    """A page's word tokens; '(image)' is a page with no text layer."""
    if text == '(image)':
        return []
    return [{"text": w, "x0": 10.0 * i, "top": 100.0} for i, w in enumerate(text.split())]


class FakeResp:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status

    def raise_for_status(self):
        if self.status != 200:
            raise requests.HTTPError(f'{self.status} error')

    def json(self):
        return self.data


@pytest.fixture
def ctx():
    return {'pages': [], 'fields': {}, 'reply': None, 'models': ['acme-text:1b'],
            'ollama_down': False, 'not_pdf': None, 'reads': {}, 'context_length': 128000,
            'show': 'full', 'call_seconds': 0.0, 'form': None, 'name_only': [],
            'done': {'done_reason': 'stop', 'prompt_eval_count': 300, 'eval_count': 90}}


# ── Given ────────────────────────────────────────────────────────────────────────

@given(parsers.parse('a text page reading "{text}"'))
def text_page(ctx, text):
    ctx['pages'].append(_tokens(text))


@given(parsers.parse('the pages "{pages}"'))
def pages(ctx, pages):
    ctx['pages'] = [_tokens(p.strip()) for p in pages.split(' / ')]


@given(parsers.parse('the page tokens "{tokens}"'))
def page_tokens(ctx, tokens):
    """'word@x,y word@x,y ...'"""
    page = []
    for tok in tokens.split():
        word, xy = tok.rsplit('@', 1)
        x, y = xy.split(',')
        page.append({"text": word, "x0": float(x), "top": float(y)})
    ctx['pages'].append(page)


@given(parsers.parse('a text page of {n:d} words with "{value}" as word {k:d}'))
def long_page(ctx, n, value, k):
    """n words, 10 to a line; word k (1-based) is the value, the rest are filler."""
    words = [value if i == k - 1 else f'acme{i}' for i in range(n)]
    ctx['pages'].append([{"text": w, "x0": 40.0 * (i % 10), "top": 100.0 + 12 * (i // 10)}
                         for i, w in enumerate(words)])


@given(parsers.parse('the model reads {field} "{value}" from the prompt'))
def model_reads(ctx, field, value):
    ctx['reads'][field] = value


@given(parsers.parse("the model's context length is {n:d} tokens"))
def context_length(ctx, n):
    ctx['context_length'] = n


@given(parsers.parse('Ollama reports {what} for the model'))
def ollama_reports(ctx, what):
    ctx['show'] = {'no model_info': 'none', 'model_info without a context length': 'no length'}[what]


@given(parsers.parse('the model call takes {seconds:f} seconds'))
def call_takes(ctx, seconds):
    ctx['call_seconds'] = seconds


@given(parsers.parse('the model reply ends with done_reason "{reason}" after {p:d} prompt tokens and {e:d} output tokens'))
def reply_ends(ctx, reason, p, e):
    ctx['done'] = {'done_reason': reason, 'prompt_eval_count': p, 'eval_count': e}


_ANSWER_SPLIT = re.compile(r', (?=[a-z0-9_]+ = |a name-only item for )')
_FORM_PREFIX = re.compile(r'form type "([^"]+)" and (.*)')


@given(parsers.parse('the model answers {field} = {raw}'))
def model_answers(ctx, field, raw):
    """One answer (box_1_wages = "75,000.00"), or several separated by commas, where an answer can
    also be 'a name-only item for <field>' (sent as {"field_name": <field>} with no value), and the
    whole line can start with 'form type "<form>" and' (the form type the model answers)."""
    text = f'{field} = {raw}'
    m = _FORM_PREFIX.fullmatch(text)
    if m:
        ctx['form'], text = m.group(1), m.group(2)
    for part in _ANSWER_SPLIT.split(text):
        if part.startswith('a name-only item for '):
            ctx['name_only'].append(part.removeprefix('a name-only item for '))
            continue
        name, value = part.split(' = ', 1)
        ctx['fields'][name] = json.loads(value)


@given(parsers.parse('the model replies {reply}'))
def model_replies(ctx, reply):
    ctx['reply'] = reply


@given(parsers.parse('Ollama has the models "{installed}"'))
def ollama_models(ctx, installed):
    if installed == '(Ollama not running)':
        ctx['ollama_down'] = True
    ctx['models'] = [] if ctx['ollama_down'] else _list(installed)


@given(parsers.parse('"{name}" is not a PDF'))
def not_a_pdf(ctx, name):
    ctx['not_pdf'] = name


# ── When ─────────────────────────────────────────────────────────────────────────

class FakeClock:
    """Stands in for extract's `time` module: monotonic() moves only when the fake model is called."""
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


def _run(ctx, monkeypatch, tmp_path, name, model=None):
    ctx['calls'] = []
    clock = FakeClock()
    used_model = model or (ctx['models'][0] if ctx['models'] else None)

    def fake_get(url, timeout=None):
        if ctx['ollama_down']:
            raise requests.ConnectionError('connection refused')
        return FakeResp({'models': [{'name': m} for m in ctx['models']]})

    def fake_post(url, json=None, timeout=None):
        if url.endswith('/api/show'):
            if json != {'model': used_model}:      # real Ollama rejects a show request without the model
                return FakeResp({'error': 'model is required'}, status=400)
            if ctx['show'] == 'none':
                return FakeResp({})
            if ctx['show'] == 'no length':
                return FakeResp({'model_info': {'acme.embedding_length': 2048}})
            return FakeResp({'model_info': {'acme.context_length': ctx['context_length']}})
        ctx['calls'].append(json)
        clock.now += ctx['call_seconds']
        reply = ctx['reply']
        if reply is None:
            form = ctx['form'] or extract.guess_form_type(name) or 'W-2'
            fields = dict(ctx['fields'])
            fields.update({f: v for f, v in ctx['reads'].items() if v in json['prompt']})
            if ctx['name_only']:   # the list-of-items reply shape, some items with a name and no value
                fields = ([{'field_name': f, 'value': v} for f, v in fields.items()]
                          + [{'field_name': f} for f in ctx['name_only']])
            reply = _json.dumps({'form_type': form, 'fields': fields})
        return FakeResp({'response': reply, **ctx['done']})

    monkeypatch.setattr(extract.requests, 'get', fake_get)
    monkeypatch.setattr(extract.requests, 'post', fake_post)
    monkeypatch.setattr(extract, 'time', clock)
    path = tmp_path / name
    if ctx['not_pdf']:
        path.write_bytes(b'not a pdf')     # the real PDF reader runs
    else:
        page_list = ctx['pages']
        monkeypatch.setattr(extract, 'extract_page_tokens', lambda p: [list(t) for t in page_list])
    try:
        ctx['result'] = extract.extract_local(path, model=model,   # hint from the filename, as run.py does
                                              form_hint=extract.guess_form_type(name))
    except Exception as e:  # noqa: BLE001 - the Then step checks the type
        ctx['error'] = e



@when(parsers.parse('"{name}" is extracted locally'))
def extracted(ctx, monkeypatch, tmp_path, name):
    _run(ctx, monkeypatch, tmp_path, name)


@when(parsers.parse('"{name}" is extracted locally with model "{model}"'))
def extracted_with_model(ctx, monkeypatch, tmp_path, name, model):
    _run(ctx, monkeypatch, tmp_path, name, None if model == '(none)' else model)


@when(parsers.parse('the form type is guessed from "{filename}"'))
def guess(ctx, filename):
    ctx['guess'] = extract.guess_form_type(filename)


# ── Then ─────────────────────────────────────────────────────────────────────────

def _result(ctx):
    assert 'error' not in ctx, f"extraction raised {ctx['error']!r}"
    return ctx['result']


@then(parsers.parse('field {field} is {expected}'))
def field_is(ctx, field, expected):
    assert _result(ctx).fields.get(field) == json.loads(expected)


@then(parsers.parse('field {field} has confidence "{confidence}"'))
def field_confidence(ctx, field, confidence):
    assert _result(ctx).field_confidence.get(field) == confidence


@then(parsers.parse('the verification failures are "{failures}"'))
def failures(ctx, failures):
    assert _result(ctx).verification_failures == _list(failures)


@then(parsers.parse('the missing required fields are "{missing}"'))
def missing(ctx, missing):
    assert _result(ctx).missing_required == _list(missing)


@then(parsers.parse('the status is "{status}"'))
def status(ctx, status):
    assert _result(ctx).status == status


@then(parsers.parse('the dropped page indices are "{dropped}"'))
def dropped(ctx, dropped):
    assert _result(ctx).dropped_pages == [int(i) for i in _list(dropped)]


@then(parsers.parse('{n:d} pages were kept'))
def kept(ctx, n):
    assert len(_result(ctx).page_routes) == n


@then(parsers.parse('the prompt shows the line "{line}"'))
def prompt_line(ctx, line):
    _result(ctx)
    assert line in ctx['calls'][0]['prompt'].splitlines()


@then(parsers.parse('the prompt does not contain "{text}"'))
def prompt_lacks(ctx, text):
    _result(ctx)
    assert text not in ctx['calls'][0]['prompt']


@then(parsers.parse('the prompt contains "{text}"'))
def prompt_has(ctx, text):
    _result(ctx)
    assert text in ctx['calls'][0]['prompt']


@then('the request asks for one JSON reply, not a stream')
def json_not_stream(ctx):
    _result(ctx)
    call = ctx['calls'][0]
    # 'json' (no form known) or a JSON schema (form known) - both hold Ollama to one JSON object
    assert call['stream'] is False and (call['format'] == 'json' or call['format'].get('type') == 'object')


def _fields_schema(ctx):
    return ctx['calls'][0]['format']['properties']['fields']


@then(parsers.parse('the reply format allows only the fields "{fields}", all required'))
def format_fields(ctx, fields):
    _result(ctx)
    fmt = ctx['calls'][0]['format']
    assert fmt['required'] == ['form_type', 'fields']
    assert fmt['properties']['form_type']['enum'] == ['W-2', '1099-INT', '1099-DIV']
    f = _fields_schema(ctx)
    assert list(f['properties']) == _list(fields) and f['required'] == _list(fields)
    assert f['additionalProperties'] is False


_TYPES = {
    'a string or null': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
    'a list of state/amount': {'anyOf': [{'type': 'array', 'items': {
        'type': 'object', 'properties': {'state': {'type': 'string'}, 'amount': {'type': 'string'}},
        'required': ['state', 'amount']}}, {'type': 'null'}]},
    'a list of box/label/value': {'anyOf': [{'type': 'array', 'items': {
        'type': 'object', 'properties': {'box': {'type': 'string'}, 'label': {'type': 'string'},
                                         'value': {'type': 'string'}},
        'required': ['box', 'label', 'value']}}, {'type': 'null'}]},
}


@then(parsers.parse('the reply format types {field} as {kind}'))
def format_type(ctx, field, kind):
    _result(ctx)
    assert _fields_schema(ctx)['properties'][field] == _TYPES[kind]


@then('the reply format is plain JSON')
def format_plain(ctx):
    _result(ctx)
    assert ctx['calls'][0]['format'] == 'json'


@then(parsers.parse('the result has no field named "{name}"'))
def no_field(ctx, name):
    r = _result(ctx)
    assert name not in r.fields and name not in r.field_confidence


@then(parsers.parse('model_said is {expected}'))
def model_said_is(ctx, expected):
    assert _result(ctx).model_said == json.loads(expected)


@then(parsers.parse('not_returned is "{names}"'))
def not_returned_is(ctx, names):
    assert _result(ctx).not_returned == _list(names)


@then(parsers.parse('the record has model_said {said} and not_returned {names}'))
def record_has(ctx, said, names):
    record = json.loads(json.dumps(_result(ctx).to_dict()))   # as run.py writes it
    assert record['model_said'] == json.loads(said)
    assert record['not_returned'] == json.loads(names)


@then(parsers.parse('the extraction time is {ms:d} ms'))
def extraction_time(ctx, ms):
    assert _result(ctx).extraction_time_ms == ms


@then(parsers.parse('the result names the source file "{name}" and the mode "{mode}"'))
def source_and_mode(ctx, name, mode):
    r = _result(ctx)
    assert (r.source_file, r.extraction_mode) == (name, mode)


@then('no page image is sent')
def no_images(ctx):
    _result(ctx)
    assert not ctx['calls'][0].get('images')


@then('the model was not called')
def not_called(ctx):
    assert ctx['calls'] == []


@then(parsers.parse("num_ctx is half the prompt's characters rounded up plus 1024"))
def num_ctx(ctx):
    _result(ctx)
    call = ctx['calls'][0]
    assert call['options']['num_ctx'] == math.ceil(len(call['prompt']) / 2) + 1024


@then(parsers.parse('num_predict is {n:d}'))
def num_predict(ctx, n):
    _result(ctx)
    assert ctx['calls'][0]['options']['num_predict'] == n


@then(parsers.parse('the unread pages are "{pages}"'))
def unread_pages(ctx, pages):
    got = [f"{u['source_file']} page {u['page']}: {u['reason']}" for u in _result(ctx).unread_pages]
    assert got == [x.strip() for x in pages.split(';')]


@then(parsers.parse('the parse failures are "{failures}"'))
def parse_failures(ctx, failures):
    assert _result(ctx).parse_failures == _list(failures)


@then(parsers.parse('the model used is "{model}"'))
def model_used(ctx, model):
    _result(ctx)
    assert ctx['calls'][0]['model'] == model


@then(parsers.parse('the form type is "{form_type}"'))
def form_type(ctx, form_type):
    assert _result(ctx).form_type == form_type


@then(parsers.parse('extraction stops with a {kind} error saying "{message}"'))
def stops(ctx, kind, message):
    err = ctx.get('error')
    assert err is not None, 'extraction did not stop'
    assert type(err).__name__ == kind
    assert message in str(err)


@then(parsers.parse('the guess is "{form_type}"'))
def guess_is(ctx, form_type):
    assert ctx['guess'] == (None if form_type == '(none)' else form_type)
