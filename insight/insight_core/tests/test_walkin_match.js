// Run: node tests/test_walkin_match.js
// Extracts the pure matching block from Code.gs (between its marker comments)
// and checks the dedupe decision table, incl. the shared-phone case.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const gs = fs.readFileSync(path.join(__dirname, "..", "apps_script", "Code.gs"), "utf8");
const a = gs.indexOf("// ---- walk-in duplicate matching");
const b = gs.indexOf("// ---- end walk-in duplicate matching ----");
assert(a > 0 && b > a, "marker comments not found in Code.gs");
const lib = new Function(
  gs.slice(a, b) +
    "; return { _normPhone, _normName, _namesSimilar, _classifyWalkinMatch };"
)();

// Syntax of the whole Apps Script file and of the page script.
new Function(gs);
const html = fs.readFileSync(path.join(__dirname, "..", "apps_script", "index.html"), "utf8");
[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].forEach((m) => new Function(m[1]));

const row = (n, name, phone, date) => ({ row: n, name, phone, date });
const kind = (existing, entry) => lib._classifyWalkinMatch(existing, entry).kind;
let n = 0;
const t = (label, got, want) => {
  assert.strictEqual(got, want, label + ": got " + got + ", want " + want);
  n++;
};

const ex = [row(2, "Ravi Kumar", "98765 43210", "2026-10-01")];

t("exact: same phone/name/date", kind(ex, { name: "ravi  kumar", phone: "+91 9876543210", date: "2026-10-01" }), "exact");
t("same person, other date warns", kind(ex, { name: "Ravi Kumar", phone: "9876543210", date: "2026-10-05" }), "same_person_other_date");
t("shared phone, different name -> new", kind(ex, { name: "Meena S", phone: "9876543210", date: "2026-10-01" }), "new");
t("shared phone, different name other date -> new", kind(ex, { name: "Meena S", phone: "9876543210", date: "2026-10-09" }), "new");
t("token-subset name warns", kind(ex, { name: "Ravi", phone: "9876543210", date: "2026-10-01" }), "similar_name");
t("typo name warns", kind(ex, { name: "Ravi Kumer", phone: "9876543210", date: "2026-10-01" }), "similar_name");
t("same name other phone warns", kind(ex, { name: "Ravi Kumar", phone: "9111111111", date: "2026-10-01" }), "same_name_other_phone");
t("nothing in common -> new", kind(ex, { name: "Anil", phone: "9222222222", date: "2026-10-01" }), "new");
t("empty sheet -> new", kind([], { name: "Anil", phone: "9222222222", date: "2026-10-01" }), "new");

// Two people share a phone: exact re-entry of the SECOND person must hit the
// second person's row, never overwrite the first.
const shared = [
  row(2, "Ravi Kumar", "9876543210", "2026-10-01"),
  row(3, "Meena S", "9876543210", "2026-10-01"),
];
const r = lib._classifyWalkinMatch(shared, { name: "Meena S", phone: "9876543210", date: "2026-10-01" });
t("shared phone exact -> second person", r.kind, "exact");
t("shared phone exact targets row 3", r.match.row, 3);
t("third person on shared phone -> new", kind(shared, { name: "Lakshmi", phone: "9876543210", date: "2026-10-01" }), "new");

// Exact outranks a weaker match regardless of row order.
const mixed = [
  row(2, "Ravi Kumar", "9876543210", "2026-10-01"),
  row(3, "Ravi Kumar", "9876543210", "2026-09-01"),
];
t("exact beats other-date", lib._classifyWalkinMatch(mixed, { name: "Ravi Kumar", phone: "9876543210", date: "2026-10-01" }).match.row, 2);

// Blank phone must never produce a phone match.
t("blank phones don't match", kind([row(2, "A One", "", "2026-10-01")], { name: "B Two", phone: "", date: "2026-10-01" }), "new");

console.log("walkin match: " + n + " checks passed");
