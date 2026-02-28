# Trello List Pivot — Weekly Saturday routine
# Usage: drop the latest Trello board export JSON into this folder,
#        update JSON_FILE below if the filename changed, then run:
#        python trello_pivot.py
# Output: trello_list_pivot.xlsx — import into Google Sheets manually

import json
from collections import Counter
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import DataPoint

JSON_FILE = "V1jGClbh - rasrichtaxteam-2026 (1).json"
OUTPUT_FILE = "trello_list_pivot.xlsx"

with open(JSON_FILE, encoding="utf-8") as f:
    data = json.load(f)

# Build list id -> name map
list_names = {lst["id"]: lst["name"] for lst in data["lists"]}

# Count cards per list (exclude archived cards)
counter = Counter()
for card in data["cards"]:
    if not card.get("closed"):
        list_id = card["idList"]
        list_name = list_names.get(list_id, f"Unknown ({list_id})")
        counter[list_name] += 1

# List order preserved from board
list_order = [lst["name"] for lst in sorted(data["lists"], key=lambda x: x["pos"])]

run_date = date.today().strftime("%d-%b-%Y")

# --- Styles ---
BLUE        = "1F4E79"   # dark blue
LIGHT_BLUE  = "BDD7EE"   # light blue for column header
YELLOW      = "FFD966"   # total row
WHITE       = "FFFFFF"

# --- Build workbook ---
wb = Workbook()
ws = wb.active
ws.title = "Weekly Status"

# Row 1: Title
ws.merge_cells("A1:B1")
title_cell = ws["A1"]
title_cell.value = "Rasrich Tax LLC - 2026 Weekly Status Updates"
title_cell.font = Font(bold=True, size=14, color=WHITE)
title_cell.fill = PatternFill("solid", fgColor=BLUE)
title_cell.alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 24

# Row 2: blank spacer
ws.row_dimensions[2].height = 6

# Row 3: Column headers
for col, val in enumerate(["List", run_date], start=1):
    cell = ws.cell(row=3, column=col, value=val)
    cell.font = Font(bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=BLUE)
    cell.alignment = Alignment(horizontal="center" if col == 2 else "left")

# Rows 4+: Data
for i, name in enumerate(list_order):
    row = 4 + i
    count = counter.get(name, 0)
    name_cell  = ws.cell(row=row, column=1, value=name)
    count_cell = ws.cell(row=row, column=2, value=count)
    # Alternate row shading
    if i % 2 == 0:
        for cell in [name_cell, count_cell]:
            cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
    count_cell.alignment = Alignment(horizontal="center")

# Total row
total_row = 4 + len(list_order)
total_name = ws.cell(row=total_row, column=1, value="TOTAL")
total_count = ws.cell(row=total_row, column=2, value=sum(counter.values()))
for cell in [total_name, total_count]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor=YELLOW)
total_count.alignment = Alignment(horizontal="center")

# Column widths
ws.column_dimensions["A"].width = 42
ws.column_dimensions["B"].width = 14

# --- Bar Chart ---
chart = BarChart()
chart.type = "bar"          # horizontal bars — easier to read long list names
chart.grouping = "clustered"
chart.title = f"Cards per List — {run_date}"
chart.y_axis.title = "List"
chart.x_axis.title = "Card Count"
chart.legend = None
chart.style = 10

# Data: counts column (B), rows 4 to 4+len(list_order)-1 (exclude total row)
data_ref = Reference(ws, min_col=2, min_row=3, max_row=3 + len(list_order))
cats_ref = Reference(ws, min_col=1, min_row=4, max_row=3 + len(list_order))
chart.add_data(data_ref, titles_from_data=True)
chart.set_categories(cats_ref)

chart.width = 22
chart.height = 14

ws.add_chart(chart, "D1")

wb.save(OUTPUT_FILE)

# Console summary
print(f"Done — {OUTPUT_FILE}")
print()
print(f"{'List':<35} {'Count':>6}")
print("-" * 43)
for name in list_order:
    print(f"{name:<35} {counter.get(name, 0):>6}")
print("-" * 43)
print(f"{'TOTAL':<35} {sum(counter.values()):>6}")
