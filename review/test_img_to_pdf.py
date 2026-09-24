"""Tests for img_to_pdf.py - synthetic images only.

    python -m unittest test_img_to_pdf -v
"""
import io
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image

import img_to_pdf
import redact
import redactor.redact_ocr as redact_ocr

LINES = ["Form W-2 Wage and Tax Statement 2025", "Employee: John Smith   SSN 123-45-6789",
         "Employer identification number 246813579  Acme Widgets Incorporated",
         "Box 1 Wages 85000.00   Box 2 Federal tax withheld 12000.00"]


def upright_image():
    page = fitz.open().new_page()
    for k, line in enumerate(LINES):
        page.insert_text((72, 100 + 30 * k), line, fontsize=13)
    return Image.open(io.BytesIO(page.get_pixmap(dpi=200).tobytes("png"))).convert("RGB")


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src, self.out = self.root / "img", self.root / "pdf"
        self.src.mkdir()
        upright_image().save(self.src / "plain.jpg", quality=95)
        # a phone photo: pixels stored sideways, EXIF says "rotate 270 to display" (orientation 6)
        sideways = upright_image().transpose(Image.ROTATE_90)
        exif = sideways.getexif()
        exif[274] = 6
        exif[271] = "PhoneMaker"  # a make tag: must not survive into the PDF
        sideways.save(self.src / "phone.JPEG", quality=95, exif=exif)

    def tearDown(self):
        self._tmp.cleanup()

    def convert(self, name):
        dst = self.out / (Path(name).stem + ".pdf")
        self.out.mkdir(exist_ok=True)
        return dst, img_to_pdf.image_to_pdf(self.src / name, dst)

    def test_one_image_only_page_no_metadata(self):
        dst, (w, h, rotated) = self.convert("plain.jpg")
        self.assertFalse(rotated)
        with fitz.open(dst) as doc:
            self.assertEqual(len(doc), 1)
            self.assertEqual(doc[0].get_text().strip(), "")
            self.assertEqual(len(doc[0].get_images()), 1)
            self.assertNotIn("PhoneMaker", doc.xref_object(doc[0].get_images()[0][0]) + str(doc.metadata))

    def test_exif_rotation_applied(self):
        dst, (w, h, rotated) = self.convert("phone.JPEG")
        self.assertTrue(rotated)
        self.assertLess(w, h)  # the upright page is portrait; the stored (sideways) pixels are landscape

    def test_original_untouched(self):
        before = (self.src / "phone.JPEG").read_bytes()
        self.convert("phone.JPEG")
        self.assertEqual((self.src / "phone.JPEG").read_bytes(), before)

    @unittest.skipUnless(redact_ocr.available(), "tesseract not installed")
    def test_phone_photo_goes_through_ocr_redaction(self):
        self.convert("phone.JPEG")
        res = redact.redact_tree(self.out, self.root / "red", default_names=["John Smith"], ocr=True)
        self.assertEqual([(r.status, r.ocr_pages) for r in res], [("OK", [1])])
        self.assertTrue({"SSN", "ID9", "John Smith"} <= set(res[0].counts))
        with fitz.open(res[0].redacted_path) as doc:
            seen = " ".join(w["text"] for w in redact_ocr.read_words(doc[0]))
        for gone in ("Smith", "6789", "246813579"):
            self.assertNotIn(gone, seen)
        self.assertIn("Acme", seen)


if __name__ == "__main__":
    unittest.main()
