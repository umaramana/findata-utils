"""Realistic synthetic source documents (16 Nov 2026): the official blank IRS W-2, 1099-INT and 1099-DIV PDFs
(irs.gov/pub/irs-pdf/fw2.pdf, f1099int.pdf, f1099div.pdf) filled with INVENTED values and flattened, so the values
are ordinary page text. Keeps the recipient's pages only (W-2 Copy B, C, 2 with their instruction pages; 1099
Copy B, the instructions and Copy 2) - roughly what a client hands over - so the copy-page handling and the
form's own label text are exercised. Writes one truth JSON per form beside the documents.

The simple make_test_docs.py documents stay as they are: the Contract tests use those.

    curl -sSLO https://www.irs.gov/pub/irs-pdf/fw2.pdf   (and f1099int.pdf, f1099div.pdf) into <blank dir>
    python make_irs_test_docs.py --blank <blank dir> --out test_docs_irs
"""
import argparse
import json
from pathlib import Path

import fitz  # PyMuPDF

SSN = "000-12-3456"  # fake, never issued (area 000)
EMPLOYEE_FIRST, EMPLOYEE_LAST = "Pat Q", "Example"
ADDR = ["100 Test Lane", "Springfield, ST 00000"]

# Each entry: (blank file, pages to keep (1-based), output name, {(x0, y0) of the box on the page: value}, truth).
# Boxes are found by position, because the field names change on every copy (f2_09, f3_09, ...).
W2_BOXES = {
    (153, 48): SSN,                                            # a
    (38, 72): "00-1234567",                                    # b EIN (fake)
    (38, 96): "ACME Widgets Inc\n200 Industrial Way\nSpringfield, ST 00000",  # c
    (38, 168): "A-0001",                                       # d
    (38, 192): EMPLOYEE_FIRST, (174, 192): EMPLOYEE_LAST,      # e
    (38, 206): "\n".join(ADDR),                                # f
    (333, 72): "75000.00",                                     # 1 wages
    (456, 72): "9850.00",                                      # 2 federal withheld
    (332, 96): "78000.00",                                     # 3 social security wages
    (455, 96): "4836.00",                                      # 4 social security tax
    (332, 120): "78000.00",                                    # 5 Medicare wages
    (455, 120): "1131.00",                                     # 6 Medicare tax
    (463, 192): "D", (491, 192): "3000.00",                    # 12a
    (38, 300): "NC", (66, 300): "000000-0",                    # 15
    (195, 300): "75000.00",                                    # 16 state wages
    (282, 300): "3100.00",                                     # 17 state income tax
}
INT_BOXES = {
    (52, 56): "ACME Savings Bank\n300 Main St\nSpringfield, ST 00000\n(000) 555-0100",
    (52, 142): "00-7654321", (174, 142): SSN,
    (52, 190): f"{EMPLOYEE_FIRST} {EMPLOYEE_LAST}", (52, 226): ADDR[0], (52, 262): ADDR[1],
    (52, 334): "ACCT-0001",
    (302, 96): "1,234.56",    # 1 interest income
    (302, 168): "300.00",     # 3 US savings bonds / Treasury interest
    (302, 192): "150.00",     # 4 federal withheld
    (302, 216): "25.00",      # 6 foreign tax paid
    (302, 252): "500.00",     # 8 tax-exempt interest
}
DIV_BOXES = {
    (52, 56): "ACME Brokerage LLC\n400 Market St\nSpringfield, ST 00000\n(000) 555-0200",
    (50, 142): "00-2345678", (173, 142): SSN,
    (52, 190): f"{EMPLOYEE_FIRST} {EMPLOYEE_LAST}", (52, 226): ADDR[0], (52, 262): ADDR[1],
    (50, 334): "ACCT-0002",
    (305, 60): "2,345.67",    # 1a ordinary dividends
    (305, 96): "1,800.00",    # 1b qualified dividends
    (305, 120): "410.00",     # 2a capital gain distributions
    (406, 192): "50.00",      # 4 federal withheld
    (305, 312): "100.00",     # 12 exempt-interest dividends
}
DOCS = [
    ("fw2.pdf", [4, 5, 6, 7, 8, 9], "acme_w2.pdf", W2_BOXES,
     {"__form_type__": "W-2", "box_1_wages": "75000.00", "box_2_federal_withheld": "9850.00"}),
    ("f1099int.pdf", [4, 5, 6, 7], "acme_1099-int.pdf", INT_BOXES,
     {"__form_type__": "1099-INT", "box_1_interest_income": "1234.56",
      "box_3_us_savings_bonds_treasury_interest": "300.00", "box_4_federal_withheld": "150.00",
      "box_8_tax_exempt_interest": "500.00"}),
    ("f1099div.pdf", [4, 5, 6], "acme_1099-div.pdf", DIV_BOXES,
     {"__form_type__": "1099-DIV", "box_1a_ordinary_dividends": "2345.67", "box_1b_qualified_dividends": "1800.00",
      "box_4_federal_withheld": "50.00", "box_12_exempt_interest_dividends": "100.00"}),
]


def fill(blank: Path, keep: list, boxes: dict, out: Path) -> None:
    doc = fitz.open(blank)
    doc.select([p - 1 for p in keep])
    for page in doc:
        for w in page.widgets():
            if w.field_type != fitz.PDF_WIDGET_TYPE_TEXT:
                continue
            value = next((v for (x, y), v in boxes.items()
                          if abs(w.rect.x0 - x) < 3 and abs(w.rect.y0 - y) < 3), None)
            if value is not None:
                w.field_value = value
                w.update()
    doc.bake()  # flatten: widget appearances become page content, the form fields go away
    doc.save(out, garbage=3, deflate=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blank", required=True, help="Folder holding the blank IRS PDFs")
    ap.add_argument("--out", default="test_docs_irs")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for blank, keep, name, boxes, truth in DOCS:
        fill(Path(args.blank) / blank, keep, boxes, out / name)
        (out / f"truth_{Path(name).stem}.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
        print(f"wrote {out / name}")


if __name__ == "__main__":
    main()
