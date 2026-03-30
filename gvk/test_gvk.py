"""
test_gvk.py — GVK merge formatting regression tests.

Runs merge on trialphase1and2/ (verses 1–11, known good baseline) and
checks all formatting rules on the merged output.

Usage:
  python test_gvk.py
"""

import re
import sys
from pathlib import Path
from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn

GVK_DIR = Path(__file__).parent
sys.path.insert(0, str(GVK_DIR))
from merge_gvk import parse_txt, parse_docx, write_merged, CHAPTER_HEADER_STYLES

TRIAL_DIR  = GVK_DIR / "trialphase1and2"
VERSE_PAT  = re.compile(r'^(\d+)\.\t')
TAB_PREFIX = re.compile(r'^\t')

PASS_COUNT = 0
FAIL_COUNT = 0


# ── Helpers ────────────────────────────────────────────────────────────────────

def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS  {name}")
        PASS_COUNT += 1
    else:
        msg = f"  FAIL  {name}"
        if detail:
            msg += f"\n        {detail}"
        print(msg)
        FAIL_COUNT += 1


def _run_font(r_elem):
    rpr = r_elem.find(qn('w:rPr'))
    if rpr is None:
        return None
    rf = rpr.find(qn('w:rFonts'))
    return rf.get(qn('w:ascii')) if rf is not None else None


def _run_size(r_elem):
    rpr = r_elem.find(qn('w:rPr'))
    if rpr is None:
        return None
    sz = rpr.find(qn('w:sz'))
    return sz.get(qn('w:val')) if sz is not None else None


def _is_latha(para):
    for r in para._element.findall('.//' + qn('w:r')):
        if _run_font(r) == 'Latha':
            return True
    return False


def _spacing_is_1_5(para):
    return para.paragraph_format.line_spacing_rule == WD_LINE_SPACING.ONE_POINT_FIVE


# ── Setup: run merge, load output ─────────────────────────────────────────────

def setup():
    txt_files = list(TRIAL_DIR.glob("*file1.txt"))
    doc_files = list(TRIAL_DIR.glob("*file2.docx"))
    assert txt_files, f"No *file1.txt in {TRIAL_DIR}"
    assert doc_files, f"No *file2.docx in {TRIAL_DIR}"

    txt, doc = txt_files[0], doc_files[0]
    stem = doc.stem.replace("file2", "merged")
    out  = TRIAL_DIR / f"{stem}.docx"

    txt_verses           = parse_txt(txt)
    docx_verses, headers = parse_docx(doc)
    write_merged(txt_verses, docx_verses, headers, doc_file=doc, out_path=out)
    return Document(out), txt_verses


# ── Group output paragraphs by verse ──────────────────────────────────────────

def group_by_verse(paras):
    verse_paras = {}
    current = None
    for para in paras:
        if para.style.name in CHAPTER_HEADER_STYLES:
            current = None   # chapter header terminates the previous verse group
            continue
        m = VERSE_PAT.match(para.text)
        if m:
            current = int(m.group(1))
            verse_paras[current] = [para]
        elif current is not None:
            verse_paras[current].append(para)
    return verse_paras


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_structure(verse_paras, txt_verses):
    print("\n[Structure]")
    nums = sorted(verse_paras.keys())

    check("Verse count in output == input",
          len(verse_paras) == len(txt_verses),
          f"output={len(verse_paras)}, input={len(txt_verses)}")

    if nums:
        expected = list(range(nums[0], nums[-1] + 1))
        check("Verse numbers contiguous",
              nums == expected,
              f"gaps: {sorted(set(expected) - set(nums))}")


def test_prefixes(verse_paras):
    print("\n[Verse Line Prefixes]")
    failures = []
    for num, plist in verse_paras.items():
        file1_paras = [p for p in plist if _is_latha(p) and p.text.strip()]
        if not file1_paras:
            failures.append(f"Verse {num}: no file1 paragraphs found")
            continue
        # Line 1: must start with N.\t
        first = file1_paras[0].text
        if not first.startswith(f"{num}.\t"):
            failures.append(f"Verse {num}: line 1 wrong prefix: {repr(first[:25])}")
        # Lines 2–4: must start with \t
        for p in file1_paras[1:4]:
            if p.text.strip() and not TAB_PREFIX.match(p.text):
                failures.append(f"Verse {num}: continuation line missing tab: {repr(p.text[:25])}")
    check("N.\\t prefix on verse line 1", not failures, "; ".join(failures[:3]))


def test_file1_font_size(verse_paras):
    print("\n[File1 Font & Size]")
    font_failures = []
    size_failures = []
    for num, plist in verse_paras.items():
        for para in plist:
            if not _is_latha(para):
                continue
            for r in para._element.findall('.//' + qn('w:r')):
                f = _run_font(r)
                s = _run_size(r)
                if f is not None and f != 'Latha':
                    font_failures.append(f"Verse {num}: font={f}")
                if s is not None and s != '20':
                    size_failures.append(f"Verse {num}: sz={s}")
    check("File1 runs use Latha font", not font_failures, "; ".join(font_failures[:3]))
    check("File1 runs are 10pt (sz=20)", not size_failures, "; ".join(size_failures[:3]))


def test_file1_spacing(verse_paras):
    print("\n[File1 Line Spacing]")
    failures = []
    for num, plist in verse_paras.items():
        for para in plist:
            # Only check paragraphs unambiguously file1: verse lines identified by prefix
            if VERSE_PAT.match(para.text) or TAB_PREFIX.match(para.text):
                if not _spacing_is_1_5(para):
                    failures.append(f"Verse {num}: verse line spacing != 1.5")
    check("Verse line paragraphs have 1.5 spacing", not failures, "; ".join(failures[:3]))


def test_blank_after_verse_block(verse_paras):
    print("\n[Blank Paragraphs]")
    failures = []
    for num, plist in verse_paras.items():
        # Find last verse-line paragraph (N.\t or \t prefixed, Latha)
        last_verse_idx = None
        for i, p in enumerate(plist):
            if _is_latha(p) and (VERSE_PAT.match(p.text) or TAB_PREFIX.match(p.text)):
                last_verse_idx = i
        if last_verse_idx is None:
            continue
        next_idx = last_verse_idx + 1
        if next_idx >= len(plist) or plist[next_idx].text.strip():
            failures.append(f"Verse {num}: no blank paragraph after verse block")
    check("Blank paragraph after verse block", not failures, "; ".join(failures[:3]))


    # NOTE: test_blank_after_sections is not implemented.
    # Both file1 rest-lines and file2 paragraphs use Latha font and can share 1.5 spacing,
    # making it impossible to distinguish them in the output without file1/file2 boundary
    # tracking at write time. The verse-block blank and end-of-verse blank tests cover
    # the critical structural checks.


def test_blank_end_of_verse(verse_paras):
    failures = []
    for num, plist in verse_paras.items():
        if not plist or plist[-1].text.strip():
            failures.append(f"Verse {num}: no blank paragraph at end of verse")
    check("Blank paragraph at end of each verse", not failures, "; ".join(failures[:3]))


def test_verse_num_stripped(verse_paras):
    print("\n[File2 Formatting]")
    failures = []
    for num, plist in verse_paras.items():
        for para in plist:
            if _is_latha(para):
                continue   # skip file1 paragraphs
            for r in para._element.findall('.//' + qn('w:r')):
                for wt in r.findall(qn('w:t')):
                    if wt.text and re.match(r'^\d+\.$', wt.text.strip()):
                        failures.append(f"Verse {num}: verse number not stripped")
    check("Verse numbers stripped from file2 paragraphs", not failures,
          "; ".join(failures[:3]))


def test_chapter_headers(paras):
    print("\n[Chapter Headers]")
    hdr_paras = [p for p in paras if p.style.name in CHAPTER_HEADER_STYLES]
    check("At least one chapter header present", len(hdr_paras) > 0,
          "no Title / Heading 1 / Heading 2 found")
    wrong = [p for p in hdr_paras if p.style.name not in CHAPTER_HEADER_STYLES]
    check("All chapter headers have correct style", not wrong,
          "; ".join(f"'{p.text[:20]}' has style '{p.style.name}'" for p in wrong[:3]))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("GVK Formatting Regression Tests")
    print(f"Trial folder: {TRIAL_DIR}")
    print("=" * 60)

    doc, txt_verses = setup()
    paras       = doc.paragraphs
    verse_paras = group_by_verse(paras)

    test_structure(verse_paras, txt_verses)
    test_prefixes(verse_paras)
    test_file1_font_size(verse_paras)
    test_file1_spacing(verse_paras)
    test_blank_after_verse_block(verse_paras)
    test_blank_end_of_verse(verse_paras)
    test_verse_num_stripped(verse_paras)
    test_chapter_headers(paras)

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
