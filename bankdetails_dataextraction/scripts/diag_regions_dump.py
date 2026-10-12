"""Diag: dump what the Regions parser receives. Usage: python diag_regions_dump.py file.pdf [more.pdf]
Writes bank_dump.txt next to where you run it. Redact account numbers/names before sharing."""
import sys
import traceback
from pdf_text import file_pages
import extract_regions_txns as R

out = []
for path in sys.argv[1:]:
    out.append(f'===== {path}')
    try:
        pages, how = file_pages(path)
        out.append(f'read as: {how}; pages: {len(pages)}; chars per page: {[len(p) for p in pages]}')
        for i, p in enumerate(pages, 1):
            lines = p.split('\n')
            out.append(f'--- page {i}: {len(lines)} lines; first 40 (repr):')
            out += [repr(l) for l in lines[:40]]
            hdrs = [(n, repr(l[:60])) for n, l in enumerate(lines) if R._header(l.strip()) is not None]
            out.append(f'headers recognised (line no, text): {hdrs}')
        out.append(f'period: {[R.parse_period(p) for p in pages]}')
        res = R.parse_statement(pages)
        out.append(f"rows: {len(res['transactions'])}; unparsed: {len(res['unparsed'])}")
        out.append(f"printed totals: {res['printed_totals']}")
        out.append(f'reconcile: {R.reconcile(res)}')
    except Exception:
        out.append(traceback.format_exc())
open('bank_dump.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('wrote bank_dump.txt')
