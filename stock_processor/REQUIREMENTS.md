# Stock Transaction Processor — Requirements Summary

## General
- **Purpose**: Convert broker 1099-B files (Excel via PDF24, or native CSV) to Drake tax software import format
- **Output**: 15-column Drake format
  - Populated: Desc, Date Acquired, Date Sold, Proceeds, Cost, Accrued Discount, Wash Sale Loss
  - Conditionally populated: Type (S/L — populated when broker provides term type data)
  - Empty: TSJ, F, State, City, Form 8949 Check Box, Ordinary, AMT Cost Basis
- **UI**: Streamlit web app — broker selection, file upload (CSV or Excel), QC report, preview, download
- **File types**: `.xlsx`, `.xls`, `.csv` accepted for all brokers
- **QC Module** (`pdf_qc.py`): Auto-detects and corrects column misalignment from PDF24 conversion
  - **Pass 1 — Right-shift detection** (existing): Date pattern validation per row against header anchor. If date found right of expected position, shifts Part 2 values left to re-align.
  - **Pass 2 — Left-shift / collapse reconciliation** (new): Header-vs-data position check for each anchor column (Date Acquired, Gain/Loss, Fed Tax). If anchor is empty at expected position but found one position left, shifts it right. Universal across all Excel brokers.
  - Anchors: Date Acquired, Cost, Gain/Loss, Fed Tax (optional) — positions per broker in `BROKER_CONFIG`
  - Header row detection: highest keyword match count in first 10 rows
  - **Skipped automatically for CSV brokers** (no PDF24 artifacts possible)
- **Broker Profiler** (`broker_profiler.py`): Standalone analysis tool for new broker files
  - Run: `python broker_profiler.py <file.xlsx|file.csv> [sheet_name]`
  - Deep analysis: `python broker_profiler.py <file> --broker <key>` (e.g., `--broker jpmorgan`)
  - Outputs: column type profiles, row type distribution, detected anchors, similarity ranking vs existing brokers
  - Deep analysis adds: optional zone analysis, right-of-Gain/Loss scan, shift pattern detection, financial totals

## CSV vs Excel Brokers
- **Convention**: CSV brokers use `csv_` prefix in their broker key (e.g., `csv_betterment`)
- App detects `csv_` prefix → skips QC, shows "CSV file detected" info message
- No manual configuration needed — prefix is self-documenting

## Type Column (S/L)
- Drake expects `S` (short-term) or `L` (long-term) in the Type column
- `_normalize_type()` in `drake_mapper.py` handles any broker's source format:
  - `Long-term`, `LONG`, `long` → `L`
  - `Short-term`, `SHORT`, `short` → `S`
  - `L`, `S` → pass through
- To enable for a broker: add `'Type': 'Type'` to its entry in `BROKER_COLUMN_MAPPINGS`
- Currently populated: Betterment

## Broker-Specific

| | Fidelity | Charles Schwab | Robinhood | Merrill Lynch | Morgan Stanley | Betterment | Apex Clearing | JP Morgan | Pershing LLC |
|---|---|---|---|---|---|---|---|---|---|
| **Status** | Complete | Complete | Complete | Complete | Complete | Complete | Complete | Complete | Complete |
| **File type** | Excel | Excel | Excel | Excel | Excel | CSV | Excel | Excel (via Excel PDF import) | Excel (native) |
| **Date Acq col** | 2 | 4 (paired row) | 3 | 2 | 2 | 3 | 4 (falls back to 3 if shifted) | 5 | 2 |
| **Cost col** | 5 | 6 | 4 | 5 | 5 | 6 | 5 | 8 | 5 |
| **Gain/Loss col** | 8 | 8 | 6 | 8 | 8 | 7 | 7 | 11 | 8 (col 7 on 8-col sheets) |
| **Optional cols** | Accrued Mkt Discount, Wash Sale | Accrued/Wash merged (col 7) | Wash Sale | Accrued Mkt Discount, Wash Sale | Accrued Mkt Discount, Wash Sale | Wash Sale | 1f/1g merged (col 6) | Accrued Mkt Discount, Wash Sale | 1f/1g merged (col 6, D=/W= markers) |
| **Type (S/L)** | — | — | — | — | — | Yes (col 10) | — | — | — |
| **Fed Tax Withheld** | — | — | — | — | Yes (col 9) | Yes (col 9) | — | — | — |
| **QC** | Yes | Yes | Yes | Yes | Yes | Skipped (CSV) | Yes | Yes | Yes |
| **Left-shift handling** | Gain/Loss collapse (QC Pass 2) | Right-shift (QC Pass 1, 10-col sheets) | — | Dynamic date finding | Gain/Loss collapse (QC Pass 2) | N/A | DateAcq col4→3 (QC Pass 2) | Optional right-shift (broker-level fallback, pending Pass 3) | Variable col count (broker-level: 8-col vs 9-col) |

## Merrill-Specific Row Patterns
1. **Fully merged multi-tx**: All transactions in one row, `\n`-separated (e.g., AMAZON with 7 txns)
2. **Merged single-tx**: Description + first transaction merged in one row
3. **Description-only**: Stock name row, no financial data
4. **Continuation**: Multi-line description spanning rows (e.g., "CHARTER COMMUNICATIONS" + "INC SHS CL A")
5. **Transaction**: Standard row with dates and financials

## Merrill QC Issues (resolved)
- PDF24 splits wash sale values (e.g., "15.38(W)") into extra columns — Sheet3 has extra blank col in Part 2
- PDF24 adds blank columns in Part 1 on some sheets (Sheet6) — shifts Part 2 right
- NVIDIA merged row has Part 1 consuming extra column — per-row date validation corrects it

## Morgan Stanley Notes
- Description is on stock-name rows (col 0), empty on transaction rows — forward-filled including across sheet boundaries
- Col 9 = Fed Tax Withheld due to PDF24 merging col 8/9 header — expected artifact, not an error
- Column header rows repeat mid-sheet — detected (2+ header keywords) and skipped
- Row types: skip | stock_name | transaction | section header (single populated cell)

## Betterment Notes
- Native CSV export — no PDF24 conversion needed
- Row 0 is the clean header row; all remaining rows are transactions (no stock-name rows, subtotals, or section headers)
- Gain/Loss (col 7) appears BEFORE Wash Sale (col 8) — opposite of other brokers; safe since columns are read by fixed index
- Type of Gain(Loss) (col 10): `Long-term` / `Short-term` → normalized to `L` / `S` in Drake output

## Apex Clearing Notes
- PDF24-converted Excel, 2 sheets in test file (pages 3-4 of 7)
- **Row pairing**: Col 0 carries 1a (description on parent row) and 1c (date sold on child row) — similar to Fidelity's parent-child but col 0 is overloaded with different data types per row type
- **Column layout (data rows)**: Col 0=DateSold(1c), Col 1=Qty, Col 2=Proceeds(1d), Col 3=(no 1x header, artifact), Col 4=DateAcq(1b), Col 5=Cost(1e), Col 6=Accrued/WashSale(1f/1g merged), Col 7=Gain/Loss, Col 8=Additional Notes (Sheet1 only, Sheet2 has 8 cols)
- **Date format**: YYYY-MM-DD (unique among brokers — needs `_format_date()` pattern in drake_mapper.py)
- **Col 6 merged 1f/1g**: Header indicates "(M)" for Accrued Market Discount and "(D)" for Wash Sale Loss Disallowed as markers. Test data has 0 values only. Placeholder `_parse_accrued_wash_sale()` function — expand when non-zero test data available
- **Left-shift**: DateAcq expected at col 4 (per 1b header) but appears at col 3 in data. Handled by universal QC Pass 2.
- **Multi-row header**: Rows 7-10 span 4 rows with partial text per row; 1x IRS codes (1a-1g) identify real columns
- **Totals row**: End of last sheet ("Totals:" in col 0) — filter out
- **Expected totals** (from test file): 10 transactions, Proceeds=$3,192.70, Cost=$5,189.38

## QC Pass 2 — Universal Left-Shift Reconciliation
- **Purpose**: After Pass 1 (right-shift) corrects Part 2 being pushed right, Pass 2 corrects individual anchor columns that shifted left (empty cell collapse or PDF24 artifact columns)
- **Approach**: For each anchor (Date Acquired, Gain/Loss, Fed Tax), check if value is at expected position. If empty, check one position left. If found, move right.
- **Replaces**: Fidelity's broker-level `_fix_empty_cell_collapse()` (to be removed once regression-proven)
- **Transaction row guard**: Only check rows where Cost or Proceeds at expected position is non-empty (avoids false positives on description/header/footer rows)
- **BROKER_CONFIG additions**: `gain_loss_col_idx` and optional `fed_tax_col_idx` added per broker

## Transaction Tagger (Implemented — Sprint 1 + Sprint 2)

### Purpose
Multi-pass transaction tagger for tax preparers. Tags bank/CC transactions to expense categories using Claude AI + preparer review. Integrated as a page in the RASRICH Streamlit app (`tagger_page.py`).

### Input
- Excel or CSV (primary input: output of Tab Collator — single Master sheet)
- Required column: Description (preparer maps in Step 2)
- Optional columns: Amount (expense filtering), Date (monthly summary pivot)
- File may optionally contain a **Lookup tab** (sheet name containing "lookup", case-insensitive) with **Category** and/or **Subcategory** vocabulary columns (see below). Not mandatory — the tool works fine without one.

### Two-Level Taxonomy (Sprint 2, redesigned Sprint 3 — 2026-07-14)
| Field | Required? | Purpose | Example |
|---|---|---|---|
| **Category** | Yes | Generic IRS tax category (maps to form line) — controlled vocabulary from `docs/rasrich_tag_lists.csv` (52 tags) + any extra values from the file's Lookup tab | Insurance - General |
| **Subcategory** | No | Specific preparer working label, independent of Category | Health Insurance |

- **Category and Subcategory are independent fields with no fallback/derivation relationship between them.** ("Quick Tag" is retired as both a term and a mechanism — it used to double as the source of Subcategory via a fallback, which was the root cause of a subcategory-erasure bug fixed in this redesign.)
- Claude returns both `tag` and `subcategory` in each response when a vendor is unresolved by the preparer.
- **Lookup tab (in uploaded file)** — vocabulary only, read by `_load_lookup_tab_vocab()`. Supplies extra valid Category/Subcategory *option values* for this client's dropdowns. Column detection: Category column name in `{tag, tags, category, categories, expense tag, expense category}`; Subcategory column name in `{subcategory, sub category, sub-category, subcategories, specific tag}`. **Not a vendor mapping** — no vendor/description column is read from it, even if present.
- **Lookup CSV** (`stock_processor/lookups/{client_id}_lookup.csv`) — the actual vendor→Category→Subcategory mapping, sole source of truth for any vendor once it exists for that client. Both fields auto-fill independently from history on repeat runs (`_build_vendor_table`) — this is the fix: Subcategory no longer depends on the preparer re-touching a field that Category already resolved.
- Subcategory dropdown is constrained (not free text) to this client's historical values + Lookup tab vocabulary, to avoid fragmenting the `_summary_tag_rows` Tag→Subcategory grouping with typo variants.
- Summary pivot groups by Tag → Subcategory with subtotals.
- **Subcategory consistency across sources**: the Subcategory dropdown constraint (client history + Lookup tab vocab) only applies to the Step 3 vendor review table. Two other write paths are NOT dropdown-constrained by design: (1) Claude's own subcategory generation — instead, `_build_system_prompt()` is given the client's existing subcategory vocabulary (`_subcategory_vocab_for_prompt()`) with an instruction to reuse an existing label rather than invent a variant (e.g. prefer "Health Insurance" over "Medical Insurance" if already in use); (2) Step 4's `Preparer_Subcategory` (flagged/low-confidence vendor correction) stays free text (`TextColumn`) deliberately — that's the one screen where a preparer needs to be able to introduce a genuinely new subcategory for an edge-case vendor.

### Vendor Extraction (Sprint 2 — Multi-bank, PII-safe)
- Raw descriptions cleaned via `_extract_vendor()` before anything is sent to Claude
- **Objective**: strip transaction metadata only — keep vendor name + location intact as context for Claude
- **Two purchase formats detected by what follows the prefix:**
  - *Citibank*: `#NNNN card ref` marks end of metadata — strips abbrev+date+time, extracts merchant from `| MERCHANT | Category` structure
  - *Capital One*: `- MERCHANT` (dash-space after prefix) — takes everything after dash as merchant
- **PIN Purchase**: handled same as Card/Mobile Purchase
- **Garbled OCR prefixes** (e.g. `Bepit Card Purchase`): `\bPurchase\s*-\s*` transfer pattern extracts merchant
- **Withdrawal/Deposit from/to**: strips prefix, masks account number (`XXXXXX0018` → stripped)
- **Amazon subtypes**: `MARK*`, `RETA*`, `MKTPL*` — strips subtype+hash, keeps location
- **ACH Electronic Debit/Credit**: strips bank prefix, keeps vendor + details
- **Merchant prefixes**: `SQ*`, `SQSP*`, `TST*`, `FSI*`, `MSFT*`, `ZIP*` (and OCR variants) stripped
- **Citibank OCR artifacts**: `=`/`_` as space substitutes normalised; `NYUS05154` concatenated state+country+zip stripped
- **Capital One OCR artifacts**: commas normalised to spaces, trailing `, US` country code stripped
- **Bank transaction code prefix** (e.g. `OT Crpj`, `11 Sjq #5989`): short 2-char code + mixed-case ref word, stripped before merchant detection. Distinguishable from vendor names because bank codes use mixed case (`Crpj`, `Sjq`) while vendor names are all-caps in bank statements.
- **Auto-personal patterns**: ATM → "Personal - ATM", Bank Fee → "Personal - Bank Charges", etc.
- **Lookup tab detection**: sheet name contains "lookup" (case-insensitive); column name: tag/tags/quick tag/category. Warning shown if sheet found but column unrecognised.

### Tagging Mode (Step 1 toggle)
| Mode | Flow |
|---|---|
| **Review-first** (default) | Preparer tags in Step 3 → Claude fills gaps in Step 4 |
| **Pre-tag** | Claude tags all vendors after Step 2 (lookup CSV first, then API) → preparer reviews in Step 3 |

Pre-tag Step 3 shows two sections: collapsed expander for pre-tagged vendors (⚡ Auto / 📋 Lookup / 🤖 Claude source labels, editable) + main editor for vendors needing attention.

### UI Flow (5 Steps)
| Step | Name | Contents |
|---|---|---|
| 1 | Setup | Client ID, entity type, primary/secondary activity, confidence threshold, tagging mode |
| 2 | Upload | File upload, column mapping (description, amount, date), Lookup tab detection. In pre-tag mode: Claude API runs here with progress bar. |
| 3 | Preparer Review | Review-first: tag untagged vendors. Pre-tag: review/correct pre-filled tags in two sections. |
| 4 | Claude Tags | Claude Haiku tags remaining blank vendors; low-confidence surfaced for review |
| 5 | Output | Download tagged Excel (Tagged / Personal / Review with Client / Summary tabs) |

### Claude API Design
- Model: `claude-haiku-4-5`
- Batch size: 30 unique vendor names per API call
- System prompt: combined specific + generic tag list, client persona (entity type, primary/secondary activity), JSON-only response rule
- Response format per item: `{"id": int, "tag": "...", "subcategory": "...", "confidence": 0.0–1.0, "reason": "..."}`
- Per-vendor payload (Card A, 2026-08-07): `{id, vendor}` plus, when available, `amount_total`, `txn_count` (recurrence signal), `amount_sample` (single value or `min to max`), `date_span` (`Jan` or `Jan-Mar`). Vendor string stays the memory key unchanged. Built by `_vendor_stats(df, amount_col, date_col)`, threaded through `_run_claude_on_vendors(..., vendor_stats=None)` → `_tag_batch`.
- Client rules (Card A, 2026-08-07): optional `stock_processor/lookups/{client_id}_rules.txt`, one plain-English rule per line (`#`-prefixed = comment). Loaded by `_load_client_rules()`, injected into the system prompt by `_build_system_prompt(..., rules=...)` via `_client_rules_note()` — includes the apportionment boundary ("apply the rule to pick a tag, never compute an apportioned dollar amount") only when a rule is actually present, so an absent file leaves the prompt byte-identical to prior behavior. Gitignored under the same `stock_processor/lookups/` rule as the lookup CSV.
- Persona toggle (Card A/4.2, 2026-08-07): `_build_system_prompt(..., include_persona=True)` — `False` omits the "Client persona: ..." clause entirely. Exists as the eval harness's `persona-off` control arm, not used by the Streamlit app (always `True` there).

### Output File (Excel, 4 tabs)
- **Tagged**: All transactions with `Tag`, `Subcategory`, `Tag Source` (claude/preparer/rwc/income), `Confidence`, `Reason`
- **Personal**: Rows tagged "Personal - *"
- **Review with Client**: Unresolved rows
- **Summary**: Monthly pivot — rows = Tag/Subcategory (with subtotals per tag), columns = months present in data + Total. Includes Income and Grand Total rows. Falls back to non-monthly if no date column selected.

### Lookup Table (`stock_processor/lookups/{client_id}_lookup.csv`) — gitignored
- Columns: `vendor_name, tag, subcategory, source, date_tagged`
- Saved at end of each run; loaded at start of next run for exact-match pre-fill
- Subcategory persists across runs — grows organically as preparer vocabulary
- Per-client. Folder created automatically. Never committed to git (client data).

### Category/Subcategory Redesign (Implemented — Sprint 3, 2026-07-14)

Fixed the subcategory-erasure bug by making Category and Subcategory independent, both-persisted fields instead of Subcategory being a fallback derivation of a "Quick Tag" field. See the "Two-Level Taxonomy" section above for the current model, and [[project_rasrich_tagger]] memory for the investigation trail (root cause, RTS sample finding, design options considered).

Key functions: `_load_lookup_tab_vocab()` (Lookup tab vocabulary reader), `_get_category_options()` / `_get_subcategory_options()` (dropdown option builders), `_build_vendor_table()` + `_resolve_vendor_category/_subcategory/_source()` (per-vendor pre-fill from lookup CSV history), `_apply_all_tags()` (no fallback logic — each field maps 1:1 from its own review-table column).

### Tag_Source Taxonomy (Fixed — 2026-07-14; `auto`→`claude` renamed 2026-07-16, Phase 1 Card 1.2)
`Tag_Source` is a per-transaction-row field distinct from the vendor-table `Source` display badge (pretag mode only). Six values, each meaning exactly one thing:
| Value | Meaning |
|---|---|
| `lookup` | Vendor's Category/Subcategory exactly match lookup CSV history — an untouched carryover, no action taken this session |
| `preparer` | Vendor tagged/edited by the preparer this session — starting from blank, or overriding a lookup-suggested value |
| `claude` | Claude classified with confidence ≥ threshold, accepted without preparer review (renamed from `auto` 2026-07-16) |
| `flagged` | Claude classified below threshold — pending Step 4 preparer review |
| `rwc` | Resolved to "Review with Client" during Step 4 |
| `income` | Not an expense row — skipped entirely |

**Prior bug**: before this fix, `preparer` was overloaded — it fired for both a genuine preparer decision AND a vendor silently auto-resolved from lookup history that the preparer never touched, making the output's audit trail (and the re-saved lookup CSV `source` column) unable to distinguish the two. Fixed in `_build_prep_map()` (line ~562) by comparing the vendor table's Category/Subcategory against lookup CSV history at apply-time: an exact match → `lookup`; any difference (or vendor not in lookup at all) → `preparer`. `_collect_lookup_entries()` deliberately does NOT re-save `lookup`-sourced rows (they're unchanged — resaving would bump `date_tagged` for vendors nobody acted on, destroying the "when was this actually decided" signal). Step 4 and Step 5 summary displays updated to show a "From lookup history" count alongside the others — a prior partial fix would have silently dropped these rows from the on-screen totals.

**`auto`→`claude` rename (2026-07-16)**: `_load_lookup()` migrates any legacy `source=='auto'` rows in an existing lookup CSV to `'claude'` on load, so historical lookup CSVs stay compatible without a manual data migration.

### Vendor Memory Hit-Rate Line (Phase 1 Card 1.3, 2026-07-16)
Step 5 shows a one-line vendor-level (not row-level) summary via `_vendor_hit_rate_line(df)`: `Memory: 62/80 vendors (78%) · Claude: 18 · Preparer: 12`. Counts unique vendors, excludes income rows, folds `rwc` into the Preparer count. No log file, no orphan detection — that's Card 3.3 (Phase 3).

### Regression Suite
- **Location**: `stock_processor/test_tagger.py` — `python test_tagger.py` (all-synthetic data, no client files, no live Claude API calls). Filter: `python test_tagger.py vendor`. Verbose: `-v`.
- Imports `tagger_page.py` by stripping its module-level `render()` call before exec (Streamlit's `render()` needs a live ScriptRunContext and can't run in a plain script; every other top-level statement is a def/import, safe to exec).
- Lookup-CSV persistence tests redirect `tp._LOOKUPS_DIR` to a `tempfile.TemporaryDirectory()` for the duration of the test, then restore it — guarantees the suite never reads/writes the real `stock_processor/lookups/` directory (client data).
- Covers: vendor extraction, amount parsing, Lookup-tab vocabulary reading (including the "not a vendor mapping" boundary), lookup CSV round-trip/overwrite, and the full Category/Subcategory redesign — including `test_subcategory_erasure_bug_regression`, an explicit regression test for the 2026-07-14 bug fix. 36/36 as of 2026-07-16 (Phase 1: raw-description regression guard, `auto`→`claude` migration, vendor hit-rate line).
- Does not cover: Claude API calls (`_run_claude_on_vendors`, `_tag_batch`) or Streamlit UI rendering — both require live/interactive context outside this suite's scope.

### Vendor-Level Diff, Eval Harness, Enriched Prompt (Cards 3.5 / 4.2 / A — built 2026-08-07)

Three tools measuring and improving tagging accuracy against a real answer key. Built in dependency order 3.5 → A → 4.2 (not the specs' literal listing order) so 4.2's `--compare bare,enriched` measures Card A's real code on first run instead of a stub — see [[project_rasrich_tagger]] for the reasoning.

- **`stock_processor/tag_compare.py`** — shared core, imported by both tools below. `load_truth_csv()` (defaults `scope` to `vendor`), `aggregate_tagged_output()` (per-vendor Tag/Amount/Count), `compare_vendor_tags()` (inner-join tagged output ∩ truth), `score_accuracy()` (excludes `scope=='structural'` rows from the denominator, reports them separately as "out of tagger scope").
- **`stock_processor/vendor_diff.py`** (Card 3.5) — `python vendor_diff.py <client_id> <tagged-output.xlsx> <truth.csv> [--year YYYY] [--out-dir DIR]`. Produces 3 outputs in `stock_processor/evals/` (gitignored — client data): disagreement report (`{client_id}_diff_{year}.csv`, sorted by dollar impact), Vendor→Category seed (`{client_id}_seed_{year}.csv`) for one-off disagreements only, proposed rules (`{client_id}_rules_PROPOSED.txt`) for any (Tag, correct_category) pair remapped identically across ≥5 transactions. Ambiguous truth vendors (same vendor mapped to 2+ categories in the truth CSV — e.g. person-to-person transfers) are never seeded, logged as excluded instead. Proposed rules state only the literal observed tag pair ("X vendors are Y for this client") — no fabricated semantics (e.g. "credit-card") — preparer edits wording before promoting to `{client_id}_rules.txt`.
- **`stock_processor/eval_tagger.py`** (Card 4.2) — `python eval_tagger.py <client_id> <vendor-data-file> <answer-key.csv> [--config bare|enriched|persona-off|persona-on] [--compare configA,configB] [--api-key KEY]`. Imports `tagger_page.py`'s real `_build_system_prompt`/`_run_claude_on_vendors`/`_vendor_stats` (same render()-stripping exec trick as `test_tagger.py`) so it measures actual production behavior, not a re-implementation. Every config runs twice — `compute_drift()` reports the % of vendors whose tag changed between identical runs, so an accuracy gain that comes from prompt instability is visible, not hidden. `--compare` prints a side-by-side table (accuracy, misses, drift, "+N correct / M regressions" vs. the first-listed config) and writes full per-vendor detail to `{client_id}_{year}_eval_{timestamp}.csv`. Read-only over inputs — never writes to Vendor Memory/lookups.
- **Card A wiring**: see the Claude API Design section above for the enriched payload, client rules file, and persona toggle this harness exercises.
- **Tests**: `stock_processor/test_cards.py`, 20/20 green — `python test_cards.py [-v] [filter]`, same runner style as `test_tagger.py`. Covers the class-remap-vs-one-off-vs-ambiguous classification (Card 3.5), drift/scoring math (Card 4.2), and payload/rules/persona changes (Card A) including the "absent rules file → byte-identical prompt" regression caught during this build (an unconditional apportionment-boundary sentence was initially added to every prompt; moved inside `_client_rules_note()` so it only appears when a rule is actually present).
- **Not yet run**: the real Devlin 2025 acceptance pass (`--compare bare,enriched` against a `238300_2025_key.csv` built from the SIyer decode) — deferred to the user per this session's data-access decision (dataforrasrichtools is off-limits to Claude directly). Until that runs, Card A's enrichment is unvalidated in production — the tagger's default behavior when a client has no `_rules.txt` is unchanged, and enrichment only activates via `vendor_stats` being passed at the two real call sites (`_step2_run_pretag`, `_render_step4`'s Claude button) — i.e. it's live for real runs today even without a measured win. If the eventual eval shows no gain or excess drift, revisit whether enrichment should ship gated behind a config flag instead of being unconditional.
- **Workflow simplified after real use, same day (2026-08-07)**: after building 3.5/4.2's CSV-key/scoring workflow, live use against Devlin showed most of the disagreement (24/59 rows, likely more) is structural/judgment (941 splits, apportionment) that no vendor-level rule can fix — scoring it as "accuracy" mostly measured noise. **Decision: `vendor_diff.py`/`eval_tagger.py` are now secondary tools**, useful for a client whose errors are mechanical/vendor-level, not the primary path. The primary path for a new client/year is: preparer reads the filed return, writes corrections straight into `{client_id}_rules.txt` in plain English — no CSV key required. Confirmed generic (works for any client via the same file-naming convention), and confirmed to only matter for vendors *new* that year — a vendor already resolved from lookup-CSV history bypasses Claude (and therefore `rules.txt`) entirely; fixing an already-known-wrong vendor requires editing the lookup CSV directly, not the rules file.
- **Bug found and fixed same day via live debugging on Devlin 2025 data**: client rules initially had no effect in a real Pre-Tag run (98 vendors) despite loading correctly and working in isolated single-vendor tests, including with the enriched payload. Root cause: rules make Claude quote the full rule text back in each vendor's `"reason"` field; across a real 30-vendor batch (`_BATCH_SIZE`), several rule-matching vendors' verbose reasons could push the JSON response past the `max_tokens=2048` cap, truncating it mid-response. A truncated response fails `json.loads()`, tripping `_run_claude_on_vendors`'s `except Exception` fallback — which silently sets **every vendor in that entire batch** to `{'tag': 'Review with Client', 'confidence': 0.0, 'reason': 'API error: ...'}`, masked because the fallback shares the same `'🤖 Claude'` source label as a genuine response, so it's indistinguishable in the UI without checking the Confidence/Reason columns. **Fixed**: `max_tokens` raised 2048→4096; `reason` capped to under 12 words with an explicit instruction not to quote rule text back. Not yet re-verified on the remote (user ran out of time this session — confirm on next run: AmEx, Mek Financial, Figlia, Squarespace, Amazon/Home Depot should all resolve per their rules instead of Review with Client). [[feedback_debug_before_defend]] pattern: root-caused via isolated single-vendor test (proved the mechanism worked) → isolated test with enriched payload (ruled that out) → batch-size/token-budget reasoning (found it) — never accepted "it's probably fine" at any step.

### Sprint 3+ (Out of Scope)
- True pivot table summary (Tag as single row, months as pure value columns)
- Lookup CSV subcategory seeding for new clients from prior client patterns
- Google Places API vendor geo-enrichment
- Multi-year / firm-wide lookup option

## Chase Bank Statement OCR Extractor (`bankdetails_dataextraction/extract_chase_txns.py`)

### Purpose
Extracts transactions from scanned Chase checking statement images using Tesseract OCR. Reconciles extracted totals against printed section totals. Outputs a clean CSV ready for the Transaction Tagger.

### How to Run
```bash
python extract_chase_txns.py "path/to/images/folder" --output result.csv
```
Input: folder of JPG/PNG images (one per page, extracted from PDF via PDF24).

### Output CSV Columns
`statement_period, date, description, subtracted, added, balance, flag, source_page`

### Sections Recognised
| Section | Sign | Total keyword matched |
|---|---|---|
| Deposits and Additions | + | `DEPOSITS AND ADDITIONS` / `DEPOSITS & ADDITIONS` |
| Checks Paid | − | `CHECKS PAID` |
| ATM & Debit Card Withdrawals | − | `ATM & DEBIT` (strict — avoids sub-total double-count) |
| Electronic Withdrawals | − | `ELECTRONIC WITHDRAWALS` |
| Other Withdrawals | − | `OTHER WITHDRAWAL` |
| Service Fees | − | `SERVICE FEE` |
| Fees | − | `FEES` |

### Reconciliation Logic
- **BTP-1**: If extracted total > printed total by exactly one row's amount → phantom row removed
- **BTP-2**: If gap remains after BTP-1 → `*** MISSING ROWS ***` sentinel row inserted with gap amount
- Sub-section totals (e.g., "Total ATM Withdrawals & Debits") are excluded via `_TOTAL_KEYWORDS` strict matching

### Dependencies
- `pytesseract==0.3.13`, `Pillow==11.1.0`
- Tesseract OCR binary at `C:\Program Files\Tesseract-OCR\tesseract.exe`

### Known Gaps (Parking Lot)
- Dec/Sep Electronic Withdrawals: $1,363.25 gap (same amount both months — specific transaction type not yet parsed)
- Small residual gaps in Checks and Fees: genuine OCR misses, low priority

## Wealthfront Notes
- **Status**: Pending — test file profiled, module not yet built.
- **Test file**: `testdata/wealthfront_1099 test jl 2024.xlsx` — sheets: Sheet3, Sheet4
- **Layout (7-col)**: Col 0=Description/Date Sold (mixed), 1=Qty, 2=Proceeds, 3=Date Acquired, 4=Cost, 5=1f/1g merged (Accrued + Wash Sale), 6=Gain/Loss
- **Closest match**: Robinhood (same description-then-data-row pattern, same 1f/1g merged single cell). Key difference: Robinhood has 8 cols with standalone Date Sold col; Wealthfront has 7 cols with Date Sold in col 0 of the data row.
- **Next closest**: Fidelity (per visual inspection)
- **Build approach**: Start from Robinhood module, adjust col indices, handle Date Sold extraction from col 0.

## Parking Lot
- **Subtotal aggregation per stock**: Roll up transactions per security for summary view
- **Summary Page QC + QC Pass 3**: Scan summary/totals rows for expected totals (Proceeds, Cost, Accrued, Wash Sale). Compare against processed output. If optional totals mismatch → trigger Pass 3 (scan right of Gain/Loss, pull shifted optional values back). This replaces broker-level shift workarounds (e.g., jpmorgan.py cols 13-14 fallback). Sequence: Summary scan → Pass 1+2 → broker processing → total comparison → Pass 3 if needed. See `stock_processor_qc.md` for full per-broker analysis of what's right of Gain/Loss and false-positive risks.
- **Proceeds gap investigation (Merrill)**: 96 transactions extracted, total proceeds $43,898.49 vs expected $48,538.58 (~$4,640 gap, ~4 missing transactions still unaccounted for)
- **Type column for remaining brokers**: Fidelity, Schwab, Robinhood, Merrill, Morgan Stanley — enable when source data confirmed
- **Apex Col 6 marker parsing**: Expand `_parse_accrued_wash_sale()` when non-zero 1f/1g test data available
- **Remove Fidelity `_fix_empty_cell_collapse()`**: After QC Pass 2 proven via regression, remove broker-level collapse handling. Deferred from JP Morgan session — do alongside Pass 3 work.
- **QC `_verify_or_search_col` search cleanup**: Search fallback disabled (trusts config). Was returning wrong anchors for Morgan Stanley, JP Morgan, and Schwab. Review with additional test data and remove if confirmed dead code.

## Charles Schwab Notes
- **Status**: Complete. Regression baseline + client file verified.
- **Paired row structure**: Header and data rows come in pairs. Row 1 (primary) has description + financials. Row 2 (secondary) has CUSIP + Date Sold.
- **Paired header**: Row 7 defines col 3 (Date Acquired code) and col 4 (Date Acquired date). Row 8 defines col 4 (Date Sold), col 5 (Proceeds), col 6 (Cost), col 7 (Wash Sale), col 8 (Gain/Loss).
- **Col 4 dual purpose**: Carries Date Acquired in primary row, Date Sold in secondary row.
- **Col 3**: SC/BC option codes (Sold to Close / Bought to Close). Not used in Drake output — description carries this info.
- **Layout (9-col)**: Col 0=Description/CUSIP, 1=Strike, 2=Option expiry, 3=SC/BC code, 4=Date Acquired (primary) / Date Sold (secondary), 5=Proceeds (sometimes merged with Cost), 6=Cost, 7=1f/1g (two-row, see below), 8=Gain/Loss
- **1f/1g two-row column design**: Col 7 carries BOTH Accrued Market Discount (1f) and Wash Sale Loss (1g) across the paired rows — this mirrors the two-row column header (header row N = "Market Discount" label, header row N+1 = "1g-Wash Sale Loss Disallowed" label). Primary row col 7 = 1f (Accrued), Secondary row col 7 = 1g (Wash Sale). Read via `_parse_accrued_wash()` in `schwab.py` — does NOT use `parse_accrued_wash_sale()` from `utils.py` (that function is for Apex Clearing's single-cell merged format).
- **Variable col count**: Sheets can have 7, 8, 9, or 10 columns depending on how many description columns precede the financial block. Financial block always occupies the last 5 cols (Date, Proceeds, Cost, 1f/1g, Gain/Loss). 10-col sheets go through QC Pass 1 first (right-shift), which normalises date to col 4.
- **Date column detection (fixed 2026-09-04)**: `_detect_date_col(df, num_cols)` in `schwab.py` scans each sheet's own columns for actual date values and picks the column with the most matches — this is now tried *before* the old `_date_col_idx(num_cols)` width formula, which is kept only as a fallback. Root cause of the bug this replaced: two sheets in the same workbook can report the *same* total column count (e.g. both 9 cols) while having genuinely different real layouts — one with a blank description spacer, one without — so the date column sits at a different index in each despite identical `num_cols`. The width formula can't distinguish these; per-sheet data-driven detection can. Symptom when this breaks: a sheet's transactions vanish entirely (silently classified `skip`, not flagged), while sibling sheets with the "same" column count parse fine — do not trust `num_cols` alone when debugging a Schwab sheet that's missing rows.
- **Merged Proceeds/Cost**: Col 5 sometimes has `"$ X $ Y"` (both values) or `"$ X $"` (trailing $, Cost in col 6). Split logic in `_split_proceeds_cost()`.
- **Proceeds merged with Cost text (added 2026-09-10, TEMPORARY)**: on a page with too few rows (e.g. a single transaction), PDF24 merges Cost text into the Proceeds cell — `"$ 0.71 Not Provided"`, Cost cell blank. `_leading_dollar_amount()` reads the leading amount (a leading `$` is required) and ignores the text; `_is_monetary()` uses it so the row classifies as a transaction, and `_split_proceeds_cost()` uses it for Proceeds, with Cost still read from the Cost column. Before this, the row was silently dropped. It's temporary because the merged text is thrown away rather than restored to its column. The proper fix is a generic QC split into the next column found from each sheet's header, which depends on per-sheet anchor detection (see PARKING_LOT).
- **VARIOUS**: Valid Date Acquired value for multi-lot positions. Recognized by QC `_has_date()` for right-shift detection.
- **Test file 1**: `schwab_1099 test 2025.xlsx` — 9-col, 4 sheets, 14 options transactions, Wash Sale=$0. Proceeds=$5,174.63, Cost=$4,192.20.
- **Test file 2**: `Charles Schwab 1099 RM_s.xlsx` — 5 sheets (Sheet1=10-col, Sheets 2-5=9-col), 21 stock transactions, Wash Sale=$13,891.50. Proceeds=$139,268.68, Cost=$128,019.96. Exercises the 1g-on-secondary-row path.
- **Test file 3 (not in regression yet)**: `testdata/2025 1099(Composite) - Charles Schwab.xlsx` — 14 populated sheets, 53 transactions, Proceeds=$87,783.75, Cost=$94,365.16. This is the file that exposed the date-column-detection bug above (Sheet7 was 9-col but missing the spacer that Sheet1/8/9/10/11/14 have). No manually-verified baseline yet — pending user QA before adding to `test_regression.py`.

## JP Morgan Notes
- **Source**: PDF converted via Excel's built-in PDF import (not PDF24). Single sheet `Append1`.
- **Layout**: Cols 0-3 = description/CUSIP/option info, col 4 = qty, 5 = DateAcq, 6 = DateSold, 7 = Proceeds, 8 = Cost, 9 = Accrued, 10 = Wash Sale, 11 = Gain/Loss, 12 = Additional Info
- **Options row shift**: 91/518 rows (PUT/CALL with expiry/strike in cols 2-3) have Accrued/Wash at cols 13-14 instead of 9-10. Currently broker-level fallback in jpmorgan.py. To be replaced by QC Pass 3.
- **Description**: Transaction rows: cols 0+1. Description-only rows: cols 0-3 (append to previous tx). Empty-description rows inherit `current_description`.
- **Repeating headers**: CUSIP / (Box 1a) markers repeat ~34 times — skipped via keyword matching.
- **Test totals**: 518 txns, Proceeds=$286,497.41, Cost=$286,245.52, Wash Sale=$2,818.89
