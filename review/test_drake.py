"""Tests for drake.py (capability A) and its use by compare.py.

    python -m unittest test_drake -v

Fixtures are fully synthetic Form 1040 PDFs built here with fitz. The "form"
layout imitates the printed 1040 - line-id markers next to amount boxes, two
boxes sharing one row (2a/2b, 3a/3b...), whole dollars, cross-references inside
labels ("Schedule 1, line 10"), dot leaders. It is a model of the real layout,
not a copy of a Drake print; passing here does not prove a real return parses.
"""
import tempfile
import unittest
from pathlib import Path

import fitz

import compare
import drake
import make_test_docs

# id -> (label, marker x, amount x, label x). Rows listed in print order.
_L, _M, _A = 36, 440, 470
_PAGE1 = [
    [("1a", "1a Total amount from Form(s) W-2, box 1 (see instructions)")],
    [("1z", "z Add lines 1a through 1h")],
    [("2a", "2a Tax-exempt interest . . . . . .", 36, 250, 275), ("2b", "b Taxable interest . . . . . .", 320, 480, 505)],
    [("3a", "3a Qualified dividends . . . . . .", 36, 250, 275), ("3b", "b Ordinary dividends . . . . . .", 320, 480, 505)],
    [("4a", "4a IRA distributions . . . . . .", 36, 250, 275), ("4b", "b Taxable amount . . . . . .", 320, 480, 505)],
    [("5a", "5a Pensions and annuities . . . . .", 36, 250, 275), ("5b", "b Taxable amount . . . . . .", 320, 480, 505)],
    [("6a", "6a Social security benefits . . . . .", 36, 250, 275), ("6b", "b Taxable amount . . . . . .", 320, 480, 505)],
    [("7", "7 Capital gain or (loss). Attach Schedule D if required. If not required, check here")],
    [("8", "8 Additional income from Schedule 1, line 10")],
    [("9", "9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7, and 8. This is your total income")],
    [("10", "10 Adjustments to income from Schedule 1, line 26")],
    [("11", "11 Subtract line 10 from line 9. This is your adjusted gross income")],
    [("12", "12 Standard deduction or itemized deductions (from Schedule A)")],
    [("13", "13 Qualified business income deduction. Attach Form 8995 or Form 8995-A")],
    [("14", "14 Add lines 12 and 13")],
    [("15", "15 Subtract line 14 from line 11. If zero or less, enter -0-. This is your taxable income")],
]
_PAGE2 = [
    [("16", "16 Tax (see instructions). Check if any from Form(s): 1 8814 2 4972 3")],
    [("17", "17 Amount from Schedule 2, line 3")],
    [("18", "18 Add lines 16 and 17")],
    [("19", "19 Child tax credit or credit for other dependents from Schedule 8812")],
    [("20", "20 Amount from Schedule 3, line 8")],
    [("21", "21 Add lines 19 and 20")],
    [("22", "22 Subtract line 21 from line 18. If zero or less, enter -0-")],
    [("23", "23 Other taxes, including self-employment tax, from Schedule 2, line 21")],
    [("24", "24 Add lines 22 and 23. This is your total tax")],
    [("25a", "a Form(s) W-2")],
    [("25b", "b Form(s) 1099")],
    [("25c", "c Other forms (see instructions)")],
    [("25d", "d Add lines 25a through 25c")],
    [("26", "26 2024 estimated tax payments and amount applied from 2023 return")],
    [("27", "27 Earned income credit (EIC)")],
    [("28", "28 Additional child tax credit from Schedule 8812")],
    [("29", "29 American opportunity credit from Form 8863, line 8")],
    [("31", "31 Amount from Schedule 3, line 15")],
    [("32", "32 Add lines 27, 28, 29, and 31. These are your total other payments and refundable credits")],
    [("33", "33 Add lines 25d, 26, and 32. These are your total payments")],
    [("34", "34 If line 33 is more than line 24, subtract line 24 from line 33. This is the amount you overpaid")],
    [("35a", "35a Amount of line 34 you want refunded to you. If Form 8888 is attached, check here")],
    [("37", "37 Subtract line 33 from line 24. This is the amount you owe")],
]
_BLANK_IF_ZERO = {"2a", "4a", "4b", "5a", "5b", "6a", "6b", "7", "8", "10", "13", "17", "20", "23",
                  "25b", "25c", "26", "27", "28", "29", "31", "32", "34", "35a", "37"}


def _fmt(v):
    return f"({abs(v):,.0f})" if v < 0 else f"{v:,.0f}"


def _draw_rows(page, rows, values, y0=60, dy=16):
    for r, row in enumerate(rows):
        y = y0 + r * dy
        for cell in row:
            lid, label = cell[0], cell[1]
            lx, mx, ax = (cell[2], cell[3], cell[4]) if len(cell) > 2 else (_L, _M, _A)
            page.insert_text((lx, y), label + " . . . . . .", fontsize=7)
            page.insert_text((mx, y), lid, fontsize=7)
            v = values.get(lid)
            if v is not None:
                page.insert_text((ax, y), _fmt(v), fontsize=7)


def write_1040(path, values, year=2024, decoys=True):
    """values: line id -> amount, or None/missing for a blank amount box."""
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((36, 30), f"Form 1040 U.S. Individual Income Tax Return {year}", fontsize=9)
    _draw_rows(p1, _PAGE1, values)
    p2 = doc.new_page()
    p2.insert_text((36, 30), f"Form 1040 ({year})   Page 2", fontsize=9)
    _draw_rows(p2, _PAGE2, values)
    if decoys:
        # Not 1040 pages: numbers here must never leak into the 1040 lines.
        p3 = doc.new_page()
        p3.insert_text((36, 30), f"Schedule 1 (Form 1040) {year}", fontsize=9)
        p3.insert_text((36, 60), "Total income . . . . 9 999,999", fontsize=7)
        p3.insert_text((36, 76), "Adjusted gross income . . . . 11 888,888", fontsize=7)
        p4 = doc.new_page()
        p4.insert_text((36, 30), "Form 1040-ES Payment Voucher", fontsize=9)
        p4.insert_text((36, 60), "Amount of estimated tax you are paying . . . . 24 777,777", fontsize=7)
    doc.save(path)


def make_values(**over):
    """A self-consistent return. Keyword args override the *input* lines; derived lines follow."""
    b = dict(w2=100_000, exempt=0, interest=1_500, qual=800, div=1_000, cap=0, sch1=0, adj=2_500,
             ded=29_200, qbi=0, tax=8_000, ctc=2_000, other_tax=0, wh=9_000, eic=0, actc=0)
    raw = over.pop("raw", {})
    b.update(over)
    v = {"1a": b["w2"], "1z": b["w2"], "2a": b["exempt"], "2b": b["interest"], "3a": b["qual"], "3b": b["div"],
         "7": b["cap"], "8": b["sch1"], "10": b["adj"], "12": b["ded"], "13": b["qbi"], "16": b["tax"],
         "19": b["ctc"], "23": b["other_tax"], "25a": b["wh"], "27": b["eic"], "28": b["actc"]}
    v["9"] = b["w2"] + b["interest"] + b["div"] + b["cap"] + b["sch1"]
    v["11"] = v["9"] - b["adj"]
    v["14"] = b["ded"] + b["qbi"]
    v["15"] = max(0, v["11"] - v["14"])
    v["18"] = b["tax"]
    v["21"] = b["ctc"]
    v["22"] = max(0, v["18"] - v["21"])
    v["24"] = v["22"] + b["other_tax"]
    v["25d"] = b["wh"]
    v["32"] = b["eic"] + b["actc"]
    v["33"] = v["25d"] + v["32"]
    v["34"] = max(0, v["33"] - v["24"])
    v["37"] = max(0, v["24"] - v["33"])
    v.update(raw)
    return {k: (None if (x == 0 and k in _BLANK_IF_ZERO) else x) for k, x in v.items()}


# --- TY2025 layout: 7a, 11a/11b, 12e, 13a/13b, 14 = 12e+13a+13b, 27a, 30, 37 incl. 38 ---
_PAGE1_2025 = [
    [("1a", "1a Total amount from Form(s) W-2, box 1 (see instructions)")],
    [("1z", "z Add lines 1a through 1h")],
    [("2a", "2a Tax-exempt interest", 36, 250, 275), ("2b", "b Taxable interest", 320, 480, 505)],
    [("3a", "3a Qualified dividends", 36, 250, 275), ("3b", "b Ordinary dividends", 320, 480, 505)],
    [("4a", "4a IRA distributions", 36, 250, 275), ("4b", "b Taxable amount", 320, 480, 505)],
    [("5a", "5a Pensions and annuities", 36, 250, 275), ("5b", "b Taxable amount", 320, 480, 505)],
    [("6a", "6a Social security benefits", 36, 250, 275), ("6b", "b Taxable amount", 320, 480, 505)],
    [("7a", "7a Capital gain or (loss). Attach Schedule D if required.")],
    [("8", "8 Additional income from Schedule 1, line 10")],
    [("9", "9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7a, and 8. This is your total income")],
    [("10", "10 Adjustments to income from Schedule 1, line 26")],
    [("11a", "11a Subtract line 10 from line 9. This is your adjusted gross income")],
]
_PAGE2_2025 = [
    [("11b", "11b Amount from line 11a")],
    [("12e", "12e Standard deduction or itemized deductions (from Schedule A)")],
    [("13a", "13a Qualified business income deduction. Attach Form 8995 or Form 8995-A")],
    [("13b", "13b Additional deductions from Schedule 1-A, line 38")],
    [("14", "14 Add lines 12e, 13a, and 13b")],
    [("15", "15 Subtract line 14 from line 11b. This is your taxable income")],
] + [row for row in _PAGE2 if row[0][0] not in ("27", "32", "34", "37")] + [
    [("27a", "27a Earned income credit (EIC)")],
    [("30", "30 Refundable credit")],
    [("32", "32 Add lines 27a, 28, 29, 30, and 31. These are your total other payments and refundable credits")],
    [("34", "34 If line 33 is more than line 24, subtract line 24 from line 33. This is the amount you overpaid")],
    [("37", "37 Subtract line 33 from line 24. This is the amount you owe")],
    [("38", "38 Estimated tax penalty (see instructions)")],
]
_BLANK_IF_ZERO_2025 = _BLANK_IF_ZERO | {"7a", "13b", "27a", "30", "38"}


def make_values_2025(pen=0, **over):
    v = make_values(**over)
    v["7a"], v["11a"], v["12e"], v["13a"], v["27a"] = (v.pop(k) for k in ("7", "11", "12", "13", "27"))
    v["11b"] = v["11a"]
    v["13b"] = None
    v["30"] = None
    v["38"] = pen or None
    v["37"] = max(0, v["24"] - v["33"]) + pen
    v["32"] = (v["27a"] or 0) + (v["28"] or 0)
    v.update(over.get("raw", {}))
    return {k: (None if (x == 0 and k in _BLANK_IF_ZERO_2025) else x) for k, x in v.items()}


def write_1040_2025(path, values):
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((20, 120), "FORM", fontsize=12, rotate=90)
    p1.insert_text((36, 780), "For Disclosure, Privacy Act, see instructions.   1040   (2025)", fontsize=7)
    _draw_rows(p1, _PAGE1_2025, values)
    p2 = doc.new_page()
    p2.insert_text((36, 30), "Form 1040 (2025)   Page 2", fontsize=9)
    _draw_rows(p2, _PAGE2_2025, values, dy=13)
    doc.save(path)


class _TmpMixin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def pdf(self, name, **kw):
        path = self.dir / name
        write_1040(path, make_values(**kw.pop("vals", {})), **kw)
        return path


class ParseTests(_TmpMixin):
    def test_reads_values_blanks_and_year(self):
        ret = drake.parse_drake(self.pdf("base.pdf"))
        self.assertEqual(ret.tax_year, 2024)
        self.assertEqual(ret.form_pages, [1, 2])
        self.assertEqual(ret.value("1a"), 100_000)
        self.assertEqual(ret.value("11"), 100_000)
        self.assertEqual(ret.lines["7"].state, "blank")
        self.assertEqual(ret.value("7"), 0.0)
        self.assertTrue(all(lv.method == "marker" for lv in ret.lines.values() if lv.state == "value"))
        self.assertEqual(ret.count("not_found") + ret.count("ambiguous"), 0)

    def test_two_boxes_on_one_row_are_not_confused(self):
        ret = drake.parse_drake(self.pdf("row.pdf", vals=dict(exempt=600, interest=1_500)))
        self.assertEqual(ret.value("2a"), 600)
        self.assertEqual(ret.value("2b"), 1_500)

    def test_cross_reference_in_label_is_not_a_marker(self):
        # Line 8's label ends "Schedule 1, line 10"; its own amount is 3,000 and line 10 is blank.
        ret = drake.parse_drake(self.pdf("xref.pdf", vals=dict(sch1=3_000, adj=0)))
        self.assertEqual(ret.value("8"), 3_000)
        self.assertEqual(ret.lines["10"].state, "blank")
        self.assertEqual(ret.value("10"), 0.0)

    def test_non_1040_pages_are_ignored(self):
        ret = drake.parse_drake(self.pdf("decoy.pdf"))
        self.assertEqual(ret.form_pages, [1, 2])
        self.assertNotEqual(ret.value("9"), 999_999)
        self.assertNotEqual(ret.value("11"), 888_888)
        self.assertNotEqual(ret.value("24"), 777_777)

    def test_negative_amount_in_parentheses(self):
        ret = drake.parse_drake(self.pdf("neg.pdf", vals=dict(cap=-2_000)))
        self.assertEqual(ret.value("7"), -2_000)

    def test_conflicting_amounts_are_ambiguous_not_guessed(self):
        path = self.dir / "amb.pdf"
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((36, 30), "Form 1040 (2024)", fontsize=9)
        p.insert_text((36, 60), "Adjusted gross income . . . . 11 50,000", fontsize=7)
        p.insert_text((36, 80), "Adjusted gross income . . . . 11 60,000", fontsize=7)
        doc.save(path)
        ret = drake.parse_drake(path)
        self.assertEqual(ret.lines["11"].state, "ambiguous")
        self.assertIsNone(ret.value("11"))

    def test_older_label_layout_falls_back_to_label_line(self):
        path = self.dir / "simple.pdf"
        make_test_docs.make_drake_return(path)
        ret = drake.parse_drake(path)
        self.assertEqual(ret.lines["1z"].method, "label-line")
        self.assertEqual((ret.value("1z"), ret.value("2a"), ret.value("2b"), ret.value("3b")),
                         (75_000, 600, 1_500, 800))
        self.assertTrue(any("tax year unknown" in w for w in ret.warnings))

    def test_unopenable_and_textless_files_raise(self):
        bad = self.dir / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        with self.assertRaises(drake.DrakeParseError):
            drake.parse_drake(bad)
        blank = self.dir / "blank.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(blank)
        with self.assertRaises(drake.DrakeParseError):
            drake.parse_drake(blank)

    def test_year_without_a_line_map_warns_and_uses_the_latest(self):
        ret = drake.parse_drake(self.pdf("y2023.pdf", year=2023))
        self.assertEqual(ret.tax_year, 2023)
        self.assertEqual(ret.map_year, max(drake.LINE_MAP_YEARS))
        self.assertTrue(any(f"TY{ret.map_year}" in w for w in ret.warnings))

    def test_year_with_a_line_map_does_not_warn(self):
        self.assertEqual(drake.parse_drake(self.pdf("y2024.pdf")).warnings, [])


class LayoutTests(_TmpMixin):
    """Things seen on a real TY2025 Drake print."""

    def test_page_heading_with_rotated_FORM_is_a_1040_page(self):
        path = self.dir / "vertical.pdf"
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((20, 120), "FORM", fontsize=12, rotate=90)          # no row starts "Form 1040"
        p1.insert_text((300, 40), "Department of the Treasury - Internal Revenue Service", fontsize=8)
        p1.insert_text((36, 60), "Total income . . . . 9 50,000", fontsize=7)
        p1.insert_text((36, 780), "For Disclosure, Privacy Act, see instructions.   1040   (2025)", fontsize=7)
        p2 = doc.new_page()
        p2.insert_text((36, 60), "Schedule 1 (Form 1040) attachment", fontsize=8)
        p2.insert_text((36, 80), "Total income . . . . 9 11,111", fontsize=7)
        doc.save(path)
        ret = drake.parse_drake(path)
        self.assertEqual(ret.form_pages, [1])
        self.assertEqual(ret.value("9"), 50_000)

    def test_horizontal_form_word_alone_does_not_make_a_1040_page(self):
        path = self.dir / "notheading.pdf"
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((20, 60), "FORM", fontsize=12)                          # upright, not the rotated heading
        p.insert_text((36, 780), "1040", fontsize=7)
        doc.save(path)
        self.assertEqual(drake.parse_drake(path).form_pages, [])

    def test_empty_box_without_dot_leaders_is_blank(self):
        path = self.dir / "noleader.pdf"
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((36, 30), "Form 1040 (2025)", fontsize=9)
        p.insert_text((36, 60), "Adjustments to income from Schedule 1, line 26", fontsize=7)
        p.insert_text((440, 60), "10", fontsize=7)                           # marker, nothing after it
        p.insert_text((36, 80), "Tax-exempt interest", fontsize=7)
        p.insert_text((250, 80), "2a", fontsize=7)                           # empty box, other column follows
        p.insert_text((320, 80), "b Taxable interest", fontsize=7)
        p.insert_text((480, 80), "2b", fontsize=7)
        p.insert_text((505, 80), "1,500", fontsize=7)
        doc.save(path)
        ret = drake.parse_drake(path)
        self.assertEqual(ret.lines["10"].state, "blank")
        self.assertEqual(ret.lines["2a"].state, "blank")
        self.assertEqual(ret.value("2b"), 1_500)

    def test_amount_stays_with_its_marker_when_fonts_differ_in_a_row(self):
        # label 14pt, amount 9pt, marker 7pt on one baseline: their tops differ by more than
        # the row tolerance, their vertical centres do not.
        words = [
            dict(text="Tax", x0=36, top=89.0, bottom=103.0),
            dict(text="16", x0=440, top=94.0, bottom=102.0),
            dict(text="8,000", x0=470, top=91.0, bottom=102.0),
        ]
        self.assertEqual(drake._group_lines(words), [["Tax", "16", "8,000"]])
        far = words + [dict(text="17", x0=440, top=105.0, bottom=113.0)]
        self.assertEqual(len(drake._group_lines(far)), 2)

    def test_ty2025_layout_reads_and_passes_the_self_check(self):
        path = self.dir / "ty2025.pdf"
        write_1040_2025(path, make_values_2025(wh=4_000, pen=50))
        ret = drake.parse_drake(path)
        self.assertEqual((ret.tax_year, ret.map_year, ret.warnings), (2025, 2025, []))
        self.assertEqual(ret.count("not_found") + ret.count("ambiguous"), 0)
        self.assertEqual(ret.value("7a"), 0.0)
        self.assertEqual(ret.value("11a"), 100_000 + 1_500 + 1_000 - 2_500)
        self.assertEqual(ret.value("11b"), ret.value("11a"))
        self.assertEqual(ret.value("38"), 50)
        self.assertEqual(ret.value("37"), ret.value("24") - ret.value("33") + 50)
        res = drake.verify_arithmetic(ret)
        self.assertEqual(res.status, "PASS", res.reason)

    def test_ty2025_penalty_not_added_into_37_fails_the_self_check(self):
        path = self.dir / "ty2025bad.pdf"
        write_1040_2025(path, make_values_2025(wh=4_000, pen=50, raw={"37": 2_000}))
        res = drake.verify_arithmetic(drake.parse_drake(path))
        self.assertEqual(res.status, "FAIL")
        self.assertIn("34 - 37 = 33 - 24 - 38", res.reason)


class IntegrityTests(_TmpMixin):
    def test_consistent_return_passes(self):
        res = drake.verify_arithmetic(drake.parse_drake(self.pdf("ok.pdf")))
        self.assertEqual(res.status, "PASS", res.reason)

    def test_tampered_line_fails(self):
        path = self.dir / "tamper.pdf"
        write_1040(path, make_values(raw={"11": 90_000}))
        res = drake.verify_arithmetic(drake.parse_drake(path))
        self.assertEqual(res.status, "FAIL")
        self.assertIn("11 = 9 - 10", res.reason)

    def test_sparse_parse_is_insufficient_not_pass(self):
        path = self.dir / "simple2.pdf"
        make_test_docs.make_drake_return(path)
        self.assertEqual(drake.verify_arithmetic(drake.parse_drake(path)).status, "INSUFFICIENT")


class CompareDelegationTests(_TmpMixin):
    def test_compare_reads_new_layout_via_drake(self):
        lines = compare.extract_drake_lines(self.pdf("cmp.pdf", vals=dict(exempt=600, interest=1_500)))
        self.assertEqual(lines, {"wages": 100_000, "federal_withholding_w2": 9_000, "tax_exempt_interest": 600,
                                 "taxable_interest": 1_500, "ordinary_dividends": 1_000})

    def test_compare_still_reads_synthetic_smoke_test_return(self):
        path = self.dir / "smoke.pdf"
        make_test_docs.make_drake_return(path)
        self.assertEqual(compare.extract_drake_lines(path),
                         {"wages": 75_000, "federal_withholding_w2": None,  # the smoke-test return has no line 25a
                          "tax_exempt_interest": 600, "taxable_interest": 1_500, "ordinary_dividends": 800})


class CliMaskingTests(_TmpMixin):
    """`python drake.py` output is meant to be pasted into a chat: no filename, no amounts by default."""

    def run_cli(self, path, *extra):
        import subprocess
        import sys
        return subprocess.run([sys.executable, "-W", "ignore", str(Path(drake.__file__)), str(path), *extra],
                              capture_output=True, text=True, encoding="utf-8")

    def test_output_has_no_filename_and_no_amounts(self):
        path = self.dir / "Jane Q Client 2024 Tax Return.pdf"
        write_1040(path, make_values())
        out = self.run_cli(path).stdout
        self.assertEqual(out.count("Client"), 0)
        self.assertNotIn(".pdf", out)
        for amount in ("100,000", "29,200", "8,000"):
            self.assertNotIn(amount, out)
        self.assertIn("Arithmetic self-check: PASS", out)

    def test_failed_self_check_names_the_identity_but_not_the_amounts(self):
        path = self.dir / "Jane Q Client tampered.pdf"
        write_1040(path, make_values(raw={"11": 90_000}))
        out = self.run_cli(path).stdout
        self.assertIn("FAIL - failed: 11 = 9 - 10", out)
        self.assertNotIn("90,000", out)
        self.assertIn("90,000", self.run_cli(path, "--values").stdout)

    def test_error_message_does_not_echo_the_filename(self):
        path = self.dir / "Jane Q Client broken.pdf"
        path.write_bytes(b"not a pdf")
        proc = self.run_cli(path)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("Client", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
