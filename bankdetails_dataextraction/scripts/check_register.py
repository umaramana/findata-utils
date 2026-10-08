"""Fill statement check descriptions from a Check Extractor register (Excel export).

Register columns used: Check No., Amount, Payee (others ignored). Lookup is exact on check number.
Each 'Check #911' row gets a `status`: 'payee filled', 'check not in register' or 'amount mismatch'.
"""
import re

import openpyxl

_CHECK_DESC = re.compile(r'^Check #(\d+)$')


def _norm(no):
    s = str(no).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s.lstrip('0') or s if s.isdigit() else s


def load_register(path):
    """{check no: (payee, amount or None)}; rows with no check number or no payee are skipped, first row wins."""
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = ws.iter_rows(values_only=True)
    head = [str(c).strip() if c is not None else '' for c in next(rows, [])]
    try:
        i_no, i_amt, i_payee = head.index('Check No.'), head.index('Amount'), head.index('Payee')
    except ValueError as e:
        raise ValueError(f'not a check register (missing column): {e}')
    reg = {}
    for r in rows:
        no, payee = r[i_no], r[i_payee]
        if no in (None, '') or not str(payee or '').strip():
            continue
        amt = r[i_amt]
        if isinstance(amt, str):
            amt = float(re.sub(r'[,$\s]', '', amt) or 0) if re.search(r'\d', amt) else None
        reg.setdefault(_norm(no), (str(payee).strip(), amt))
    return reg


def fill_checks(txns, register=None):
    """Set `status` on every transaction; rewrite 'Check #N' descriptions from the register. Mutates and returns txns."""
    for t in txns:
        t['status'] = t.get('status') or 'OK'
        m = _CHECK_DESC.match(t['description'])
        if not m:
            continue
        hit = (register or {}).get(_norm(m.group(1)))
        if not hit:
            t['status'] = 'check not in register' if register is not None else 'OK'
            continue
        payee, amt = hit
        t['description'] = payee
        t['status'] = ('amount mismatch' if amt is not None and abs(abs(t['amount']) - abs(float(amt))) > 0.005
                       else 'payee filled')
    return txns
