# Trello List Pivot — Weekly Saturday routine
# Usage: drop the latest Trello board export JSON into this folder,
#        update JSON_FILE below if the filename changed, then run:
#        python trello_pivot.py
# Output: trello_list_pivot.csv — import into Google Sheets manually

import json
import csv
from collections import Counter
from datetime import date

JSON_FILE = "V1jGClbh - rasrichtaxteam-2026 (1).json"
OUTPUT_FILE = "trello_list_pivot.csv"

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

# Write CSV sorted by list position (preserve board order)
list_order = [lst["name"] for lst in sorted(data["lists"], key=lambda x: x["pos"])]

run_date = date.today().strftime("%d-%b-%Y")

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Rasrich Tax LLC - 2026 Weekly Status Updates"])
    writer.writerow([])
    writer.writerow(["List", run_date])
    for name in list_order:
        writer.writerow([name, counter.get(name, 0)])
    writer.writerow(["TOTAL", sum(counter.values())])

print(f"Done — {OUTPUT_FILE}")
print()
print(f"{'List':<35} {'Count':>6}")
print("-" * 43)
for name in list_order:
    print(f"{name:<35} {counter.get(name, 0):>6}")
print("-" * 43)
print(f"{'TOTAL':<35} {sum(counter.values()):>6}")
