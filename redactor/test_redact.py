"""Synthetic edge-case matrix for redact.py — no client data.

Builds PDFs in a temp folder, runs redact.py as the CLI, then checks each
output: sensitive text gone (true positives), look-alikes kept (false
positives), expected status per file, exit codes, and the same-folder guard.

    python test_redact.py
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz

HERE = Path(__file__).parent
# A DOB, a phone number and an account number entered alongside the names are matched in every written form.
NAMES = "John Smith, Jane Doe, 03/04/1980, 212 555 0199, 7788 9900 1122"
INDIA_ENTRY = "Flat 4B; Sai Apts.; M.G. Road; Kothrud - 411038"  # passed separately: commas split --names
SSNS = "123-45-6789, 987-65-4321"

# Must NOT appear in any output text layer.
FORBIDDEN = {
    "SSN#1 any format": re.compile(r"(?<!\d)123[\s-]*45[\s-]*6789(?!\d)"),
    "SSN#1 masked": re.compile(r"[Xx*]{3}[\s-]*[Xx*]{2}[\s-]*6789"),
    "SSN#2": re.compile(r"987-65-4321"),
    "other SSN": re.compile(r"222-33-4444"),
    "John Smith": re.compile(r"john\s+smith", re.I),
    "Jane Doe": re.compile(r"jane\s+do-?\s*e\b", re.I),
    # other written forms of the same two people (name_variant_patterns)
    "Smith, John": re.compile(r"smith,\s*john", re.I),
    "SMITH JOHN": re.compile(r"smith\s+john\b", re.I),
    "J. Smith": re.compile(r"\bj\.\s*smith", re.I),
    "John Q. Smith": re.compile(r"john\s+q\.?\s+smith", re.I),
    "Doe, Jane": re.compile(r"doe,\s*jane", re.I),
    "undashed 9-digit": re.compile(r"(?<![\d.,$-])\d{9}(?!\d)(?![.,]\d)"),
    "US phone": re.compile(r"(?:\(\d{3}\)\s?|(?<![\d-])\d{3}-)\d{3}-\d{4}(?![\d-])"),
    "email": re.compile(r"@"),
    "labelled DOB": re.compile(r"07/22/1975|1975-07-22|7/22/75|Jan 5, 1990"),
    "entered DOB": re.compile(r"03/04/1980|3/4/80|04/03/1980|1980-03-04|Mar 4, 1980|March 4th, 1980|4-Mar-1980|3\.4\.80"),
    "entered phone": re.compile(r"2125550199|212\.555\.0199|212 555 0199"),
    "PAN": re.compile(r"ABCPE1234F|XYZHK9876Q"),
    "Aadhaar": re.compile(r"2345[ -]?6789[ -]?0123"),
    "CA employer ID": re.compile(r"123-4567-8"),
    # account numbers: nothing before the last 4 may survive
    "account number": re.compile(r"12345678901234|5566778899001|1234-5678|44332211|55443\b|12 3456789|778-?899-?00"),
    "India address": re.compile(r"Sai Apts MG|SAI APTS, M G|Kothrud|KOTHRUD|Lake View|Koramangala|Bengaluru|"
                                r"Anna Nagar|600 040|Kalyani|411006|Nandi|562103|560034|4B"),
    "layout address": re.compile(r"Shivaji|Kasturba|Nasik|Maharashtr|422001|Sai Ganga|Lakshmi|Tilak|422002|"
                                 r"Ring Road|Hubli|580020|48210|Quail|Escondido|92027"),
    "variation address": re.compile(r"Lodha|Xperia|Dombivli|421204|Ram Mandir|Sangli|416416|GANDHI|BELGAUM|590016|"
                                    r"Panchkula|134109|Shirur|412210|Sai Kripa|440010|Banyan|Tamarind|Shivaji|"
                                    r"Kasturba|MIDC|SAN JOSE|95131|HARBOR"),
    "US address": re.compile(r"Main St|MAPLE AVENUE|Box 4411|San Diego|92121|SPRINGFIELD"),
}
XMP = ("<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
       "<rdf:Description xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:creator>John Smith</dc:creator>"
       "<dc:title>Jane Doe return</dc:title></rdf:Description></rdf:RDF></x:xmpmeta>")
# Source filenames that carry a client name; the redacted copies must not.
NAMED_FILES = ["W2 - John Smith.pdf", "W2 - John_Smith.pdf", "1099_Jane_Doe.pdf", "JohnSmith 1040.pdf"]
EXPECTED_OUT_NAMES = {"W2 - REDACTED.pdf", "W2 - REDACTED_2.pdf", "1099_REDACTED.pdf", "REDACTED 1040.pdf"}
BASE_KEEP = ["Phone", "1234-56-7890", "123-45-67890"]
SPLIT_KEEP = ["John Adams", "Mary Smith", "Jane Doeman"]


def base_page(p):
    p.insert_text((72, 100), "Taxpayer: John Smith  SSN 123-45-6789")
    p.insert_text((72, 130), "Spouse: jane   doe  SSN: 987-65-4321  Dep: 222-33-4444")
    p.insert_text((72, 160), "Phone 555-123-4567  Code 1234-56-7890  Ref 123-45-67890")


def split_page(p):
    p.insert_text((72, 100), "The return was signed by taxpayer John")   # name across line break
    p.insert_text((72, 115), "Smith on April 10.")
    p.insert_text((72, 145), "Spouse name: Jane Do-")                      # hyphenated across lines
    p.insert_text((72, 160), "e, filing jointly.")
    p.insert_text((72, 190), "SSN on file 123-45-")                         # SSN across lines
    p.insert_text((72, 205), "6789 verified.")
    p.insert_text((72, 300), "Prepared for John")                           # two-column layout
    p.insert_text((72, 315), "Smith, 2025 year.")
    p.insert_text((330, 300), "Right column note")
    p.insert_text((72, 400), "KEEP: John Adams met Mary Smith; Jane Doeman.")


def variants_page(p):
    p.insert_text((72, 100), "Payee: Smith, John   Ref SMITH JOHN A")     # reordered
    p.insert_text((72, 130), "Signed J. Smith and John Q. Smith")          # initial / middle initial
    p.insert_text((72, 160), "Spouse Doe, Jane M.")
    p.insert_text((72, 200), "KEEP: Jane Smith paid Johnny Doe and Roberta")  # different people


def sideways_page(p, rot):
    """Upright page (/Rotate 0) whose text is drawn rotated, e.g. a landscape schedule."""
    x0, step = (100, 15) if rot == 90 else (500, -15)
    y = 700 if rot == 90 else 100
    lines = ["Taxpayer: John Smith  SSN 123-45-6789",
             "Spouse: jane   doe  SSN: 987-65-4321  Dep: 222-33-4444",
             "Phone 555-123-4567  Code 1234-56-7890  Ref 123-45-67890",
             "Signed by taxpayer John",   # name across line break
             "Smith on April 10."]
    for n, line in enumerate(lines):
        p.insert_text((x0 + n * step * 2, y), line, rotate=rot)


def known_ssn_page(p):
    p.insert_text((72, 100), "Unformatted 123456789  Spaced 123 45 6789")
    p.insert_text((72, 130), "Masked XXX-XX-6789  Stars ***-**-6789  Compact XXXXX6789")
    p.insert_text((72, 160), "KEEP: Card ending 6789  Invoice 0123456789  Other XXX-XX-1111")


def contact_page(p):
    p.insert_text((72, 100), "Email: jsmith@example.com  Payer: tax-help@bank-co.org")
    p.insert_text((72, 120), "Phone 555-123-4567  Fax (555) 987-6543  Cell (555)222-3333")
    p.insert_text((72, 140), "Toll-free 1-800-555-0100  Intl +1 555-444-5555")
    p.insert_text((72, 160), "Date of Birth: 07/22/1975  DOB 1975-07-22  D.O.B. Jan 5, 1990")
    p.insert_text((72, 180), "Birth date (MM/DD/YYYY) 7/22/75")
    p.insert_text((72, 200), "Other forms: 3/4/80  04/03/1980  1980-03-04  Mar 4, 1980")
    p.insert_text((72, 220), "More: March 4th, 1980  4-Mar-1980  3.4.80  (03/04/1980)")
    p.insert_text((72, 240), "Entered phone 2125550199 and 212.555.0199")
    p.insert_text((72, 280), "KEEP: Date sold 07/22/2024  Acquired 2023-01-15  Order 5551234567")
    p.insert_text((72, 300), "KEEP: dots 555.123.4567  spaces 555 123 4567  Ref 123-456-78901")
    p.insert_text((72, 320), "KEEP: born before January 2, 1961  ZIP+4 62701-1234  03/14/1980")


def ids_page(p):
    p.insert_text((72, 100), "PAN ABCPE1234F  Karvy ID XYZHK9876Q  Aadhaar 2345 6789 0123  CA ID 123-4567-8")
    p.insert_text((72, 120), "ICICI 5566778899001  Account No. 12345678901234  Schwab Account number: 1234-5678")
    p.insert_text((72, 140), "A/c No: 44332211  Folio No. 55443  EIN 12 3456789  entered 778-899-001122")
    p.insert_text((72, 160), "1234 N Main St Apt 5  55 MAPLE AVENUE  PO Box 4411")
    p.insert_text((72, 180), "San Diego, CA 92121  SPRINGFIELD IL 62701-1234")
    p.insert_text((72, 220), "KEEP: years 2024 2023 2022  Wages 123456.78  grouped 12,345,678,901")
    p.insert_text((72, 240), "KEEP: 1 Wages, tips, other comp.  16 State wages, tips  OMB No. 1545-0074")
    p.insert_text((72, 260), "KEEP: Account number (see instructions) 2 Early withdrawal penalty")
    p.insert_text((72, 280), "KEEP: 15 State Employer's state ID number  PAN card  Tax year 2024")


def india_page(p):
    # entered as "Flat 4B, Sai Apts., M.G. Road, Kothrud - 411038" (INDIA_ENTRY); printed with other punctuation
    p.insert_text((72, 100), "Owner addr: Flat 4B Sai Apts MG Road Kothrud 411 038")
    p.insert_text((72, 120), "Also: FLAT 4B,SAI APTS, M G ROAD,KOTHRUD,411038")
    p.insert_text((72, 140), "Property: 12 Lake View Layout, Koramangala, Bengaluru, Karnataka 560034")
    p.insert_text((72, 160), "Plot 7, Anna Nagar, Chennai 600 040, India   Kalyani Nagar, Pune - 411006")
    p.insert_text((72, 180), "Farm: Survey 22, Nandi Hills, Karnataka, India   Pin Code: 562103")
    p.insert_text((72, 220), "KEEP: Country India  State Karnataka  Punjab National Bank  Amount 560001")
    p.insert_text((72, 240), "KEEP: Self-select PIN 12345  Tax year 2024 India  Sai Apts")


def layout_page(p):
    # Layouts seen in real returns (probe_labels.py): Form 8938 values on the line after their label; a Schedule E
    # India line with ~10 words before PIN + India; the 1040 header's city, state and ZIP on separate lines.
    p.insert_text((72, 98), "Mailing address of financial institution in which account is maintained. Number, street, and room or suite no.")
    p.insert_text((72, 116), "Shivaji Chowk, Kasturba Rd 12")
    p.insert_text((72, 134), "23")
    p.insert_text((72, 152), "City or town, state or province, country, and ZIP or foreign postal code")
    p.insert_text((72, 170), "Nasik, Maharashtr, India 422001")
    p.insert_text((72, 188), "Part VI Detailed Information for Each Other Foreign Asset")
    p.insert_text((72, 206), "Mailing address of foreign entity. Number, street, and room or suite no.")
    p.insert_text((72, 224), "24")
    p.insert_text((72, 242), "City or town, state or province, country, and ZIP or foreign postal code")
    p.insert_text((72, 260), "Form 8938 (Rev. 11-2024)")
    p.insert_text((72, 278), "A 101 Sai Ganga B Wing Lakshmi Nagar Road, Tilak Wadi, Nasik, 422002, India")
    p.insert_text((72, 296), "B 7 Ring Road Near Old Temple Colony, Hubli India 580020")
    p.insert_text((72, 314), "Home address (number and street). If you have a P.O. box, see instructions.")
    p.insert_text((72, 332), "48210 Quail Hollow Glen")
    p.insert_text((72, 350), "Escondido")
    p.insert_text((72, 368), "CA")
    p.insert_text((72, 386), "92027")
    p.insert_text((72, 404), "KEEP: Part VI Detailed Information for Each Other Foreign Asset")
    p.insert_text((72, 422), "KEEP: Form 8938 (Rev. 11-2024)")


def variations_page(p):
    # Address shapes NOT taken from any real file: long / short lines, capitals, no commas, lower-case words,
    # a value on the line below other labels, a street with no house number, empty fields, look-alikes.
    p.insert_text((40, 70), 'Flat No 1203, Tower B, Lodha Palava City, Near Xperia Mall, Dombivli East, Thane District, Maharashtra 421204', fontsize=9)
    p.insert_text((40, 88), 'Plot 45, opp. Ram Mandir, behind Bus Stand, Sangli - 416416', fontsize=9)
    p.insert_text((40, 106), 'NO 5 3RD CROSS GANDHI NAGAR BELGAUM KARNATAKA 590016', fontsize=9)
    p.insert_text((40, 124), 'House 12 Sector 21 Panchkula Haryana 134109 India', fontsize=9)
    p.insert_text((40, 142), 'Survey No 88 Shirur Taluka Pune District India 412210', fontsize=9)
    p.insert_text((40, 160), 'Rent 12,345.00  Flat 9 Sai Kripa Nagpur - 440010', fontsize=9)
    p.insert_text((40, 178), "Employee's address and ZIP code", fontsize=9)
    p.insert_text((40, 196), '77 Banyan Tamarind Unit 4', fontsize=9)
    p.insert_text((40, 214), "Payer's street address", fontsize=9)
    p.insert_text((40, 232), 'Shivaji Chowk, Kasturba Marg', fontsize=9)
    p.insert_text((40, 250), 'Number, street, and room or suite no.', fontsize=9)
    p.insert_text((40, 268), 'Plot 5 MIDC Industrial Area', fontsize=9)
    p.insert_text((40, 286), 'SAN JOSE', fontsize=9)
    p.insert_text((40, 304), 'CA', fontsize=9)
    p.insert_text((40, 322), '95131-1234', fontsize=9)
    p.insert_text((40, 340), '900 W HARBOR DR STE 200', fontsize=9)
    p.insert_text((40, 358), 'Street address', fontsize=9)
    p.insert_text((40, 376), 'If you moved, see the instructions for line 5', fontsize=9)
    p.insert_text((40, 394), 'City or town, state or province, country, and ZIP or foreign postal code', fontsize=9)
    p.insert_text((40, 412), 'Part IV Summary of Tax Items', fontsize=9)
    p.insert_text((40, 430), 'Enter your address', fontsize=9)
    p.insert_text((40, 448), 'Rents received 12,345 and 6,789', fontsize=9)
    p.insert_text((40, 466), 'KEEP: Invoice - 123456  Bill No - 556677  Ref, 654321', fontsize=9)
    p.insert_text((40, 484), 'KEEP: Karnataka Bank Ltd  State Bank of India  Tax paid in India 2024', fontsize=9)
    p.insert_text((40, 502), 'KEEP: 5 Social security tax withheld  Box 12 Code DD', fontsize=9)


def field_labels_page(p):
    # Empty address fields on a Drake-printed foreign address block (real layout, 2024 return; probe via
    # diag_redact.py): the address labels' next line is the next field's number and label. Redacting that
    # label made the following one line up under the address label, and verify() failed the file. Also a
    # checkbox "X" on the row above a 9-digit number next to a state code + 5 digits: once the number went,
    # "X / NY / 10001" read as city, state, ZIP.
    p.insert_text((40, 480), "10  Street address (number, street, apartment or suite number)", fontsize=6)
    p.insert_text((300, 480), "11  City", fontsize=6)
    p.insert_text((420, 480), "Postal code", fontsize=6)
    p.insert_text((40, 494), "12  State", fontsize=6)
    p.insert_text((300, 494), "13  Country", fontsize=6)
    p.insert_text((420, 494), "14  ZIP/Postal Code", fontsize=6)
    p.insert_text((35, 318), "Dependent row", fontsize=9)
    p.insert_text((560, 270), "X", fontsize=9)
    p.insert_text((344, 318), "246813579", fontsize=9)
    p.insert_text((430, 318), "NY", fontsize=9)
    p.insert_text((459, 318), "10001", fontsize=9)


def nine_digit_page(p):
    # Digits differ from the known test SSNs on purpose: a known SSN is matched in any format, which would
    # hide whether the standalone 9-digit rule (ID9) is what removed something.
    p.insert_text((72, 100), "Employer identification number 246813579  Employee code 135792468")
    p.insert_text((72, 130), "KEEP: ten digits 2468135790, eight digits 24681357")
    p.insert_text((72, 145), "KEEP: amount 246813579.50, ZIP+4 24681-3579, grouped 1,246813579")
    p.insert_text((72, 160), "KEEP: negative -246813579 and ref W2-246813579")


def build(d):
    def save(name, fill, rotate=0, crop=None, metadata=None, scan=False, xmp=None):
        doc = fitz.open()
        p = doc.new_page()
        fill(p)
        if rotate:
            p.set_rotation(rotate)
        if crop:
            p.set_cropbox(fitz.Rect(*crop))
        if metadata:
            doc.set_metadata(metadata)
        if xmp:
            doc.set_xml_metadata(xmp)
        if scan:  # image-only page containing an SSN
            img = fitz.open()
            ip = img.new_page()
            ip.insert_text((72, 100), "SSN 111-22-3333")
            doc.new_page().insert_image(fitz.Rect(0, 0, 612, 792), pixmap=ip.get_pixmap())
        doc.save(d / name)

    # name -> (expected status, strings that must survive)
    save("plain.pdf", base_page, metadata={"author": "John Smith", "title": "Jane Doe 1040"}, xmp=XMP)
    save("rotated.pdf", base_page, rotate=90)
    save("cropped.pdf", base_page, crop=(20, 30, 580, 800))
    save("scanned_page.pdf", base_page, scan=True)
    save("split.pdf", split_page)
    save("split_rotated.pdf", split_page, rotate=90)
    save("sideways_90.pdf", lambda p: sideways_page(p, 90))
    save("sideways_270.pdf", lambda p: sideways_page(p, 270))
    save("variants.pdf", variants_page)
    save("known_ssn.pdf", known_ssn_page)
    save("nine_digit.pdf", nine_digit_page)
    save("contact.pdf", contact_page)
    save("ids.pdf", ids_page)
    save("india.pdf", india_page)
    save("layout.pdf", layout_page)
    save("variations.pdf", variations_page)
    save("field_labels.pdf", field_labels_page)
    save("known_ssn_rotated.pdf", known_ssn_page, rotate=270)
    for named in NAMED_FILES:
        save(named, base_page)
    return {
        "plain.pdf": ("OK", BASE_KEEP), "rotated.pdf": ("OK", BASE_KEEP),
        "cropped.pdf": ("OK", BASE_KEEP), "scanned_page.pdf": ("REVIEW", BASE_KEEP),
        "split.pdf": ("OK", SPLIT_KEEP), "split_rotated.pdf": ("OK", SPLIT_KEEP),
        "sideways_90.pdf": ("OK", BASE_KEEP), "sideways_270.pdf": ("OK", BASE_KEEP),
        "variants.pdf": ("OK", ["Jane Smith paid Johnny Doe and Roberta"]),
        "nine_digit.pdf": ("OK", ["ten digits 2468135790", "eight digits 24681357", "amount 246813579.50",
                                  "ZIP+4 24681-3579", "grouped 1,246813579", "negative -246813579",
                                  "ref W2-246813579"]),
        "contact.pdf": ("OK", ["Email:", "Phone", "Date of Birth:", "DOB", "Birth date (MM/DD/YYYY)",
                               "Date sold 07/22/2024", "Acquired 2023-01-15", "Order 5551234567",
                               "dots 555.123.4567", "spaces 555 123 4567", "Ref 123-456-78901",
                               "born before January 2, 1961", "ZIP+4 62701-1234", "03/14/1980"]),
        "india.pdf": ("OK", ["Owner addr:", "Also:", "Property:", "Farm:", "Country India", "State Karnataka",
                             "Punjab National Bank", "Amount 560001", "Self-select PIN 12345",
                             "Tax year 2024 India", "Sai Apts"]),
        "layout.pdf": ("OK", ["Number, street, and room or suite no.", "ZIP or foreign postal code",
                              "Part VI Detailed Information for Each Other Foreign Asset", "Form 8938 (Rev. 11-2024)",
                              "Home address (number and street)", "Mailing address of foreign entity"]),
        "field_labels.pdf": ("OK", ["10 Street address", "11 City", "Postal code", "12 State", "13 Country",
                                    "14 ZIP/Postal Code", "X", "NY", "10001"]),
        "variations.pdf": ("OK", ["Rent 12,345.00", "Employee's address and ZIP code", "Payer's street address",
                                  "If you moved, see the instructions for line 5", "Part IV Summary of Tax Items",
                                  "Rents received 12,345 and 6,789", "Invoice - 123456", "Bill No - 556677",
                                  "Ref, 654321", "Karnataka Bank Ltd", "State Bank of India", "Tax paid in India 2024",
                                  "5 Social security tax withheld", "Box 12 Code DD"]),
        # last 4 of an account number stays visible; labels stay
        "ids.pdf": ("OK", ["PAN", "Karvy ID", "Aadhaar", "CA ID", "9001", "Account No.", "1234",
                           "Account number:", "5678", "A/c No:", "2211", "Folio No.", "EIN", "1122",
                           "years 2024 2023 2022", "Wages 123456.78", "grouped 12,345,678,901",
                           "1 Wages, tips, other comp.", "16 State wages, tips", "OMB No. 1545-0074",
                           "Account number (see instructions) 2 Early withdrawal penalty",
                           "15 State Employer's state ID number", "PAN card", "Tax year 2024"]),
        "known_ssn.pdf": ("OK", ["Card ending 6789", "Invoice 0123456789", "Other XXX-XX-1111"]),
        "known_ssn_rotated.pdf": ("OK", ["Card ending 6789", "Invoice 0123456789", "Other XXX-XX-1111"]),
    }


def run(*args):
    return subprocess.run([sys.executable, str(HERE / "redact.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


SCAN_LINES = ["Form W-2 Wage and Tax Statement 2025",
              "Employee: John Smith   SSN 123-45-6789",
              "Spouse: Doe, Jane  Dependent SSN 222-33-4444",
              "Employer EIN 12-3456789  Acme Widgets Incorporated",
              "Employer identification number 987654321",
              "Box 1 Wages 85000.00   Box 2 Federal tax withheld 12000.00",
              "KEEP: Mary Smith and John Adams are other people"]
SCAN_FORBIDDEN = {"John Smith": r"john\s+smith", "Jane Doe": r"doe,?\s+jane|jane\s+doe", "SSN": r"\d{3}-\d{2}-\d{4}",
                  "EIN": r"\d{2}-\d{7}", "undashed 9-digit": r"(?<![\d.,$-])\d{9}(?!\d)"}


def scan_pdf(path, lines, rotate=0, pixel_rotate=0):
    """Image-only PDF (no text layer): the lines are drawn, rendered to a picture, and only the picture kept."""
    src = fitz.open()
    p = src.new_page()
    for k, line in enumerate(lines):
        p.insert_text((72, 100 + 30 * k), line, fontsize=13)
    png = p.get_pixmap(dpi=200).tobytes("png")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png)
    if pixel_rotate:  # the picture itself is sideways, as from a badly fed scanner
        pix = fitz.Pixmap(png)
        doc = fitz.open()
        page = doc.new_page(width=pix.height * 72 / 200, height=pix.width * 72 / 200)
        page.insert_image(page.rect, stream=png, rotate=pixel_rotate)
    if rotate:
        page.set_rotation(rotate)
    doc.save(path)


def ocr_checks(check):
    """--ocr: image-only pages are read, redacted and re-read; unreadable ones stay REVIEW. Needs tesseract."""
    sys.path.insert(0, str(HERE))
    import redact_ocr
    if not redact_ocr.available():
        print("  SKIP  OCR checks (tesseract not installed)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        src, out, out_plain = Path(tmp, "in"), Path(tmp, "out"), Path(tmp, "out_plain")
        src.mkdir()
        scan_pdf(src / "scan.pdf", SCAN_LINES)
        scan_pdf(src / "scan_rot90.pdf", SCAN_LINES, rotate=90)
        scan_pdf(src / "scan_sideways.pdf", SCAN_LINES, pixel_rotate=90)
        scan_pdf(src / "scan_few_words.pdf", ["Hi John Smith"])
        blank = fitz.open()
        blank.new_page()
        blank.save(src / "blank.pdf")
        mixed = fitz.open()
        mixed.new_page().insert_text((72, 100), "Taxpayer John Smith SSN 123-45-6789 and some more words")
        mixed.insert_pdf(fitz.open(src / "scan.pdf"))
        mixed.save(src / "mixed.pdf")

        plain = run("--input", str(src), "--output", str(out_plain), "--names", NAMES, "--ssns", SSNS)
        statuses = {l.split()[1].rstrip(":"): l.split()[0] for l in plain.stdout.splitlines()
                    if l.split()[:1] and l.split()[0] in ("OK", "REVIEW", "FAIL")}
        check("OCR off: an image-only page still makes the file REVIEW", statuses.get("scan.pdf") == "REVIEW", str(statuses))

        r = run("--input", str(src), "--output", str(out), "--names", NAMES, "--ssns", SSNS, "--ocr")
        statuses = {l.split()[1].rstrip(":"): l.split()[0] for l in r.stdout.splitlines()
                    if l.split()[:1] and l.split()[0] in ("OK", "REVIEW", "FAIL")}
        for name, want in {"scan.pdf": "OK", "scan_rot90.pdf": "OK", "mixed.pdf": "OK", "blank.pdf": "REVIEW",
                           "scan_few_words.pdf": "REVIEW", "scan_sideways.pdf": "REVIEW"}.items():
            check(f"OCR on, {name}: status {want}", statuses.get(name) == want, r.stdout)
        check("OCR on: console reports which pages OCR read", "OCR read page(s) [1]" in r.stdout, r.stdout)
        for name in ("scan.pdf", "scan_rot90.pdf", "mixed.pdf"):
            with fitz.open(out / name) as doc:
                check(f"OCR on, {name}: no text layer was added", not any(pg.get_text().strip() for pg in doc if pg.number == len(doc) - 1))
                seen = " ".join(" ".join(w["text"] for w in redact_ocr.read_words(pg)) for pg in doc)
            leaked = [k for k, rx in SCAN_FORBIDDEN.items() if re.search(rx, seen, re.I)]
            check(f"OCR on, {name}: sensitive text gone from the pixels", not leaked, f"leaked {leaked}")
            if name != "mixed.pdf":
                check(f"OCR on, {name}: look-alikes and other content kept",
                      all(w in seen for w in ("Mary", "Adams", "Acme", "85000.00")), "over-redacted")

def main():
    results = []

    def check(label, ok, detail=""):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail and not ok else ""))

    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp, "in"), Path(tmp, "out")
        src.mkdir()
        expected = build(src)
        originals = {p.name: p.read_bytes() for p in src.iterdir()}
        r = run("--input", str(src), "--output", str(out), "--names", NAMES + ", " + INDIA_ENTRY, "--ssns", SSNS)
        check("exit code 0 (no FAIL files)", r.returncode == 0, r.stdout + r.stderr)
        check("console output never prints a supplied SSN", "6789" not in r.stdout and "4321" not in r.stdout)
        check("console output never prints a supplied DOB or phone",
              not re.search(r"1980|0199", r.stdout), r.stdout[:300])

        for name, (status, keep) in expected.items():
            line = next((l for l in r.stdout.splitlines() if l.strip().endswith(name + ":") or f" {name}:" in l), "")
            check(f"{name}: status {status}", line.split()[:1] == [status], line.strip())
            with fitz.open(out / name) as doc:
                texts = [pg.get_text(sort=s) for pg in doc for s in (False, True)]
                # "format"/"encryption" describe the file itself, not user-entered metadata
                meta = " ".join(v for k, v in doc.metadata.items() if v and k not in ("format", "encryption"))
            leaked = [k for k, rx in FORBIDDEN.items() if any(rx.search(t) for t in texts)]
            check(f"{name}: nothing sensitive left", not leaked, f"leaked {leaked}")
            missing = [k for k in keep if not any(k in " ".join(t.split()) for t in texts)]
            check(f"{name}: look-alikes kept", not missing, f"over-redacted {missing}")
            check(f"{name}: metadata cleared", not meta, meta)
            with fitz.open(out / name) as doc:
                xmp_left = doc.get_xml_metadata() or ""
            check(f"{name}: XMP metadata cleared", not re.search(r"john\s+smith|jane\s+doe", xmp_left, re.I), xmp_left[:80])
            check(f"{name}: original untouched", (src / name).read_bytes() == originals[name])

        out_names = {p.name for p in out.iterdir()}
        check("named source files written under scrubbed names", EXPECTED_OUT_NAMES <= out_names,
              f"got {sorted(n for n in out_names if 'REDACTED' in n or 'W2' in n)}")
        squashed = [re.sub(r"[^a-z]", "", n.lower()) for n in out_names]
        check("no output filename carries a supplied name",
              not any("johnsmith" in n or "janedoe" in n for n in squashed))
        shown_names = [m.group(1) for m in re.finditer(r"^\s+(?:OK|REVIEW|FAIL|ERROR)\s+(.*?):", r.stdout, re.M)]
        check("console status lines never print a client name from a filename",
              shown_names and not any(re.search(r"john[\s_]*smith|jane[\s_]*doe", n, re.I) for n in shown_names),
              str(shown_names))
        check("same input/output folder refused", run("--input", str(src), "--output", str(src)).returncode != 0)
        check("malformed --ssns refused",
              run("--input", str(src), "--output", str(out), "--ssns", "12-345").returncode != 0)

    ocr_checks(check)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
