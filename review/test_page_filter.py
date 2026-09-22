"""Tests for page_filter.py.

    python -m unittest test_page_filter -v
"""
import unittest

import page_filter


class CopyPagesToDropTests(unittest.TestCase):
    def test_no_designator_drops_nothing(self):
        texts = ["Form W-2 Wage and Tax Statement Box 1 Wages 75,000.00"]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [])

    def test_single_copy_drops_nothing(self):
        texts = ["Form W-2 Copy B - To Be Filed With Employee's FEDERAL Tax Return Box 1 Wages 75,000.00"]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [])

    def test_keeps_first_of_multiple_copies(self):
        texts = [
            "Form W-2 Copy B - To Be Filed With Employee's FEDERAL Tax Return Box 1 Wages 75,000.00",
            "Form W-2 Copy C - For EMPLOYEE'S RECORDS Box 1 Wages 75,000.00",
            "Form W-2 Copy 2 - To Be Filed With Recipient's State Tax Return Box 1 Wages 75,000.00",
        ]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [1, 2])

    def test_earliest_undesignated_page_kept_when_present(self):
        texts = [
            "Form W-2 (master copy, no designator) Box 1 Wages 75,000.00",
            "Form W-2 Copy B - To Be Filed With Employee's FEDERAL Tax Return Box 1 Wages 75,000.00",
        ]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [])

    def test_applies_to_1099_int_too(self):
        texts = [
            "Form 1099-INT Copy B For Recipient Box 1 Interest income 1,200.00",
            "Form 1099-INT Copy C For Payer Box 1 Interest income 1,200.00",
        ]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [1])

    def test_image_only_page_left_alone(self):
        texts = ["Form W-2 Copy B Box 1 Wages 75,000.00", ""]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [])

    def test_no_false_positive_on_unrelated_copy_mention(self):
        texts = ["Please retain a copy of this form for your records. Box 1 Wages 75,000.00"]
        self.assertEqual(page_filter.copy_pages_to_drop(texts), [])


if __name__ == "__main__":
    unittest.main()
