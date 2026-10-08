"""
Regions checking / savings statement parser (text in, rows out).

Input is the text of each statement page: the text layer for checking, OCR text for
savings (an image PDF). No OCR or PDF library is imported here.

Sections and sign (amounts print unsigned; the section gives the sign):
  DEPOSITS & CREDITS -> positive      INTEREST    -> positive
  WITHDRAWALS        -> negative      CHECKS      -> negative

Dates print as MM/DD with no year; the year comes from the page-1 period line
("<TITLE> January 14, 2026 through February 10, 2026").
"""
import re
from datetime import date

_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july',
           'august', 'september', 'october', 'november', 'december']

_PERIOD_RE = re.compile(
    r'(%s)\s+(\d{1,2}),\s*(\d{4})\s+through\s+(%s)\s+(\d{1,2}),\s*(\d{4})'
    % ('|'.join(_MONTHS), '|'.join(_MONTHS)), re.I)

# header text (after stripping punctuation / "continued") -> (sign, canonical name)
_SECTIONS = {
    'DEPOSITS & CREDITS': (+1, 'Deposits & Credits'),
    'INTEREST':           (+1, 'Interest'),
    'WITHDRAWALS':        (-1, 'Withdrawals'),
    'CHECKS':             (-1, 'Checks'),
}

_AMT = r'\$?(\d[\d,]*\.\d{2})'
_AMT_TAIL_RE = re.compile(_AMT + r'\s*\S{0,3}$')
_DATE_ROW_RE = re.compile(r'^(\d{2})/(\d{2})[.\s_]+(.+)$')
_TOTAL_RE = re.compile(r'^\s*total\s+(.+?)\s+' + _AMT + r'\s*\S{0,3}$', re.I)
# one check: date, check no. (optional trailing * = break in sequence), amount.
# A line holds one or two of these (two side-by-side blocks); findall gets both,
# in whatever order the text extractor emitted the columns.
_CHECK_RE = re.compile(r'(\d{2})/(\d{2})\s+(\d{3,6})\s*\*?\s+' + _AMT)
_IGNORE_HEADER_WORDS = ('BALANCE', 'SUMMARY')


_LONE_DATE_RE = re.compile(r'^\d{2}/\d{2}$')
_LONE_TOTAL_RE = re.compile(r'^total\s+[A-Za-z &]+$', re.I)
_MAX_JOIN = 6


def _join_split_rows(lines):
    """Some text layers put each column on its own line: '03/02', description, '2,500.00'
    (and 'Total Withdrawals', '$118,998.18').
    Join a lone MM/DD line with the lines after it up to the first one ending in an amount
    (at most _MAX_JOIN lines, stopping at another lone date); otherwise the date is left alone."""
    out, i = [], 0
    while i < len(lines):
        end = None
        if _LONE_DATE_RE.match(lines[i].strip()) or _LONE_TOTAL_RE.match(lines[i].strip()):
            for j in range(i + 1, min(i + 1 + _MAX_JOIN, len(lines))):
                nxt = lines[j].strip()
                if _LONE_DATE_RE.match(nxt) or _LONE_TOTAL_RE.match(nxt):
                    break
                if _AMT_TAIL_RE.search(nxt):
                    end = j
                    break
        if end is None:
            out.append(lines[i])
            i += 1
        else:
            out.append(' '.join(x.strip() for x in lines[i:end + 1] if x.strip()))
            i = end + 1
    return out


def parse_period(text):
    """(start_date, end_date) from the period line, or None."""
    m = _PERIOD_RE.search(text)
    if not m:
        return None
    sm, sd, sy, em, ed, ey = m.groups()
    return (date(int(sy), _MONTHS.index(sm.lower()) + 1, int(sd)),
            date(int(ey), _MONTHS.index(em.lower()) + 1, int(ed)))


def _year_for(month, period):
    start, end = period
    if start.year == end.year:
        return end.year
    return start.year if month >= start.month else end.year


def _to_date(mm, dd, period):
    return date(_year_for(int(mm), period), int(mm), int(dd))


def _header(line):
    """(sign, name) for a section header, (0, None) for an ignored block, else None."""
    if _DATE_ROW_RE.match(line):
        return None
    norm = re.sub(r'\(?\s*continued\s*\)?', '', line, flags=re.I)
    norm = re.sub(r'[^A-Za-z&\s]', '', norm).strip().upper()
    norm = re.sub(r'\s+', ' ', norm)
    if norm in _SECTIONS:
        return _SECTIONS[norm]
    if (line.strip() == line.strip().upper()
            and any(w in norm for w in _IGNORE_HEADER_WORDS)):
        return 0, None
    return None


def parse_statement(pages):
    """
    pages: list of page texts. Returns dict:
      period          (start, end) dates
      transactions    [{date, description, amount, section}]  (checks: description 'Check #911')
      printed_totals  {section: positive amount}, summed across pages
      unparsed        date-prefixed lines in a section that gave no amount (nothing dropped silently)
    """
    period = None
    for text in pages:
        period = parse_period(text)
        if period:
            break
    if period is None:
        raise ValueError('statement period line not found ("... through ...")')

    txns, totals, unparsed = [], {}, []
    sign, section = 0, None
    for text in pages:
        for raw in _join_split_rows(text.split('\n')):
            line = raw.strip()
            if not line:
                continue

            tm = _TOTAL_RE.match(line)
            if tm:
                label = re.sub(r'[^A-Za-z&\s]', '', tm.group(1)).strip().upper()
                if label in _SECTIONS:
                    name = _SECTIONS[label][1]
                    totals[name] = totals.get(name, 0.0) + float(tm.group(2).replace(',', ''))
                continue

            h = _header(line)
            if h is not None:
                sign, section = h
                continue
            if not sign:
                continue

            if section == 'Checks':
                for mm, dd, no, amt in _CHECK_RE.findall(line):
                    txns.append({'date': _to_date(mm, dd, period),
                                 'description': f'Check #{no}',
                                 'amount': sign * float(amt.replace(',', '')),
                                 'section': section})
                continue

            m = _DATE_ROW_RE.match(line)
            if not m:
                # wrapped description: a short line with no amount extends the previous row
                if (txns and txns[-1]['section'] == section and len(line) < 100
                        and not _AMT_TAIL_RE.search(line)):
                    txns[-1]['description'] += ' ' + re.sub(r'\s{2,}', ' ', line)
                continue
            mm, dd, rest = m.groups()
            am = _AMT_TAIL_RE.search(rest)
            if not am:
                unparsed.append(line)
                continue
            desc = re.sub(r'\s{2,}', ' ', rest[:am.start()]).strip()
            txns.append({'date': _to_date(mm, dd, period),
                         'description': desc,
                         'amount': sign * float(am.group(1).replace(',', '')),
                         'section': section})

    return {'period': period, 'transactions': txns,
            'printed_totals': totals, 'unparsed': unparsed}


def reconcile(result):
    """{section: (printed, extracted, ok)}; sections with no printed total (Interest) get printed=None, ok=None."""
    extracted = {}
    for t in result['transactions']:
        extracted[t['section']] = extracted.get(t['section'], 0.0) + abs(t['amount'])
    out = {}
    for name in {n for _, n in _SECTIONS.values()}:
        ex = round(extracted.get(name, 0.0), 2)
        pr = result['printed_totals'].get(name)
        if pr is None:
            if ex:
                out[name] = (None, ex, None)
        else:
            out[name] = (round(pr, 2), ex, abs(pr - ex) < 0.005)
    return out
