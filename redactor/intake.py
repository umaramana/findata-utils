"""Paste-friendly terminal intake of one client's redaction entries (names, addresses, DOBs, phones, emails).

Used by review/redact.py --prompt and diag_redact.py --prompt. Nothing typed is saved or echoed back in full.
"""
import re

try:
    from .redact import classify_entry  # imported as redactor.intake
except ImportError:
    from redact import classify_entry  # run from this folder

KIND_LABEL = {"name": "name/address", "dob": "DOB", "phone": "phone", "email": "email", "number": "account no.",
              "ssn": "SSN"}


def mask(entry):
    """Enough to spot a typo, not enough to read: first letter of each word, every other letter *, digits #."""
    return re.sub(r"\d", "#", re.sub(r"(?<=[A-Za-z])[A-Za-z]", "*", entry))


def read_entries(prompt="  > "):
    """Read lines until END (any case) or Ctrl-D. One entry per line; a tab also separates entries (a row
    copied from a spreadsheet), so does a line break inside a paste. Blank lines are skipped, so a pasted
    block with gaps is read whole. Commas do NOT split: "Smith, Jane" and addresses contain them.
    Returns (entries, ssns) - an SSN typed or pasted here is moved to ssns."""
    entries, ssns = [], []
    while True:
        try:
            line = input(prompt)
        except EOFError:
            break
        parts = [p.strip() for p in line.split("\t")]
        if any(p.upper() == "END" for p in parts):
            parts = parts[:[p.upper() for p in parts].index("END")]
            done = True
        else:
            done = False
        for p in filter(None, parts):
            (ssns if classify_entry(p)[0] == "ssn" else entries).append(p)
        if done:
            break
    return entries, ssns


def summary_lines(entries, n_ssns):
    """Masked, numbered list of what was entered, one line per entry, plus a totals line."""
    kinds = [classify_entry(e)[0] for e in entries]
    lines = [f"  {i:>2}  {KIND_LABEL[k]:<13} {mask(e)}" + ("   (every email is redacted anyway)" if k == "email" else "")
             for i, (k, e) in enumerate(zip(kinds, entries), 1)]
    totals = ", ".join(f"{kinds.count(k)} {KIND_LABEL[k]}" for k in ("name", "dob", "phone", "number", "email") if k in kinds)
    lines.append(f"  Total: {totals or 'nothing'}; {n_ssns} SSN(s)")
    return lines


INSTRUCTIONS = ("Paste or type one item per line: names (every written form), addresses (incl. India), dates of\n"
                "birth, phone numbers, account numbers. Tabs split items too (a spreadsheet row). Blank lines are ignored.\n"
                "Type END on its own line when done.")
