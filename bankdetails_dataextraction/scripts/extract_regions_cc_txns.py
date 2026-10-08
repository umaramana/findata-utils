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
_ROW_RE = re.compile(r'^(\d{2})/(\d{2})\s+(\d{2})/(\d{2})\s+(\d{4})\s+(\d{10,})\s+(.+?)\s+'
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
    for text in pages:
        billing = parse_billing_date(text)
        if billing:
            break
    if billing is None:
        raise ValueError('Billing Date not found in the Account Summary')

    txns, totals, unparsed = [], {}, []
    for text in pages:
        for raw in text.split('\n'):
            line = raw.strip()
            if not line:
                continue

            m = _ROW_RE.match(line)
            if m:
                tm, td, pm, pd, _cat, _ref, desc, amt, cr = m.groups()
                amount = _num(amt)
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
    charges = sum(t['amount'] for t in result['transactions'] if t['amount'] > 0)
    credits = -sum(t['amount'] for t in result['transactions'] if t['amount'] < 0)
    pt = result['printed_totals']
    out = {}

    def add(name, printed, extracted):
        out[name] = (round(printed, 2), round(extracted, 2), abs(printed - extracted) < 0.005)

    if 'Credits' in pt:
        add('Credits', pt['Credits'], credits)
    if 'Debits/Other Fees' in pt or 'Cash Advances' in pt:
        add('Debits + Cash Advances', pt.get('Debits/Other Fees', 0.0) + pt.get('Cash Advances', 0.0), charges)
    if 'Total Activity' in pt:
        add('Total Activity', pt['Total Activity'], charges - credits)
    return out
