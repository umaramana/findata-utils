# GVK Merge Tool — Requirements

## Purpose
Merge two source files of Guru Vachaka Kovai (by Bhagavan Ramana Maharshi) — one TXT, one DOCX — into a single DOCX, matching content by verse number.

## Source Files
| File | Format | Content |
|---|---|---|
| `*file1.txt` | Plain text, UTF-8 | Original Tamil verse (compact form + expanded text + word meanings + commentary) |
| `*file2.docx` | Word document | Prose translation/explanation per verse (Sadhu Om) |

> When full 1000-verse files are available, update `_DEFAULT_TXT` and `_DEFAULT_DOC` at the top of `merge_gvk.py`.

## Collaboration Model
- Both editors (user + collaborator) work on a shared Google Doc via Google Drive
- Source files are named `*file1.txt` and `*file2.docx` per trial folder
- Subtitle cue keys: editors use existing substitution keys from their own script (to be shared when subtitle phase begins)

## Trial Folder Convention
Each trial folder holds its own input and output files:
- Input TXT  : `*file1.txt`
- Input DOCX : `*file2.docx`
- Output     : `*merged.docx` (auto-named: file2 stem with "file2" → "merged")

---

## Verse Detection

### TXT file
- Verse start: `^\d+\.` followed by anything **except a tab**
- Tab after number (`^\d+\.\t`) = section header → skip
- Duplicate verse number = sub-section header reusing a small number → skip

### DOCX file
- Verse start: `^\d+\.` followed by tab or space, with content ≥ 40 characters
- Short content (< 40 chars) = chapter/section heading → preserved, not a verse
- In file2, the tab between number and text is a `<w:tab/>` XML element (not `\t` in text)

---

## Section Naming Convention

Each verse is composed of up to 10 named sections. Sections marked Optional may be absent for some verses.

| File   | Section name                               | Subtitle (future use)                                         | Order | Optional? |
|--------|--------------------------------------------|---------------------------------------------------------------|-------|-----------|
| file1  | Verse No lines 1–4                         | N.\t                                                          | 1     |           |
| file1  | padachedam                                 | **பதச்சேதம்:**                                                | 2     |           |
| file1  | arumpadhavurai                             | **அரும்பதவுரை:**                                              | 3     | Optional  |
| —      | muruganar karuthurai                       | **முருகனார் கருத்துரை:**                                      | 4     | NA        |
| file1  | muruganar pozhippurai                      | **முருகனார் பொழிப்புரை:**                                     | 5     | Optional  |
| file1  | muruganar visedavurai                      | **முருகனார் விசேடவுரை:**                                      | 6     | Optional  |
| file2  | muruganar visadavuraikku sadhuom thazhuval | **முருகனார் விசேடவுரைக்கு சாதுஓம் தழுவல்:**                 | 7     | Optional  |
| file2  | sadhuom pozhippurai                        | **சாது ஓம் பொழிப்புரை:**                                     | 8     |           |
| file2  | sadhuom vilakkakkurippu                    | **சாது ஓம் விளக்கக் குறிப்பு:**                              | 9     | Optional  |
| file2  | bagavan kurippu                            | **பகவான் குறிப்பு:**                                          | 10    | Optional  |

> Section subtitles are NOT yet present in source files (except `விளக்கக் குறிப்பு:` already appears in file2 as `Heading 3`).
> Subtitle insertion is a future phase — will use editors' existing substitution/cue keys.

---

## Output Format

### Per verse structure
```
[chapter title — Heading 1/Title, deep-copied from file2]
N.\t[file1 verse line 1]       ← poetic verse: 4 separate paragraphs
    \t[line 2]                  ← lines 2–4 indented with \t (align under line 1 text)
    \t[line 3]
    \t[line 4]
                                ← blank line (after verse block)
[padachedam]
                                ← blank line
[arumpadhavurai — if present]
                                ← blank line
[muruganar pozhippurai — if present]
                                ← blank line
[muruganar visedavurai — if present]
                                ← blank line (after last file1 section = file1/file2 separator)
[sadhuom pozhippurai — number stripped, run formatting preserved]
[sadhuom vilakkakkurippu — if present]
[bagavan kurippu — if present]
                                ← blank line (end of verse)
```

### Formatting rules
1. **Document base**: file2 (DOCX) is copied as the output template — all its styles and fonts are inherited
2. **Chapter titles** (`Title`, `Heading 1`, `Heading 2` styles): deep-copied from file2 as-is — exact style, font, and formatting preserved
3. **file1 content** (verse + padachedam etc.): new paragraphs using `normal` style with Latha font, 10pt, 1.5 line spacing applied explicitly
4. **file2 content**: deep-copied paragraph XML — all run-level formatting preserved (red font, yellow highlight, bold, italic, etc.)
5. **Verse number in file2**: stripped at XML level — removes `<w:t>N.</w:t>` and adjacent `<w:tab/>` from first run; remaining text and formatting untouched
6. **Verse lines (1–4)**: each on its own paragraph (hard return). Line 1 prefixed `N.\t`; lines 2–4 prefixed `\t` to align under line 1 text. Followed by one blank paragraph.
7. **Section separation (file1)**: each section (padachedam, arumpadhavurai, etc.) followed by one blank paragraph — giving 2 hard returns between sections. Last section's blank also serves as file1/file2 visual separator.
8. **Blank line (end of verse)**: empty `normal` paragraph after last file2 paragraph of each verse
9. **Font**: Latha, 10pt (sz=20, szCs=20), RTL off — applied to every run in file1-sourced paragraphs
10. **Line spacing**: 1.5 — applied to all file1-sourced paragraphs (file2 paragraphs inherit their own spacing via deep-copy)

---

## Verse Number Stripping (file2)
File2 stores verse numbers as separate XML nodes inside the first `w:r` of each verse paragraph:
```xml
<w:r>
  <w:rPr>...</w:rPr>
  <w:t>N.</w:t>      ← removed
  <w:tab/>           ← removed
  <w:t>actual text</w:t>
</w:r>
```
The script removes `<w:t>N.</w:t>` and the following `<w:tab/>` only. All other runs and formatting are preserved.

---

## Chapter Header Detection (file2)
Paragraphs with styles `Title`, `Heading 1`, `Heading 2` are chapter-level headers:
- Collected as pending when encountered
- Associated with the next verse number that follows them
- Deep-copied into output before that verse

Paragraphs with `Heading 3` and below (e.g. `விளக்கக் குறிப்பு:`) are treated as verse-level content — they stay inside the verse's paragraph block.

---

## Verification Step

### `--verify-only` (inputs, no write)
1. TXT: count == range, list any gaps within range
2. DOCX: count == range, list any gaps within range
3. Cross-match: verse numbers present in one file but not the other

### Normal run (merge + output check)
4. All of stage 1–3 first; abort or user confirms on mismatch
5. Write merged DOCX
6. Parse output: count == expected, numbers contiguous, list any gaps

### `--verify-report` (content diff, post-merge)
7. For each verse: file1 expected lines vs file1-sourced output paragraphs (Latha, 1.5-spaced)
8. Writes `verify_report.txt` to same folder as output

---

## Regression Tests
`test_gvk.py` — run from the `gvk/` folder:
```
python test_gvk.py
```
Tests merge output on `trialphase1and2/` (verses 1–11, known good baseline).
Checks: verse count, contiguity, `N.\t` and `\t` prefixes, Latha 10pt font, 1.5 spacing,
blank after verse block, blank at end of verse, verse number stripped from file2,
chapter header styles.

---

## Script
`merge_gvk.py` — run from the `gvk/` folder:
```
python merge_gvk.py                               # uses default files in gvk/ root
python merge_gvk.py wholefile                     # uses *file1.txt + *file2.docx in subfolder
python merge_gvk.py --verify-only                 # check verse counts only, no output written
python merge_gvk.py wholefile --verify-only
python merge_gvk.py wholefile --verify-report     # merge + write verify_report.txt
```

---

## Known Formatting Irregularities in Source Files
- Some verse numbers use space after dot (`53. துன்பக்`), others attach directly (`1.அருளவா`) — handled
- DOCX verse 18 uses space instead of tab — handled via length threshold
- TXT sub-section header `1.உலகுண்மைத்திறன்` reuses verse number 1 — handled via duplicate-skip
- TXT table of contents entries (`63. Chapter\t\t128`) use page-number suffix — detected via `\t\d+$` and skipped
- TXT file may be UTF-16 LE (BOM `0xFFFE`) — auto-detected and handled

---

## Current Status
- `trialphase1and2/` — verses 1–11. Regression baseline. All tests green.
- `wholefile/` — full ~1249-verse files. Run `--verify-only` before merge.
- Remaining `wholefile/` mismatches (pending file2 corrections): TXT only `[63, 282, 815, 1136]`; DOCX only `[99, 304, 570, 621, 696]`; genuine gap `1135`

---

## Pending (Future Phases)
- **Subtitle insertion**: add **பதச்சேதம்:**, **அரும்பதவுரை:**, **சாது ஓம் பொழிப்புரை:** etc. labels — requires section detection logic in file1 and agreement on cue key convention with editors
- **Section detection (file1)**: define boundaries between padachedam / arumpadhavurai / pozhippurai / visedavurai (currently all treated as continuation lines after the 4 verse lines)
- **Subtitle cue keys**: editors to share existing substitution keys; script will convert to Tamil subtitle labels
- **`விளக்கக் குறிப்பு:` standardisation**: file2 currently uses bare label; future — prefix with `சாது ஓம்` → `சாது ஓம் விளக்கக் குறிப்பு:`
