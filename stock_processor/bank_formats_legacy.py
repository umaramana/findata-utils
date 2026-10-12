"""
Adapters that put the Chase (checking, credit card) and Citi checking parsers on the Bank Statements
page. Each takes page texts and returns {transactions, unparsed, totals} like the Regions parsers:
transactions = [{date, description, amount, section}], totals = {name: (printed, extracted, ok)}.
The parsers themselves are imported unchanged.
"""
import re
from datetime import date

import extract_chase_txns as chase
import extract_chase_cc_txns as chase_cc
import extract_bank_txns as citi
import extract_regions_txns as regions   # only for its "Month d, yyyy through ..." period reader


def _check(printed, extracted):
    return (round(printed, 2), round(extracted, 2), abs(printed - extracted) < 0.005)


def _md(mmdd, year):
    """date from 'MM/DD' (or 'MM/DD/YY') and a default year; None when unreadable."""
    m = re.match(r'^(\d{2})/(\d{2})(?:/(\d{2}))?$', mmdd or '')
    if not m:
        return None
    y = 2000 + int(m.group(3)) if m.group(3) else year
    try:
        return date(y, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def parse_chase_checking(pages):
    period = None
    for p in pages:
        period = regions.parse_period(p)
        if period:
            break
    if period is None:
        raise ValueError('statement period line not found ("... through ...")')
    txns, printed = [], {}
    for text in pages:
        page_txns, page_totals = chase.parse_page(text)
        for t in page_txns:
            mm = re.match(r'^(\d{2})/(\d{2})$', t['date'] or '')
            d = regions._to_date(mm.group(1), mm.group(2), period) if mm else None
            status = None
            if d is None:
                d, status = period[1], 'date unreadable'
            row = {'date': d, 'description': t['description'], 'amount': t['amount'],
                   'section': t['section']}
            if status:
                row['status'] = status
            txns.append(row)
        for sec, amt in page_totals.items():
            printed[sec] = printed.get(sec, 0.0) + amt
    totals = {}
    for sec, pr in printed.items():
        ex = abs(sum(t['amount'] for t in txns if t['section'] == sec))
        totals[sec] = _check(pr, ex)
    return {'transactions': txns, 'unparsed': [], 'totals': totals}


def parse_chase_cc(pages):
    closing = None
    for p in pages:
        m = chase_cc._PERIOD_RE.search(p)
        if m:
            closing = m.group(2)
            break
    if closing is None:
        raise ValueError('"Opening/Closing Date" line not found')
    cm, _, cy = (int(x) for x in closing.split('/'))
    txns, printed = [], None
    for text in pages:
        page_txns, total = chase_cc.parse_page(text)
        for t in page_txns:
            mo, dd = t['date'].split('/')
            year = 2000 + cy - (1 if int(mo) > cm else 0)   # Dec rows on a January close
            txns.append({'date': date(year, int(mo), int(dd)), 'description': t['description'],
                         'amount': t['amount'], 'section': 'Credit card'})
        if total is not None:
            printed = total
    totals = {}
    if printed is not None:
        totals['Transactions this cycle'] = _check(printed, abs(sum(t['amount'] for t in txns)))
    return {'transactions': txns, 'unparsed': [], 'totals': totals}


def parse_citi(pages):
    year = None
    for p in pages:
        year = citi.extract_year_from_text(p)
        if year:
            break
    txns, last_totals = [], None
    for text in pages:
        page_txns = citi.parse_transactions(text)
        exp_sub, exp_add = citi.parse_page_totals(text)
        page_txns, _ = citi._try_exclude_total_row(page_txns, exp_sub, exp_add)
        if exp_sub is not None:
            last_totals = (exp_sub, exp_add)   # last page carries the cumulative total
        txns.extend(page_txns)
    for t in txns:
        t['statement_period'] = 'x'
        t.setdefault('flag', '')
    citi._reconcile_and_correct(txns)          # balance walk; only sets t['flag']

    rows, unparsed = [], []
    for t in txns:
        sub, add = citi._to_float(t['subtracted']), citi._to_float(t['added'])
        d = _md(t['date'], year)
        if d is None or (sub is None and add is None):
            unparsed.append(f"{t['date']} {t['description']}")
            continue
        row = {'date': d, 'description': t['description'],
               'amount': (add or 0) - (sub or 0),
               'section': 'Added' if add else 'Subtracted'}
        if t.get('flag'):
            row['status'] = t['flag']
        rows.append(row)
    totals = {}
    if last_totals:
        totals['Subtracted'] = _check(last_totals[0], -sum(r['amount'] for r in rows if r['amount'] < 0))
        totals['Added'] = _check(last_totals[1], sum(r['amount'] for r in rows if r['amount'] > 0))
    return {'transactions': rows, 'unparsed': unparsed, 'totals': totals}
