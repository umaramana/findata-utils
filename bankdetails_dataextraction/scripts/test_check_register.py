"""Synthetic tests for check_register (invented names). Run: python3 test_check_register.py"""
import os
import tempfile
import unittest

import openpyxl

import check_register as C

COLS = ['Source', 'Page', 'Check #', 'Check No.', 'Date', 'Amount', 'Payee', 'Payee (OCR)', 'Purpose', 'Confidence', 'Flag']


def make_register(rows):
    wb = openpyxl.Workbook()
    wb.active.append(COLS)
    for r in rows:
        wb.active.append(r)
    f = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    f.close()
    wb.save(f.name)
    return f.name


def txns():
    return [{'date': None, 'description': 'Check #911', 'amount': -4878.32, 'section': 'Checks'},
            {'date': None, 'description': 'Check #912', 'amount': -2844.14, 'section': 'Checks'},
            {'date': None, 'description': 'Check #913', 'amount': -10.00, 'section': 'Checks'},
            {'date': None, 'description': 'Card Purchase KLMN', 'amount': -5.0, 'section': 'Withdrawals'}]


class Fill(unittest.TestCase):
    def setUp(self):
        self.path = make_register([
            ['a.pdf', 1, 1, 911, '2026-02-02', 4878.32, 'ACME Supply', 'ACME Suppl', '', 0.9, ''],
            ['a.pdf', 1, 2, '0912', '2026-02-03', 2800.00, 'KLMN Foods', '', '', 0.9, ''],
            ['a.pdf', 1, 3, 913, '', 10.0, '', '', '', 0.1, 'no payee'],
        ])
        self.addCleanup(os.unlink, self.path)
        self.reg = C.load_register(self.path)

    def test_fill_mismatch_missing(self):
        t = C.fill_checks(txns(), self.reg)
        self.assertEqual((t[0]['description'], t[0]['status']), ('ACME Supply', 'payee filled'))
        self.assertEqual((t[1]['description'], t[1]['status']), ('KLMN Foods', 'amount mismatch'))
        self.assertEqual((t[2]['description'], t[2]['status']), ('Check #913', 'check not in register'))
        self.assertEqual((t[3]['description'], t[3]['status']), ('Card Purchase KLMN', 'OK'))

    def test_no_register_keeps_checks(self):
        t = C.fill_checks(txns(), None)
        self.assertEqual({x['status'] for x in t}, {'OK'})
        self.assertEqual(t[0]['description'], 'Check #911')

    def test_bad_file(self):
        p = make_register([])
        wb = openpyxl.load_workbook(p)
        wb.active.delete_rows(1)
        wb.active.append(['x', 'y'])
        wb.save(p)
        self.addCleanup(os.unlink, p)
        with self.assertRaises(ValueError):
            C.load_register(p)


if __name__ == '__main__':
    unittest.main()
