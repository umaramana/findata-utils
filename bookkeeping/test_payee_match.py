"""
Synthetic tests for payee_match (Phase 2). Invented vendor names only; never real lookup files.
Run: python bookkeeping/test_payee_match.py           (tests)
     python bookkeeping/test_payee_match.py --report  (threshold table -> bookkeeping/diag_output/)
"""
import hashlib
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_extractor as ce  # noqa: E402
import payee_match as pm  # noqa: E402

# collisions on purpose: two ACME vendors share a word, KLMN/KLAX are short look-alikes
VENDORS = ["KLMN", "KLAX", "ACME SUPPLY CO NC", "ACME PLUMBING LLC", "BRAVO FOODS INC",
           "ZENTRIX LOGISTICS", "OMNI PAPER", "DELTA ICE CO", "SUNRISE PRODUCE", "NORTHSIDE GAS"]
NON_VENDORS = ["PETTY CASH", "JOHN SMITH", "CITY WATER DEPT", "CASH", "PAYROLL", "STATE BOARD",
               "MARIA LOPEZ", "QUICK LUBE"]

# handwriting-style misreads, the shape seen on the 17-check sample
MISREADS = [
    ("KLMB", "KLMN"), ("KAL MB", "KLMN"), ("KLNB", "KLMN"), ("klmn", "KLMN"), ("K L M N", "KLMN"),
    ("KLAK", "KLAX"), ("ACME SUPPLY", "ACME SUPPLY CO NC"), ("Acme Suply", "ACME SUPPLY CO NC"),
    ("ACME PLUMBNG", "ACME PLUMBING LLC"), ("Acme Plumbing", "ACME PLUMBING LLC"),
    ("BRAVD FODS", "BRAVO FOODS INC"), ("Bravo", "BRAVO FOODS INC"), ("ZENTRIK", "ZENTRIX LOGISTICS"),
    ("OMNl PAPFR", "OMNI PAPER"), ("Delta Ice", "DELTA ICE CO"), ("SUNRlSE PRODUCF", "SUNRISE PRODUCE"),
    ("NORTH SIDE GAS", "NORTHSIDE GAS"),
]

# visually confusable letters in handwriting OCR
CONFUSE = {"M": "NWH", "N": "MBHU", "B": "RDE", "O": "DQCU", "D": "OB", "I": "LT", "L": "IT", "E": "FC",
           "U": "VN", "V": "UY", "C": "GE", "G": "C", "R": "BK", "K": "RX", "H": "NM", "A": "R", "P": "R",
           "T": "I", "X": "K"}
AZ = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def mutate(s, rng, k):
    """k random edits: confusable substitution, drop, insert, or a split."""
    s = list(s)
    for _ in range(k):
        op = rng.choice("sssdi ")
        idx = [i for i, c in enumerate(s) if c != " "]
        i = rng.choice(idx)
        if op == "s":
            s[i] = rng.choice(CONFUSE.get(s[i]) or AZ)
        elif op == "d" and len(idx) > 3:
            del s[i]
        elif op == "i":
            s.insert(i, rng.choice(AZ))
        elif op == " ":
            s.insert(i, " ")
    return "".join(s)


def variations(seed=7, per_vendor=40):
    """(ocr_text, true_vendor) misreads; true_vendor None for payees that aren't vendors."""
    rng = random.Random(seed)
    out = []
    for v in VENDORS:
        for _ in range(per_vendor):
            t = v.split()
            written = " ".join(t[:rng.choice([1, len(t)])])  # often only the first word is written
            # ~1 edit per 3 letters at most: beyond that no text matcher can recover the name
            k = min(rng.choice([1, 1, 2, 2, 3]), max(1, len(written.replace(" ", "")) // 3))
            out.append((mutate(written, rng, k), v))
    out += [(n, None) for n in NON_VENDORS]
    out += [(mutate(n, rng, 1), None) for n in NON_VENDORS for _ in range(5)]
    return out


def tally(matcher, cases, min_score, min_margin):
    right = wrong = flagged = neg_matched = 0
    for ocr, truth in cases:
        r = matcher.ranked(ocr)
        best, name = r[0]
        hit = best >= min_score and best - r[1][0] >= min_margin
        if truth is None:
            neg_matched += hit
        elif not hit:
            flagged += 1
        elif name == truth:
            right += 1
        else:
            wrong += 1
    return right, wrong, flagged, neg_matched


def report():
    m, cases = pm.PayeeMatcher(VENDORS), variations()
    n_neg = sum(t is None for _, t in cases)
    lines = [f"{len(cases) - n_neg} misreads of {len(VENDORS)} invented vendors, {n_neg} non-vendor payees",
             "min_score margin | right wrong flagged | non-vendors matched"]
    for s in (0.45, 0.5, 0.55, 0.6, 0.65, 0.7):
        for g in (0.0, 0.05, 0.1, 0.15):
            r, w, f, n = tally(m, cases, s, g)
            mark = "  <- locked" if (s, g) == (pm.MIN_SCORE, pm.MIN_MARGIN) else ""
            lines.append(f"{s:9} {g:6} | {r:5} {w:5} {f:7} | {n}/{n_neg}{mark}")
    out = Path(__file__).parent / "diag_output" / "payee_thresholds.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwritten to {out}")


# ── Tests ─────────────────────────────────────────────────────────────────────

def check(cond, msg):
    if not cond:
        print("FAIL", msg)
    return 0 if cond else 1


def test_misreads():
    m, fails = pm.PayeeMatcher(VENDORS), 0
    for ocr, want in MISREADS:
        got = m.match(ocr)
        fails += check(got.vendor == want and got.kind == "fuzzy", f"{ocr!r} -> {got} (want {want})")
    return fails


def test_collisions():
    m, fails = pm.PayeeMatcher(VENDORS), 0
    fails += check(m.match("ACME").kind == "none", "'ACME' with two ACME vendors must be flagged")
    fails += check(m.match("KLMN").vendor == "KLMN", "exact short name")
    fails += check(m.match("KLAX").vendor == "KLAX", "exact short look-alike")
    fails += check(m.match("KL").kind == "none", "too short to tell KLMN from KLAX")
    for n in NON_VENDORS:
        fails += check(m.match(n).kind == "none", f"non-vendor {n!r} matched {m.match(n).vendor!r}")
    # bank-style name with extra tokens, handwriting has the first word only
    solo = pm.PayeeMatcher(["ACME SUPPLY CO NC", "BRAVO FOODS INC"])
    fails += check(solo.match("ACME").vendor == "ACME SUPPLY CO NC", "first word of a bank-style name")
    fails += check(solo.match("").kind == "none", "empty payee")
    # same vendor in two spellings: first exact name wins, no self-collision
    dup = pm.PayeeMatcher(["Acme Supply", "ACME SUPPLY", "KLMN"])
    fails += check(dup.match("ACME SUPLY").vendor == "Acme Supply", "case-duplicate vendors")
    return fails


def test_thresholds():
    """The locked thresholds must keep the property they were chosen for."""
    r, w, f, n = tally(pm.PayeeMatcher(VENDORS), variations(), pm.MIN_SCORE, pm.MIN_MARGIN)
    fails = check(w == 0, f"{w} wrong vendor matches at locked thresholds")
    fails += check(n == 0, f"{n} non-vendors matched at locked thresholds")
    fails += check(r >= 350, f"only {r}/400 misreads matched")
    return fails


def test_aliases_and_files():
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        tagger = pm.lookup_path("demo", d)
        tagger.write_text("vendor_name,tag,subcategory,source,date_tagged\n"
                          "KLMN,COGS,,user,2026-01-01\nACME SUPPLY CO NC,Supplies,,claude,2026-01-01\n"
                          "OMNI PAPER,Supplies,,user,2026-01-01\n")
        before = hashlib.sha256(tagger.read_bytes()).hexdigest()
        fails += check(pm.list_clients(d) == ["demo"], "list_clients")
        m = pm.load_matcher("demo", d)
        fails += check(m.match("XQZW").kind == "none", "unreadable payee not matched")
        n = pm.save_aliases("demo", [("xq zw!", "OMNI PAPER"), ("KLMB", "KLMN"), ("", "KLMN"), ("ZZ", "")], d)
        fails += check(n == 2, f"saved {n}, want 2 (blank OCR/vendor skipped)")
        pm.save_aliases("demo", [("XQZW", "KLMN")], d)  # re-correction replaces, no duplicate row
        aliases = pm.load_aliases("demo", d)
        fails += check(aliases == {"XQ ZW": "OMNI PAPER", "KLMB": "KLMN", "XQZW": "KLMN"}, f"aliases {aliases}")
        m = pm.load_matcher("demo", d)
        got = m.match("Xq-Zw")
        fails += check(got.kind == "alias" and got.vendor == "OMNI PAPER", f"alias hit {got}")
        # an alias to a vendor not in the tagger list still joins the fuzzy pool
        pm.save_aliases("demo", [("SNRSE", "SUNRISE PRODUCE")], d)
        fails += check(pm.load_matcher("demo", d).match("SUNRISE PRODUC").vendor == "SUNRISE PRODUCE",
                       "alias-only vendor fuzzy match")
        fails += check(hashlib.sha256(tagger.read_bytes()).hexdigest() == before, "tagger lookup changed")
        fails += check(sorted(p.name for p in Path(d).iterdir()) == ["demo_check_aliases.csv", "demo_lookup.csv"],
                       "unexpected files in lookups dir")
        fails += check(pm.load_matcher("nobody", d).match("KLMN").kind == "none", "unknown client = no vendors")
    return fails


def test_rows():
    """No client = Phase 1 rows unchanged; with a client = Payee (OCR) column, flags, alias confidence."""
    chk = ce.CheckImage("a.pdf", 1, 1, None)
    base = {"check_no": "101", "date": "01/02/2026", "amount": 50.0, "payee": "KLMB", "purpose": "",
            "raw_text": "x", "printed": 3, "value_conf": 0.5, "amount_conf": 0.9}
    fails = 0
    plain = ce.build_row(chk, dict(base))
    fails += check(list(plain) == ["Source", "Page", "Check #", "Check No.", "Date", "Amount", "Payee",
                                   "Purpose", "Confidence", "Flag"], f"no-client columns {list(plain)}")
    fails += check(plain["Payee"] == "KLMB" and plain["Confidence"] == "LOW", "no-client row changed")

    m = pm.PayeeMatcher(VENDORS, {"KLMB": "KLMN"})
    f = dict(base)
    ce.apply_payee_match(f, m)
    row = ce.build_row(chk, f)
    fails += check(row["Payee"] == "KLMN" and row["Payee (OCR)"] == "KLMB", f"alias row {row}")
    fails += check(row["Confidence"] == "HIGH" and not row["Flag"], "alias hit -> payee conf HIGH")

    f = dict(base, payee="KLNB")
    ce.apply_payee_match(f, m)
    row = ce.build_row(chk, f)
    fails += check(row["Payee"] == "KLMN" and row["Confidence"] == "LOW", "fuzzy match keeps OCR grading")

    f = dict(base, payee="PETTY CASH", value_conf=0.95)
    ce.apply_payee_match(f, m)
    row = ce.build_row(chk, f)
    fails += check(row["Payee"] == "PETTY CASH" and row["Confidence"] == "HIGH" and row["Flag"],
                   "unmatched payee keeps OCR text and is flagged")

    single = dict(base, printed=0, payee="KLMB", value_conf=0.5, amount_conf=0.9)
    ce.apply_payee_match(single, m)
    fails += check(single["value_conf"] == 0.9, "single check: alias leaves amount conf as the limit")
    return fails


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
        sys.exit(0)
    total = test_misreads() + test_collisions() + test_thresholds() + test_aliases_and_files() + test_rows()
    print("ALL PASS" if total == 0 else f"{total} FAILURE(S)")
    sys.exit(1 if total else 0)
