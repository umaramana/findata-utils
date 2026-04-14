# claudefin — Practice Tools Registry

Custom scripts and utilities built for this practice.
Each entry has enough info to run the tool without reading the code.

Run all scripts from the **workspace root**:
`C:\Users\UN\fractals\VibeCoding\ClaudeCode`

---

## Tools

### 1. Jones Tax Category Summary
| | |
|---|---|
| **File** | `claudefin/jones/jones_tax_summary.py` |
| **Client** | Jones |
| **Purpose** | Maps Quicken transactions to IRS categories and produces a tax estimate summary |
| **Input** | Quicken "Transaction" report exported as xlsx (no-pivot version) |
| **Output** | `docs/jones/Jones_Tax_Summary.xlsx` — Summary tab (key figures + rental matrix + detail sections) + Transactions tab (all rows tagged) |
| **Run (default)** | `python claudefin/jones/jones_tax_summary.py` |
| **Run (new file)** | `python claudefin/jones/jones_tax_summary.py --input "docs/jones/NewFile.xlsx" --output "docs/jones/Summary_2026.xlsx"` |
| **Last updated** | Apr 2026 |
| **Businesses** | Farming (Harrellsville + Murfreeboro) + Rental RE (Beaumont, Britton, Hickory, OBBC II, River, Woodrow School, secu3496) |
| **Reuse for similar client** | Edit `PROPERTY_ORDER` for their properties, `irs_group()` for their category names, `preprocess_row()` for any Quicken artifacts found in their data |

**Sections produced:** Farm Income/Expenses (Sch F) · Rental Income & Expenses per property matrix (Sch E) · Other Income · Land Sale Proceeds (flagged) · Schedule A itemized · RE Business · Personal Auto · Non-deductible · Transfers excluded

**Known Quicken artifacts handled:**
- Opening balance entries (desc = "Opening Balance") → excluded
- Mortgage principal splits (positive amount under rental expense + "payment/transfer" desc) → excluded
- Land sale detection via memo field ("land sale")
- Forestry cost-share payment → Farm Income

---

### 2. Loan Comparator
| | |
|---|---|
| **File** | `claudefin/loan_comparator.html` |
| **Client** | General |
| **Purpose** | Side-by-side loan comparison — rate, term, monthly payment, total interest |
| **Run** | Open in browser — no server needed |

---

### 3. Chart Types Visual Reference
| | |
|---|---|
| **File** | `claudefin/chart_types_visual_reference.html` |
| **Client** | General |
| **Purpose** | Visual reference guide for chart type selection |
| **Run** | Open in browser — no server needed |

---

## Adding a new tool

1. Create a subfolder if client-specific: `claudefin/clientname/`
2. Write the script with a full docstring (client, input, output, usage, reuse notes)
3. Add a row to this README
4. Add a memory entry in `MEMORY.md` under the relevant project
5. Commit `claudefin/` — **never commit data files (xlsx, csv, images)**

## Gitignore rule
Data files in `docs/` and `claudefin/` are never committed.
Only `.py`, `.html`, `.md` files belong in git.
