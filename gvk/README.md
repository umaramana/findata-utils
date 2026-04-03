# GVK Merge Tool

Merges two Guru Vachaka Kovai source files (TXT + DOCX) into a single formatted DOCX, matched by verse number.

## Run Commands

All commands must be run from inside the `gvk/` folder:

```bash
cd gvk
```

| Task | Command |
|---|---|
| Merge wholefile (full ~1249 verses) | `python merge_gvk.py wholefile` |
| Merge trial phase (verses 1–11) | `python merge_gvk.py trialphase1and2` |
| Check verse count gaps only (no output) | `python merge_gvk.py wholefile --verify-only` |
| Generate content diff report | `python merge_gvk.py wholefile --verify-report` |
| Run regression tests | `python test_gvk.py` |

Output is written to the same folder passed as argument, e.g. `wholefile/gvk_merged.docx`.

`--verify-report` writes `verify_report.txt` in the same folder.

## Folder Structure

```
gvk/
  merge_gvk.py          # main script
  test_gvk.py           # regression tests (11 tests, must all pass)
  REQUIREMENTS.md       # full spec
  trialphase1and2/      # verses 1–11 (regression baseline)
    1-11 gvk file1.txt
    1-11 gvk file2.docx
    1-11 gvk merged.docx
  wholefile/            # full verse files (active working set)
    gvk file1.txt
    gvk file2.docx
```

## Source Files

- `*file1.txt` — Tamil verse + padachedam + commentary (UTF-8 or UTF-16 LE, auto-detected)
- `*file2.docx` — Sadhu Om prose translation (used as output template — preserves styles/fonts)

## Per-Verse Output Order

1. Chapter title / heading (deep-copied from file2)
2. `N.\t` + TXT verse lines (file1 content, Latha 10pt, 1.5 spacing)
3. Blank line
4. DOCX lines with verse number stripped (file2 content, original formatting preserved)
5. Blank line

## Dependencies

```bash
pip install python-docx
```
