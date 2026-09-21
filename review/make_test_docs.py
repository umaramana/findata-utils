"""Generates synthetic W-2 / 1099-INT / 1099-DIV / 1098 source documents plus a
matching Drake-style return PDF, all with fake data, for exercising run.py
end-to-end without any real client documents.

1098 is out of v1 scope (SPEC.md §1/§10) - extract.py no longer recognizes
it, so it's kept here as a regression case: a doc extract.py can't classify
should come back UNKNOWN, not be silently forced into one of the three
in-scope form types.

    python make_test_docs.py --out ./test_docs

Writes 4 source docs to --out, and a return.pdf beside it (--out's parent) -
run with:

    python make_test_docs.py --out ./test_docs
    python run.py --docs ./test_docs --drake ./return.pdf --mode api
"""
import argparse
from pathlib import Path

import fitz  # PyMuPDF

SSN = "123-45-6789"
NAME = "John Q Taxpayer"


def _page(doc, lines, y0=100, dy=20):
    p = doc.new_page()
    for i, line in enumerate(lines):
        p.insert_text((72, y0 + i * dy), line, fontsize=11)
    return p


def make_w2(path):
    doc = fitz.open()
    _page(doc, [
        "Form W-2 Wage and Tax Statement",
        f"Employee SSN: {SSN}",
        f"Employee name: {NAME}",
        "Employer: Acme Corp",
        "Box 1  Wages, tips, other compensation:  75,000.00",
        "Box 2  Federal income tax withheld:      12,000.00",
    ])
    doc.save(path)


def make_1099int(path):
    doc = fitz.open()
    _page(doc, [
        "Form 1099-INT Interest Income",
        f"Recipient SSN: {SSN}",
        f"Recipient name: {NAME}",
        "Payer: First National Bank",
        "Box 1  Interest income:                          1,200.00",
        "Box 3  Interest on US Savings Bonds/Treasury:       300.00",
        "Box 4  Federal income tax withheld:                 150.00",
        "Box 6  Foreign tax paid:                             25.00",
        "Box 8  Tax-exempt interest:                         500.00",
    ])
    doc.save(path)


def make_1099div(path):
    doc = fitz.open()
    _page(doc, [
        "Form 1099-DIV Dividends and Distributions",
        f"Recipient SSN: {SSN}",
        f"Recipient name: {NAME}",
        "Payer: Big Brokerage LLC",
        "Box 1a Total ordinary dividends:      800.00",
        "Box 1b Qualified dividends:           800.00",
        "Box 4  Federal income tax withheld:    50.00",
        "Box 9  Cash liquidation distributions: 10.00",
        "Box 12 Exempt-interest dividends:     100.00",
    ])
    doc.save(path)


def make_1098(path):
    doc = fitz.open()
    _page(doc, [
        "Form 1098 Mortgage Interest Statement",
        f"Payer/Borrower SSN: {SSN}",
        f"Payer/Borrower name: {NAME}",
        "Lender: Home Mortgage Co",
        "Box 1  Mortgage interest received:  12,000.00",
    ])
    doc.save(path)


def make_drake_return(path):
    doc = fitz.open()
    _page(doc, [
        "Form 1040 U.S. Individual Income Tax Return",
        f"Taxpayer: {NAME}   SSN {SSN}",
        "1z  Wages, salaries, tips, etc. Attach Form(s) W-2 ....... 75,000.00",
        "2a  Tax-exempt interest .......... 600.00",
        "2b  Taxable interest .............. 1,500.00",
        "3a  Qualified dividends ........... 800.00",
        "3b  Ordinary dividends ............ 800.00",
    ], dy=22)
    _page(doc, [
        "Schedule A - Itemized Deductions",
        "8a  Home mortgage interest and points reported on Form 1098 .... 12,000.00",
    ])
    doc.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="./test_docs", help="Folder for the 4 source documents")
    ap.add_argument("--drake-out", default=None, help="Path for the Drake return PDF (default: <out>/../return.pdf)")
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    make_w2(out_dir / "employer_a_w2.pdf")
    make_1099int(out_dir / "bank_a_1099int.pdf")
    make_1099div(out_dir / "broker_a_1099div.pdf")
    make_1098(out_dir / "mortgage_a_1098.pdf")

    drake_path = Path(args.drake_out).resolve() if args.drake_out else out_dir.parent / "return.pdf"
    make_drake_return(drake_path)

    print(f"Wrote 4 source docs to {out_dir}")
    print(f"Wrote Drake return to {drake_path}")
    print(f"\nTry:\n  python run.py --docs {out_dir} --drake {drake_path} --mode api")


if __name__ == "__main__":
    main()
