"""
Regions credit card statement parser (text in, rows out).

Input is the text of each statement page (text PDF). No OCR or PDF library is imported here.

Columns: Tran Date, Post Date, Category, Reference Number, Transactions, Amount.
Sign: statement-signed, like the Chase card parser - a charge is positive, an amount
followed by CR is a credit and negative.
Dates print as MM/DD with no year; the year comes from the Billing Date (MM/DD/YY) in the
Account Summary, and a Dec -> Jan statement rolls the year back for months after the billing month.
"""
import re
from datetime import date

_AMT = r'\$?(\d[\d,]*\.\d{2})'
_BILLING_RE = re.compile(r'Billing\s+Date\s+(\d{2})/(\d{2})/(\d{2,4})', re.I)
# transaction line: tran date, post date, 4-digit category, long reference, description, amount, optional CR
_ROW_RE = re.compile(r'^(\d{2})/(\d{2})\s+(\d{2})/(\d{2})\s+(\d{4})\s+(\d{4,})\s+(.+?)\s+'
                     + _AMT + r'(?:\s*(CR))?\s*$', re.I)
_TWO_DATES_RE = re.compile(r'^\d{2}/\d{2}\s+\d{2}/\d{2}\s')
# Account Summary lines. The text extractor may put a left-column label on the same line
# (e.g. "Credit Limit $18,000 Credits - $132.66"), so these are searched, not anchored; the
# +/- sign in front of the amount keeps them from matching other text. Only the FIRST
# "Total Activity" counts: the per-cardholder header further down carries its own.
_CREDITS_RE = re.compile(r'\bCredits\s*-\s*' + _AMT)
_DEBITS_RE = re.compile(r'\bDebits\s*/\s*Other\s+Fees\s*\+\s*' + _AMT, re.I)
_CASH_RE = re.compile(r'\bCash\s+Advances\s*\+\s*' + _AMT, re.I)
_TOTAL_RE = re.compile(r'\bTotal\s+Activity\s+' + _AMT, re.I)


_LONE_DATE_RE = re.compile(r'^\d{2}/\d{2}$')
_AMT_END_RE = re.compile(_AMT + r'(?:\s*CR)?\s*$', re.I)
_LABEL_RE = re.compile(r'(?:Billing\s+Date|Credits\s*-|Debits\s*/\s*Other\s+Fees\s*\+|Cash\s+Advances\s*\+'
                       r'|Total\s+Activity)\s*$', re.I)
_MAX_JOIN = 8


def _join_split_rows(lines):
    """Some text layers put each field on its own line ('03/02', '03/03', '5411', reference,
    description, '$45.10'; 'Credits -', '$132.66'). Join a transaction (starts at a lone MM/DD
    line, up to the first line ending in an amount; a second lone date right after the first is the
    post date) and a summary label with the line after it. Anything else is left alone."""
    out, i = [], 0
    while i < len(lines):
        cur = lines[i].strip()
        end = None
        if _LONE_DATE_RE.match(cur):
            for j in range(i + 1, min(i + 1 + _MAX_JOIN, len(lines))):
                nxt = lines[j].strip()
                if _LONE_DATE_RE.match(nxt):
                    if all(_LONE_DATE_RE.match(x.strip()) for x in lines[i:j]) and j == i + 1:
                        continue
                    break
                if _AMT_END_RE.search(nxt):
                    end = j
                    break
        elif _LABEL_RE.search(cur) and i + 1 < len(lines):
            end = i + 1
        if end is not None and _LONE_DATE_RE.match(cur) and end + 1 < len(lines) \
                and lines[end + 1].strip().upper() == 'CR':
            end += 1      # the CR marker is its own column, so its own line
        if end is None:
            out.append(lines[i])
            i += 1
        else:
            out.append(' '.join(x.strip() for x in lines[i:end + 1] if x.strip()))
            i = end + 1
    return out


_COMPANY_RE = re.compile(r'Company\s+Summary', re.I)
_DOLLAR_RE = re.compile(r'\$\s*(\d[\d,]*\.\d{2})')


def parse_company_summary(text):
    """The 'Company Summary' table: Previous Balance - Payments - Credits + Purchases/Other
    Debits/Other Fees + Cash Advances + Interest Charges + Late Fees = New Balance. The text layer
    may put the eight dollar figures on one line or one per line, so take the first eight after the
    heading and accept them only if they satisfy that identity. Returns printed totals or {}."""
    m = _COMPANY_RE.search(text)
    if not m:
        return {}
    v = [_num(x) for x in _DOLLAR_RE.findall(text[m.end():])[:8]]
    if len(v) < 8 or abs(v[0] - v[1] - v[2] + v[3] + v[4] + v[5] + v[6] - v[7]) > 0.005:
        return {}
    return {'Payments': v[1], 'Credits': v[2], 'Debits/Other Fees': round(v[3] + v[5] + v[6], 2),
            'Cash Advances': v[4]}


def parse_billing_date(text):
    """Billing date from the Account Summary, or None."""
    m = _BILLING_RE.search(text)
    if not m:
        return None
    mm, dd, yy = m.groups()
    year = int(yy) + 2000 if len(yy) == 2 else int(yy)
    return date(year, int(mm), int(dd))


def _to_date(mm, dd, billing):
    month = int(mm)
    year = billing.year - 1 if month > billing.month else billing.year
    return date(year, month, int(dd))


def _num(s):
    return float(s.replace(',', ''))


def parse_statement(pages):
    """
    pages: list of page texts. Returns dict:
      billing_date    date
      transactions    [{date, post_date, description, amount, section}]  (section: Purchases / Credits)
      printed_totals  {'Credits', 'Debits/Other Fees', 'Cash Advances', 'Total Activity'} from the
                      Account Summary (first occurrence; missing ones are absent)
      unparsed        lines starting with two dates that did not parse (nothing dropped silently)
    """
    billing = None
    pages = ['\n'.join(_join_split_rows(t.split('\n'))) for t in pages]
    for text in pages:
        billing = parse_billing_date(text)
        if billing:
            break
    if billing is None:
        raise ValueError('Billing Date not found in the Account Summary')

    txns, totals, unparsed = [], {}, []
    for text in pages:
        for raw in _join_split_rows(text.split('\n')):
            line = raw.strip()
            if not line:
                continue

            m = _ROW_RE.match(line)
            if m:
                tm, td, pm, pd, _cat, _ref, desc, amt, cr = m.groups()
                amount = _num(amt)
                payment = _cat == '0000' or re.match(r'payment\b', desc, re.I)
                if payment:
                    # a payment received: not in the Account Summary's Credits / Total Activity
                    txns.append({'date': _to_date(tm, td, billing),
                                 'post_date': _to_date(pm, pd, billing),
                                 'description': re.sub(r'\s{2,}', ' ', desc).strip(),
                                 'amount': -amount, 'section': 'Payments'})
                    continue
                txns.append({'date': _to_date(tm, td, billing),
                             'post_date': _to_date(pm, pd, billing),
                             'description': re.sub(r'\s{2,}', ' ', desc).strip(),
                             'amount': -amount if cr else amount,
                             'section': 'Credits' if cr else 'Purchases'})
                continue
            if _TWO_DATES_RE.match(line):
                unparsed.append(line)
                continue

            for key, rx in (('Credits', _CREDITS_RE), ('Debits/Other Fees', _DEBITS_RE),
                            ('Cash Advances', _CASH_RE), ('Total Activity', _TOTAL_RE)):
                sm = rx.search(line)
                if sm and key not in totals:
                    totals[key] = _num(sm.group(1))
                    break

    for text in pages:
        for k, val in parse_company_summary(text).items():
            totals.setdefault(k, val)
    return {'billing_date': billing, 'transactions': txns,
            'printed_totals': totals, 'unparsed': unparsed}


def reconcile(result):
    """
    {name: (printed, extracted, ok)} for the checks the Account Summary supports:
      Credits         sum of CR rows (positive)
      Total Activity  charges - credits
    Debits/Other Fees + Cash Advances is checked against the charges sum, but only when the
    summary prints at least one of them. A name with no printed total is left out.
    """
    acts = [t for t in result['transactions'] if t['section'] != 'Payments']
    charges = sum(t['amount'] for t in acts if t['amount'] > 0)
    credits = -sum(t['amount'] for t in acts if t['amount'] < 0)
    pt = result['printed_totals']
    out = {}

    def add(name, printed, extracted):
        out[name] = (round(printed, 2), round(extracted, 2), abs(printed - extracted) < 0.005)

    if 'Payments' in pt:
        add('Payments', pt['Payments'], -sum(t['amount'] for t in result['transactions']
                                              if t['section'] == 'Payments'))
    if 'Credits' in pt:
        add('Credits', pt['Credits'], credits)
    if 'Debits/Other Fees' in pt or 'Cash Advances' in pt:
        add('Debits + Cash Advances', pt.get('Debits/Other Fees', 0.0) + pt.get('Cash Advances', 0.0), charges)
    if 'Total Activity' in pt:
        add('Total Activity', pt['Total Activity'], charges - credits)
    return out
