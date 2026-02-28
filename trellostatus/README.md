# Trello Weekly Status Pivot

Generates a formatted Excel summary of card counts per list from a Trello board JSON export.

**Run every Saturday.**

---

## Output

`trello_list_pivot.xlsx` — one column per week, showing card count per Trello list:

| List | 28-Feb-2026 |
|---|---|
| NOT THIS YEAR | 15 |
| Backlog | 145 |
| ... | ... |
| TOTAL | 219 |

Formatted with dark blue headers, alternating rows, and a yellow total row.

---

## Weekly Routine

**Step 1 — Export from Trello**
- Open the board → Board menu (top right) → Print and Export → Export as JSON
- Save the JSON file into this folder (`trellostatus/`)

**Step 2 — Update filename if needed**
- Open `trello_pivot.py`
- Check that `JSON_FILE` matches the exported filename (it may change each export)

**Step 3 — Run**
```
cd trellostatus
python trello_pivot.py
```

**Step 4 — Import to Google Sheets**
- Open `trello_list_pivot.xlsx`
- Copy the data column into the weekly status Google Sheet

---

## Dependencies

Uses `openpyxl` — already installed if you have the stock processor set up.
If not: `pip install openpyxl`

---

## Notes

- Archived (closed) cards are excluded from counts
- List order follows the board column order
- JSON and Excel output files are gitignored — only the script is tracked
