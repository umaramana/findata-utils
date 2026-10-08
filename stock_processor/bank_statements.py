"""
Bank Statements — pure logic for the page (no Streamlit): pick parser by format,
reconcile, fill check payees, build the Summary -> Master -> per-month workbook.
"""
import io
import os
import sys
from collections import defaultdict

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                        'bankdetails_dataextraction', 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

import extract_regions_txns as regions          # noqa: E402
import extract_regions_cc_txns as regions_cc    # noqa: E402
from check_register import fill_checks          # noqa: E402

import bank_formats_legacy as legacy         # noqa: E402


def _regions(mod):
    def parse(pages):
        res = mod.parse_statement(pages)
        return {'transactions': res['transactions'], 'unparsed': res['unparsed'],
                'totals': mod.reconcile(res)}
    return parse


# format label -> parse(pages) -> {transactions, unparsed, totals}
FORMATS = {
    'Regions checking / savings': _regions(regions),
    'Regions credit card': _regions(regions_cc),
    'Chase business checking': legacy.parse_chase_checking,
    'Chase credit card': legacy.parse_chase_cc,
    'Citi checking': legacy.parse_citi,
}

_GREEN = PatternFill('solid', fgColor='C6EFCE')
_RED = PatternFill('solid', fgColor='FFC7CE')
_COLS = ['Date', 'Description', 'Amount', 'Section', 'Status']


def parse_file(fmt, pages):
    """Parse one statement. Returns {transactions, unparsed, totals: {name: (printed, extracted, ok)}}."""
    return FORMATS[fmt](pages)


def apply_register(txns, register=None):
    return fill_checks(txns, register)


def _month_key(d):
    return d.strftime('%Y-%m')


def build_workbook(statements):
    """
    statements: [{'name', 'transactions', 'totals'}] (transactions already status-filled).
    Returns BytesIO: Summary, Master (via the shared collator), then one tab per month.
    """
    import excel_collator as C

    by_month = defaultdict(list)
    for s in statements:
        for t in s['transactions']:
            by_month[_month_key(t['date'])].append(t)

    wb = Workbook()
    wb.remove(wb.active)
    for month in sorted(by_month):
        ws = wb.create_sheet(month)
        ws.append(_COLS)
        for t in sorted(by_month[month], key=lambda x: x['date']):
            ws.append([t['date'].strftime('%m/%d/%Y'), t['description'], f"{t['amount']:.2f}",
                       t['section'], t.get('status', 'OK')])
    if not wb.sheetnames:
        wb.create_sheet('Empty').append(_COLS)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    df = C._collate_sheets(buf, wb.sheetnames)
    types = {'Month': 'text', 'Date': 'date', 'Description': 'text',
             'Amount': 'currency', 'Section': 'text', 'Status': 'text'}
    buf.seek(0)
    out = C._generate_output(buf, df, types)

    wb2 = load_workbook(out)
    ws = wb2.create_sheet('Summary')
    ws.append(['Statement', 'Check', 'Printed', 'Extracted', 'Gap', 'Result'])
    for c in ws[1]:
        c.font = Font(bold=True)
    for s in statements:
        for name, (printed, extracted, ok) in s['totals'].items():
            gap = None if printed is None else round(extracted - printed, 2)
            result = 'no printed total' if ok is None else ('OK' if ok else 'MISMATCH')
            ws.append([s['name'], name, printed, extracted, gap, result])
            if ok is not None:
                ws.cell(ws.max_row, 6).fill = _GREEN if ok else _RED
        if s.get('unparsed'):
            ws.append([s['name'], 'Unparsed lines', None, len(s['unparsed']), None, 'REVIEW'])
            ws.cell(ws.max_row, 6).fill = _RED
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=5):
        for c in row:
            c.number_format = '#,##0.00'
    wb2._sheets.remove(ws)
    wb2._sheets.insert(0, ws)
    final = io.BytesIO()
    wb2.save(final)
    final.seek(0)
    return final
