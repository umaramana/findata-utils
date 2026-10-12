"""Tests for pdf_text (synthetic PDFs built on the fly). Run: ~/.cache/checkocr_venv/bin/python test_pdf_text.py"""
import os
import shutil
import tempfile
import unittest

import pymupdf

import pdf_text as P

TEXT = 'ACME CHECKING January 14, 2026 through February 10, 2026\nDEPOSITS & CREDITS\n01/15 Deposit ACME Store 7 1,000.00\n'


def _pdf(path, texts, as_image=False):
    doc = pymupdf.open()
    for t in texts:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 560, 400), t, fontsize=12)
    if as_image:   # re-render to an image-only PDF (no text layer)
        img = pymupdf.open()
        for p in doc:
            pix = p.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            ip = img.new_page(width=p.rect.width, height=p.rect.height)
            ip.insert_image(ip.rect, pixmap=pix)
        doc = img
    doc.save(path)


class PdfText(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_text_layer_used(self):
        f = os.path.join(self.d, 't.pdf')
        _pdf(f, [TEXT, TEXT])
        pages, mode = P.file_pages(f)
        self.assertEqual(mode, 'text')
        self.assertEqual(len(pages), 2)
        self.assertIn('Deposit ACME Store 7', pages[0])

    @unittest.skipUnless(shutil.which('tesseract'), 'tesseract not installed')
    def test_image_pdf_goes_to_ocr(self):
        f = os.path.join(self.d, 'i.pdf')
        _pdf(f, [TEXT], as_image=True)
        pages, mode = P.file_pages(f)
        self.assertEqual(mode, 'ocr')
        self.assertIn('1,000.00', pages[0])

    def test_unsupported_type(self):
        with self.assertRaises(ValueError):
            P.file_pages(os.path.join(self.d, 'x.docx'))

    def test_env_var_overrides_tesseract_path(self):
        class Fake:
            class pytesseract:
                tesseract_cmd = 'tesseract'
        os.environ['TESSERACT_CMD'] = '/opt/x/tesseract'
        try:
            P.configure_tesseract(Fake)
        finally:
            del os.environ['TESSERACT_CMD']
        self.assertEqual(Fake.pytesseract.tesseract_cmd, '/opt/x/tesseract')


if __name__ == '__main__':
    unittest.main()
