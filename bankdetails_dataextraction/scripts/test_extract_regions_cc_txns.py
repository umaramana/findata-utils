"""Synthetic tests for extract_regions_cc_txns (invented names, shaped like the Regions card screenshots).
Run: python3 test_extract_regions_cc_txns.py
"""
import unittest
from datetime import date

import extract_regions_cc_txns as C

PAGE1 = """Individual Account Summary Page 1 of 4
Credit Limit $18,000 Credits - $132.66
Available Credit $18,000 Purchases/Other
Billing Date 01/22/26 Debits/Other Fees + $458.35
Days in Billing Cycle 31 Cash Advances + $0.00
Total Activity $325.69
"""
# summary lines as a text extractor would emit them when the label columns are split out
SUMMARY = """Billing Date 01/22/26
Credits - $132.66
Debits/Other Fees + $458.35
Cash Advances + $0.00
Total Activity $325.69
"""

ACTIVITY = """Cardholder Activity
ACME CARDHOLDER
Credit Limit $ 18,000 Total Activity $1,140.66
Tran Post
Date Date Category Reference Number Transactions Amount
12/22 12/23 5300 24455015356141014575609 KLMN CLUB #6463 ANDERSON SC 66.92
12/26 12/29 5942 74692165360106434595318 ACME MKTPLACE PMTS Acme.com/billWA 89.87 CR
12/26 12/29 5942 74692165360106443077027 ACME MKTPLACE PMTS Acme.com/billWA 42.79 CR
01/16 01/19 5300 24445006017400103955111 KLMN CLUB #6463 864-261-7609 SC 60.93
01/17 01/19 5300 24455016017141010461290 KLMN CLUB #6463 ANDERSON SC 322.54
01/19 01/20 5300 24445006020400107820720 KLMN CLUB #6463 ANDERSON SC 7.96
"""
# charges 458.35, credits 132.66 -> matches the summary above
ACTIVITY2 = """01/21 01/22 7342 24632696040500642828877 ORKIN LLC 002 877-620-8282 GA 1,000.00
"""


class RegionsCC(unittest.TestCase):
    def test_rows_sign_and_dates(self):
        r = C.parse_statement([SUMMARY, ACTIVITY])
        t = r['transactions']
        self.assertEqual(len(t), 6)
        self.assertEqual(r['unparsed'], [])
        self.assertEqual([x['amount'] for x in t], [66.92, -89.87, -42.79, 60.93, 322.54, 7.96])
        self.assertEqual([x['section'] for x in t][:3], ['Purchases', 'Credits', 'Credits'])
        # Dec -> Jan: months after the billing month (Jan) belong to the previous year
        self.assertEqual(t[0]['date'], date(2025, 12, 22))
        self.assertEqual(t[0]['post_date'], date(2025, 12, 23))
        self.assertEqual(t[3]['date'], date(2026, 1, 16))

    def test_description_drops_reference_and_category(self):
        t = C.parse_statement([SUMMARY, ACTIVITY])['transactions']
        self.assertEqual(t[0]['description'], 'KLMN CLUB #6463 ANDERSON SC')
        self.assertEqual(t[1]['description'], 'ACME MKTPLACE PMTS Acme.com/billWA')
        self.assertNotIn('2445501535', t[0]['description'])

    def test_summary_merged_with_left_column(self):
        r = C.parse_statement([PAGE1, ACTIVITY])
        self.assertEqual(r['billing_date'], date(2026, 1, 22))
        self.assertEqual(r['printed_totals'], {'Credits': 132.66, 'Debits/Other Fees': 458.35,
                                               'Cash Advances': 0.0, 'Total Activity': 325.69})

    def test_summary_totals_and_cardholder_total_ignored(self):
        r = C.parse_statement([SUMMARY, ACTIVITY])
        self.assertEqual(r['printed_totals'], {'Credits': 132.66, 'Debits/Other Fees': 458.35,
                                               'Cash Advances': 0.0, 'Total Activity': 325.69})

    def test_reconcile_ok_and_gap(self):
        r = C.parse_statement([SUMMARY, ACTIVITY])
        rec = C.reconcile(r)
        self.assertTrue(all(ok for _, _, ok in rec.values()), rec)
        self.assertEqual(rec['Total Activity'], (325.69, 325.69, True))
        # drop a row -> every figure that includes it goes red
        r['transactions'].pop(0)
        rec = C.reconcile(r)
        self.assertFalse(rec['Total Activity'][2])
        self.assertFalse(rec['Debits + Cash Advances'][2])
        self.assertTrue(rec['Credits'][2])

    def test_thousands_separator_and_dollar_sign(self):
        r = C.parse_statement([SUMMARY, ACTIVITY2])
        self.assertEqual(r['transactions'][0]['amount'], 1000.0)
        self.assertEqual(r['transactions'][0]['date'], date(2026, 1, 21))

    def test_same_year_statement_has_no_rollover(self):
        r = C.parse_statement(["Billing Date 07/22/26\n06/25 06/26 5300 24445006017400103955111 KLMN 5.00\n"])
        self.assertEqual(r['transactions'][0]['date'], date(2026, 6, 25))

    def test_four_digit_billing_year(self):
        self.assertEqual(C.parse_billing_date('Billing Date 01/22/2026'), date(2026, 1, 22))

    def test_unparsed_two_date_line_reported(self):
        r = C.parse_statement([SUMMARY + "01/16 01/19 5300 244450060174 KLMN no amount here\n"])
        self.assertEqual(len(r['unparsed']), 1)
        self.assertEqual(r['transactions'], [])

    def test_missing_billing_date_raises(self):
        with self.assertRaises(ValueError):
            C.parse_statement(["nothing here"])

    def test_no_summary_means_no_reconcile_rows(self):
        r = C.parse_statement(["Billing Date 01/22/26\n" + ACTIVITY.split('Amount\n')[1]])
        self.assertEqual(C.reconcile(r), {})

    def test_non_transaction_lines_ignored(self):
        r = C.parse_statement([SUMMARY + "Page 2 of 4\nPayment Due Date 02/16/26\n"])
        self.assertEqual(r['transactions'], [])
        self.assertEqual(r['unparsed'], [])

    def test_one_field_per_line_text_layer(self):
        text = "\n".join(["Billing Date", "03/20/26", "Credits -", "$10.00",
                          "03/02", "03/03", "5411", "12345678901", "ACME GROCERY #12", "$45.10",
                          "03/05", "03/06", "5411", "12345678901", "REFUND ACME", "$10.00 CR"])
        r = C.parse_statement([text])
        self.assertEqual([t['amount'] for t in r['transactions']], [45.10, -10.00])
        self.assertEqual(r['printed_totals'], {'Credits': 10.00})

    def test_payment_row_kept_but_not_in_activity_totals(self):
        text = ("Billing Date 03/20/26\nCredits - $0.00\nTotal Activity $45.10\n"
                "03/02 03/03 5411 12345678901 ACME GROCERY #12 $45.10\n"
                "03/09 03/10 0000 0021 PAYMENT - THANK YOU 45.00\n")
        r = C.parse_statement([text])
        self.assertEqual([(x['section'], x['amount']) for x in r['transactions']],
                         [('Purchases', 45.10), ('Payments', -45.00)])
        self.assertTrue(all(ok for _, _, ok in C.reconcile(r).values()))

    def test_company_summary_table_one_figure_per_line(self):
        figs = ["$45.00", "$45.00", "$0.00", "$226.65", "$0.00", "$0.00", "$0.00", "$226.65"]
        text = ("Billing Date 03/20/26\nCompany Summary\nPrevious\nBalance\n" + "\n".join(figs) + "\n"
                "03/02 03/03 5411 12345678901 ACME GROCERY #12 $226.65\n"
                "03/09 03/10 0000 0021 PAYMENT - THANK YOU 45.00 CR\n")
        r = C.parse_statement([text])
        self.assertEqual(r['printed_totals'], {'Payments': 45.0, 'Credits': 0.0,
                                               'Debits/Other Fees': 226.65, 'Cash Advances': 0.0})
        rec = C.reconcile(r)
        self.assertEqual(set(rec), {'Payments', 'Credits', 'Debits + Cash Advances'})
        self.assertTrue(all(ok for _, _, ok in rec.values()))

    def test_company_summary_failing_identity_is_ignored(self):
        text = "Billing Date 03/20/26\nCompany Summary\n" + " ".join(["$1.00"] * 8) + "\n"
        self.assertEqual(C.parse_statement([text])['printed_totals'], {})

    def test_cr_marker_on_its_own_line_is_a_credit(self):
        text = "\n".join(["Billing Date 01/22/26", "12/26", "12/29", "5942", "7469216536010643459531",
                          "AMAZON MKTPLACE PMTS", "Amzn.com/billWA", "89.87", "CR",
                          "01/16", "01/19", "5300", "2444500601740010395511", "SAMS CLUB #6463", "60.93"])
        r = C.parse_statement([text])
        self.assertEqual([(t['amount'], t['section']) for t in r['transactions']],
                         [(-89.87, 'Credits'), (60.93, 'Purchases')])


if __name__ == '__main__':
    unittest.main()
