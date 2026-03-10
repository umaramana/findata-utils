# Trello List Pivot — Weekly Saturday routine
# Usage: drop the latest Trello board export JSON into this folder,
#        update JSON_FILE below if the filename changed, then run:
#        python trello_pivot.py
# Output: trello_list_pivot.xlsx — one file, new date column added each week

import json
import os
from collections import Counter
from datetime import date
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.text import RichText
from openpyxl.drawing.text import RichTextProperties

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
BLUE       = "1F4E79"
LIGHT_BLUE = "BDD7EE"
YELLOW     = "FFD966"
WHITE      = "FFFFFF"

# --- Load existing or create new workbook ---
if os.path.exists(OUTPUT_FILE):
    wb = load_workbook(OUTPUT_FILE)
    ws = wb["Weekly Status"]
    # Guard: skip if this date was already written
    existing_dates = [ws.cell(row=3, column=c).value for c in range(2, ws.max_column + 1)]
    if run_date in existing_dates:
        print(f"Already recorded {run_date} — nothing to do.")
        exit(0)
    # Find next empty data column (after col A)
    new_col = ws.max_column + 1
else:
    wb = Workbook()
    ws = wb.active
    ws.title = "Weekly Status"
    new_col = 2

    # Row 1: Title — span will be extended each week via merge
    ws["A1"].value = "Rasrich Tax LLC - 2026 Weekly Status Updates"
    ws["A1"].font = Font(bold=True, size=14, color=WHITE)
    ws["A1"].fill = PatternFill("solid", fgColor=BLUE)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    # Row 2: blank spacer
    ws.row_dimensions[2].height = 6

    # Row 3 col A: "List" header
    cell = ws.cell(row=3, column=1, value="List")
    cell.font = Font(bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=BLUE)

    # Rows 4+: list names + total
    for i, name in enumerate(list_order):
        ws.cell(row=4 + i, column=1, value=name)
    ws.cell(row=4 + len(list_order), column=1, value="TOTAL")
    ws.column_dimensions["A"].width = 42

# --- Add this week's column ---
# Header (row 3)
hdr = ws.cell(row=3, column=new_col, value=run_date)
hdr.font = Font(bold=True, color=WHITE)
hdr.fill = PatternFill("solid", fgColor=BLUE)
hdr.alignment = Alignment(horizontal="center")

# Data rows
for i, name in enumerate(list_order):
    row = 4 + i
    count = counter.get(name, 0)
    name_cell  = ws.cell(row=row, column=1)
    count_cell = ws.cell(row=row, column=new_col, value=count)
    if i % 2 == 0:
        name_cell.fill  = PatternFill("solid", fgColor=LIGHT_BLUE)
        count_cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
    count_cell.alignment = Alignment(horizontal="center")

# Total row
total_row = 4 + len(list_order)
total_name  = ws.cell(row=total_row, column=1)
total_count = ws.cell(row=total_row, column=new_col, value=sum(counter.values()))
for cell in [total_name, total_count]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor=YELLOW)
total_count.alignment = Alignment(horizontal="center")

# Column width for new date column
from openpyxl.utils import get_column_letter
ws.column_dimensions[get_column_letter(new_col)].width = 14

# Re-merge title row across all data columns
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=new_col)

# --- Rebuild bar chart (all weeks) ---
# Remove existing charts
ws._charts = []

num_weeks = new_col - 1  # number of date columns
chart = BarChart()
chart.type = "col"
chart.grouping = "clustered"
chart.title = "Cards per List — Weekly"
chart.x_axis.title = "List"
chart.y_axis.title = "Card Count"
chart.style = 10
# Fix axis positions for column chart (openpyxl defaults to horizontal bar positions)
chart.x_axis.axPos = "b"  # category axis at bottom
chart.y_axis.axPos = "l"  # value axis at left
# Data labels: show values only
chart.dLbls = DataLabelList()
chart.dLbls.showVal = True
chart.dLbls.showSerName = False
chart.dLbls.showCatName = False
# Rotate category axis labels vertically
chart.x_axis.txPr = RichText(bodyPr=RichTextProperties(rot=-5400000))

# Data: all date columns (cols 2 to new_col), rows 3 to 3+len(list_order)
data_ref = Reference(ws, min_col=2, max_col=new_col, min_row=3, max_row=3 + len(list_order))
cats_ref = Reference(ws, min_col=1, min_row=4, max_row=3 + len(list_order))
chart.add_data(data_ref, titles_from_data=True)
chart.set_categories(cats_ref)

chart.width  = 30
chart.height = 14

# Place chart to the right of the data
chart_col = get_column_letter(new_col + 2)
ws.add_chart(chart, f"{chart_col}1")

wb.save(OUTPUT_FILE)

# Console summary
print(f"Done — {OUTPUT_FILE} (week {num_weeks})")
print()
print(f"{'List':<35} {'Count':>6}")
print("-" * 43)
for name in list_order:
    print(f"{name:<35} {counter.get(name, 0):>6}")
print("-" * 43)
print(f"{'TOTAL':<35} {sum(counter.values()):>6}")
