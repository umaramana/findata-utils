"""Synthetic tests for extract_regions_txns (invented names, shaped like the Regions screenshots).
Run: python3 test_extract_regions_txns.py
"""
import unittest
from datetime import date

import extract_regions_txns as R

PAGE1 = """ACME BUSINESS CHECKING January 14, 2026 through February 10, 2026
SUMMARY
Beginning Balance $1,000.00
DEPOSITS & CREDITS
01/15 Deposit ACME Store 7 1,000.00
01/30 Transfer From Savings Ref# 000000 0001065 250.50
Total Deposits & Credits $1,250.50
"""

PAGE2 = """DEPOSITS & CREDITS (CONTINUED)
02/03 Overdraft Protection Transfer 11.50
Total Deposits & Credits $11.50
WITHDRAWALS
01/20 Card Purchase KLMN Supply #6463 5300 Town SC 29621 8323 262.81
02/02 EB to Savings # 0321568960 Ref# 000000 0001028 6,694.87
Total Withdrawals $6,957.68
CHECKS
Date Check No. Amount Date Check No. Amount
02/02 911 4,878.32 02/04 990 * 11,335.14
02/03 912 2,844.14 02/05 991 3,322.90
02/06 920 * 4,629.76
Total Checks $27,010.26
* Break In Check Sequence.
DAILY BALANCE SUMMARY
01/15 2,000.00
02/02 1,500.00
"""


class Regions(unittest.TestCase):
    def setUp(self):
        self.r = R.parse_statement([PAGE1, PAGE2])
        self.by = {}
        for t in self.r['transactions']:
            self.by.setdefault(t['section'], []).append(t)

    def test_period_and_year_rollover(self):
        self.assertEqual(self.r['period'], (date(2026, 1, 14), date(2026, 2, 10)))
        dates = {t['description']: t['date'] for t in self.r['transactions']}
        self.assertEqual(dates['Deposit ACME Store 7'], date(2026, 1, 15))
        # Dec -> Jan statement: Dec rows get the earlier year
        r = R.parse_statement(["X December 20, 2025 through January 19, 2026\nWITHDRAWALS\n"
                               "12/22 Fee 5.00\n01/03 Fee 6.00\n"])
        self.assertEqual([t['date'] for t in r['transactions']],
                         [date(2025, 12, 22), date(2026, 1, 3)])

    def test_signs_and_counts(self):
        self.assertEqual([t['amount'] for t in self.by['Deposits & Credits']], [1000.0, 250.5, 11.5])
        self.assertTrue(all(t['amount'] < 0 for t in self.by['Withdrawals']))
        self.assertEqual(len(self.by['Withdrawals']), 2)

    def test_description_keeps_digits_amount_taken_from_end(self):
        w = self.by['Withdrawals'][1]
        self.assertEqual(w['description'], 'EB to Savings # 0321568960 Ref# 000000 0001028')
        self.assertEqual(w['amount'], -6694.87)

    def test_checks_two_blocks_star_stripped(self):
        c = self.by['Checks']
        self.assertEqual([t['description'] for t in c],
                         ['Check #911', 'Check #990', 'Check #912', 'Check #991', 'Check #920'])
        self.assertEqual(c[1]['amount'], -11335.14)
        self.assertEqual(c[4]['amount'], -4629.76)

    def test_checks_in_column_order_extract(self):
        # extractor that emits the left block, then the right block
        page = ("A January 14, 2026 through February 10, 2026\nCHECKS\n"
                "02/02 911 100.00\n02/03 912 200.00\n02/04 990 * 300.00\n02/05 991 400.00\n")
        r = R.parse_statement([page])
        self.assertEqual(sum(t['amount'] for t in r['transactions']), -1000.0)

    def test_daily_balance_ignored(self):
        self.assertEqual(len(self.r['transactions']), 3 + 2 + 5)

    def test_reconcile_green(self):
        rec = R.reconcile(self.r)
        self.assertEqual(rec['Deposits & Credits'], (1262.0, 1262.0, True))
        self.assertTrue(all(ok for _, _, ok in rec.values()))

    def test_reconcile_red_on_gap(self):
        bad = PAGE2.replace('4,878.32', '4,878.30')
        rec = R.reconcile(R.parse_statement([PAGE1, bad]))
        self.assertFalse(rec['Checks'][2])

    def test_unparsed_not_dropped(self):
        r = R.parse_statement(["A January 14, 2026 through February 10, 2026\nWITHDRAWALS\n"
                               "02/03 Card Purchase with no amount here\n"])
        self.assertEqual(len(r['unparsed']), 1)

    def test_wrapped_description_joined(self):
        page = ("A January 14, 2026 through February 10, 2026\nWITHDRAWALS\n"
                "02/03 Zelle Payment To ACME Supply 120.00\n  Ref 123 Conf KLMN\n"
                "02/04 Fee 5.00\nTotal Withdrawals $125.00\n")
        r = R.parse_statement([page])
        self.assertEqual(r['transactions'][0]['description'], 'Zelle Payment To ACME Supply Ref 123 Conf KLMN')
        self.assertEqual(r['transactions'][1]['description'], 'Fee')

    def test_missing_period_raises(self):
        with self.assertRaises(ValueError):
            R.parse_statement(["DEPOSITS & CREDITS\n02/03 X 1.00\n"])


SAVINGS_OCR = """ACME SAVINGS February 1, 2026 through February 28, 2026
DEPOSITS & CREDITS
02/03. EB From Checking # 0327957233 Ref# 000000 0001023 500.00
02/10___EB From Checking # 0327957233 Ref# 000000 0001033 $500.00 |
Total Deposits & Credits $1,000.00
INTEREST
02/27 Effective Date 02-28-26 Interest Payment 0.01
WITHDRAWALS |
02/03 EB to Checking # 0343878636 Ref# 000000 0001030 500.00
Total Withdrawals $500.00
"""


class SavingsOcr(unittest.TestCase):
    def test_noisy_ocr_text(self):
        r = R.parse_statement([SAVINGS_OCR])
        self.assertEqual(len(r['transactions']), 4)
        self.assertEqual(r['unparsed'], [])
        rec = R.reconcile(r)
        self.assertEqual(rec['Interest'], (None, 0.01, None))   # interest has no printed total
        self.assertTrue(rec['Deposits & Credits'][2] and rec['Withdrawals'][2])

    def test_interest_description_line_is_not_a_header(self):
        r = R.parse_statement([SAVINGS_OCR])
        interest = [t for t in r['transactions'] if t['section'] == 'Interest']
        self.assertEqual(interest[0]['description'], 'Effective Date 02-28-26 Interest Payment')


if __name__ == '__main__':
    unittest.main()
