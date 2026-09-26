"""Tests for harvest.py on synthetic Drake-style returns (no real return is ever used).

    python -m unittest test_harvest -v

A synthetic 1040 is drawn the way Drake prints one: the form's labels first, then the typed values as a separate
layer, so in the text stream the values come after every label. It also carries the quirks seen (masked) on a real
Drake print, 25 Sep: form wording that carries on beside the ZIP on the same line, the email one line under the
spouse's occupation, empty comb boxes drawn as letter glyphs, and a 9pt section heading under the foreign row. Layouts are shifted, rescaled and given different
label-to-value gaps to show that nothing depends on fixed coordinates.
"""
import tempfile
import unittest
from pathlib import Path

import fitz

import harvest
import redact

JOINT = {
    "tp_first": "JOHN A", "tp_last": "SMITH", "tp_ssn": "400-11-2222",
    "sp_first": "JANE B", "sp_last": "SMITH", "sp_ssn": "400-33-4444",
    "street": "4471 QUINCE HOLLOW LANE", "apt": "3B", "city": "HOLLY SPRINGS", "state": "NC", "zip": "27540",
    "tp_occupation": "SOFTWARE ENGINEER", "sp_occupation": "RETIRED",
    "phone": "919-555-0123", "routing": "061000104", "account": "8642013579", "email": "jsmith@example.com",
}


def make_return(path, values, dx=0, dy=0, scale=1.0, gap=4, extra_pages=()):
    """A 2-page 1040 look-alike. gap: points between a label's bottom and its value's top."""
    doc = fitz.open()
    lf, vf = 6 * scale, 9 * scale
    X = lambda x: dx + x * scale
    Y = lambda y: dy + y * scale
    # (label, x, y, value key, where): "below" values sit under the label, "right" values after it
    p1 = [("Your first name and middle initial", 36, 100, "tp_first", "below"),
          ("Last name", 250, 100, "tp_last", "below"),
          ("Your social security number", 470, 100, "tp_ssn", "below"),
          ("If joint return, spouse's first name and middle initial", 36, 124, "sp_first", "below"),
          ("Last name", 250, 124, "sp_last", "below"),
          ("Spouse's social security number", 470, 124, "sp_ssn", "below"),
          ("Home address (number and street). If you have a P.O. box, see instructions.", 36, 148, "street", "below"),
          ("Apt. no.", 420, 148, "apt", "below"),
          ("City, town, or post office. If you have a foreign address, also complete spaces below.", 36, 172,
           "city", "below"),
          ("State", 330, 172, "state", "below"),
          ("ZIP code", 390, 172, "zip", "below"),
          ("Foreign country name", 36, 196, "country", "below"),
          ("Foreign province/state/county", 200, 196, "province", "below"),
          ("Foreign postal code", 360, 196, "postal", "below"),
          ("Presidential Election Campaign", 470, 148, None, None),   # on the Apt. row, as on the real print
          ("Check here if you, or your", 470, 161, None, None),        # its wording runs on beside the ZIP value
          ("spouse if filing jointly, want $3", 470, 185, None, None),
          ("Filing Status", 36, 222, None, None)]
    p2 = [("b Routing number", 36, 300, "routing", "right"),
          ("c Type: Checking Savings", 330, 300, None, None),
          ("d Account number", 36, 316, "account", "right"),
          ("Your signature", 36, 500, None, None), ("Date", 250, 500, None, None),
          ("Your occupation", 320, 500, "tp_occupation", "below"),
          ("If the IRS sent you an Identity Protection PIN, enter it here", 440, 500, None, None),
          ("Spouse's signature. If a joint return, both must sign.", 36, 524, None, None),
          ("Date", 250, 524, None, None),
          ("Spouse's occupation", 320, 524, "sp_occupation", "below"),
          ("If the IRS sent your spouse an Identity Protection PIN, enter it here", 440, 524, None, None),
          ("Phone no.", 36, 548, "phone", "right"), ("Email address", 250, 548, "email", "right")]
    for spec in (p1, p2):
        page = doc.new_page(width=612 * scale + 2 * dx, height=792 * scale + 2 * dy)
        for text, x, y, key, where in spec:               # the printed form
            page.insert_text((X(x), Y(y)), text, fontsize=vf if text == "Filing Status" else lf, fontname="helv")
            if key in ("routing", "account"):             # empty comb boxes, drawn as a letter glyph each
                x0 = X(x) + fitz.get_text_length(text, "helv", lf) + 10
                for n in range(17 if key == "account" else 9):
                    page.insert_text((x0 + n * 12 * scale, Y(y)), "o", fontsize=vf, fontname="cour")
        for text, x, y, key, where in spec:               # the typed values, a layer of their own
            if not key or not values.get(key):
                continue
            v = values[key]
            if where == "below":
                page.insert_text((X(x + 2), Y(y) + gap + vf), v, fontsize=vf, fontname="cour")
            elif key in ("routing", "account"):           # comb boxes: one digit per box
                x0 = X(x) + fitz.get_text_length(text, "helv", lf) + 10
                for n, ch in enumerate(v):
                    page.insert_text((x0 + n * 12 * scale, Y(y)), ch, fontsize=vf, fontname="cour")
            else:
                x0 = X(x) + fitz.get_text_length(text, "helv", lf) + 8
                page.insert_text((x0, Y(y)), v, fontsize=vf, fontname="cour")
    for text in extra_pages:
        doc.new_page().insert_text((50, 100), text, fontsize=9)
    doc.save(path)
    doc.close()


class HarvestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _harvest(self, values, **kw):
        pdf = self.dir / "ret.pdf"
        make_return(pdf, values, **kw)
        return harvest.harvest(pdf)

    def _expect(self, h, values):
        want = dict(values)
        want["phone"] = "9195550123"
        want.pop("email", None)   # the EMAIL rule covers any address; harvest does not read it
        for key, v in want.items():
            self.assertEqual(h.values.get(key), [v], key)

    def test_joint_return(self):
        self._expect(self._harvest(JOINT), JOINT)

    def test_layout_shifted_rescaled_other_gaps(self):
        for kw in ({"dx": 30, "dy": -20}, {"scale": 1.25}, {"scale": 0.85, "gap": 1}, {"gap": 9, "dx": -10}):
            with self.subTest(**kw):
                self._expect(self._harvest(JOINT, **kw), JOINT)

    def test_single_filer_has_no_spouse(self):
        single = {k: v for k, v in JOINT.items() if not k.startswith("sp_")}
        h = self._harvest(single)
        self._expect(h, single)
        self.assertFalse(any(k.startswith("sp_") for k in h.values))
        self.assertNotIn("JANE B SMITH", h.entries())

    def test_entries(self):
        e = self._harvest(JOINT).entries()
        for want in ("JOHN A SMITH", "JANE B SMITH", "400-11-2222", "400-33-4444", "SOFTWARE ENGINEER",
                     "4471 QUINCE HOLLOW LANE", "4471 QUINCE HOLLOW LANE; HOLLY SPRINGS; NC 27540",
                     "9195550123", "061000104", "8642013579"):
            self.assertIn(want, e)
        self.assertNotIn("RETIRED", e)   # a generic occupation identifies nobody

    def test_spouse_surname_left_blank(self):
        v = dict(JOINT, sp_last="")
        self.assertIn("JANE B SMITH", self._harvest(v).entries())

    def test_no_direct_deposit(self):
        v = dict(JOINT, routing="", account="")   # empty comb boxes only
        h = self._harvest(v)
        self.assertNotIn("routing", h.values)
        self.assertNotIn("account", h.values)

    def test_us_address_ignores_heading_below_foreign_row(self):
        h = self._harvest(JOINT)
        self.assertFalse(any("Filing" in e for e in h.entries()))
        self.assertNotIn("country", h.values)

    def test_value_starting_past_a_short_label(self):
        # real print: the State value starts a little right of where the word "State" ends
        pdf = self.dir / "st.pdf"
        doc = fitz.open()
        page = doc.new_page()
        for text, x in (("City, town, or post office", 36), ("State", 330), ("ZIP code", 390)):
            page.insert_text((x, 172), text, fontsize=6, fontname="helv")
        for text, x in (("HOLLY SPRINGS", 38), ("NC", 348), ("27540", 392)):
            page.insert_text((x, 185), text, fontsize=9, fontname="cour")
        doc.save(pdf)
        doc.close()
        h = harvest.harvest(pdf)
        self.assertEqual((h.values.get("state"), h.values.get("zip")), (["NC"], ["27540"]))

    def test_foreign_address(self):
        v = dict(JOINT, city="LONDON", state="", zip="", country="UNITED KINGDOM", province="GREATER LONDON",
                 postal="SW1A 1AA")
        h = self._harvest(v)
        for key in ("country", "province", "postal"):
            self.assertEqual(h.values.get(key), [v[key]], key)
        self.assertIn("SW1A 1AA", h.entries())

    def test_not_a_return(self):
        pdf = self.dir / "other.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((50, 100), "Form 1099-INT Interest Income  Payer's name  Account number "
                                   "(see instructions)  1 Interest income 1,234.56", fontsize=9)
        doc.save(pdf)
        doc.close()
        h = harvest.harvest(pdf)
        self.assertEqual(h.entries(), [])

    def test_label_followed_by_wording_is_not_a_value(self):
        # "Account number (see instructions)" on some other form: the words after it are not a number
        h = self._harvest({}, extra_pages=["Account number or other designation 2024 Form 8938 Part V"])
        self.assertEqual(h.entries(), [])

    def test_harvested_values_redact_a_source_document(self):
        """End to end: harvest -> build_patterns -> redact a 1099-style page that writes the same client the
        way a bank does (title case, surname first, abbreviated street, masked account)."""
        entries = self._harvest(JOINT).entries()
        src, dst = self.dir / "1099.pdf", self.dir / "1099_red.pdf"
        doc = fitz.open()
        page = doc.new_page()
        lines = ["RECIPIENT'S name: Smith, John A", "Jane Smith", "4471 Quince Hollow Ln, Holly Springs, NC 27540",
                 "Account number 8642013579   Recipient's TIN ***-**-2222", "Phone (919) 555-0123",
                 "1 Interest income 1,234.56"]
        for n, t in enumerate(lines):
            page.insert_text((50, 100 + 16 * n), t, fontsize=9)
        doc.save(src)
        doc.close()
        redact.redact_file(src, dst, redact.build_patterns(entries))
        with fitz.open(dst) as d:
            text = d[0].get_text()
        for gone in ("Smith", "John", "Jane", "4471", "Holly Springs", "27540", "8642013", "2222", "555-0123"):
            self.assertNotIn(gone, text, gone)
        self.assertIn("1,234.56", text)   # the amount check 4 needs survives


if __name__ == "__main__":
    unittest.main()
