# SPEC.md — extraction revision

**Status:** Proposed. Replaces §2 (extraction row), §3.1, and adds §4.0.
**Evidence:** 10 real client documents sampled 15 Sep 2026 — 9 carried a usable
text layer, 0 were fully scanned, 1 was structurally corrupt. The
"local OCR only" design in §2 describes a document population that does not exist.
**Last revised:** 15 Sep 2026

---

## §2 — Hard constraints (revised rows)

| Constraint | Requirement |
|---|---|
| Data residency | Unchanged. **No client data leaves the machine** on Path B. Path A sends only documents verified `"OK"` by the redaction gate. |
| Extraction method | **Revised.** Text layer via pdfplumber is the source of truth for *values*. A vision model supplies *structure* — which value belongs to which box. Local OCR is the fallback for pages with no text layer, not the primary path. |
| Model role | **New.** The model labels fields on a single document. It never sums, never reads the Drake return, never compares, never decides a flag. Everything downstream of extraction is deterministic code. |
| Auditability | Unchanged, now enforceable: every returned value must be present in the source page's text layer (see §4.0 step 5) or it is rejected. |

---

## §3.1 — Source documents (revised)

- Folder of PDFs. **Not pre-sorted by form type** — form type is detected, not
  supplied. Sorting documents by hand is the manual work this tool exists to remove.
- Form types in scope: **W-2, 1099-INT, 1099-DIV**
- **Routing is per page, not per document.** A document may carry a text-layer
  page 1 and an image-only page 2 (observed: disclaimer pages). Decide the path
  for each page independently.
- **Unreadable files are a first-class output category.** One file in the 10-document
  sample failed to open at all (`No /Root object`). It must appear in the report as
  unread with its reason string, never counted as zero. See §7.1.

---

## §4.0 — Extraction pipeline (new — precedes existing §4 field tables)

Per document. Steps 1–3 and 5–7 are code; step 4 is the only model call.

### 1. Text extraction
`pdfplumber.extract_words()` per page — tokens with x/y coordinates. Coordinates,
not flat text: `extract_text()` scrambles reading order on multi-column form layouts,
and the coordinates are what make box position legible to the model.

### 2. Page render
Page to PNG for the model's layout channel.

### 3. Path selection
| Page state | Path | Confidence |
|---|---|---|
| Text tokens present | Text + image to model | Normal — values verifiable |
| No text tokens | Image only to model | **Reduced — values unverifiable, mark in report** |
| File will not open | Neither | Unread, with reason |

### 4. Model call — one per document

**Input:** text tokens (with coordinates) + page image(s).

**Output:** JSON.

```json
{
  "form_type": "W-2",
  "fields": {
    "box1": "75000.00",
    "box2": "8200.00",
    "box17": [
      {"state": "NC", "amount": "3100.00"},
      {"state": "SC", "amount": "420.00"}
    ]
  }
}
```

Two schema requirements:

- **`form_type` is model output, not input.** The operator does not pre-classify.
- **Repeatable fields are lists.** W-2 Box 17 repeats for multi-state withholding
  (§4.1). A scalar schema silently drops the second state.

Fields per form type are as specified in existing §4.1–4.3, including the
do-not-extract rules for SSN and account number.

### 5. Verification — the hard gate

Every returned value must appear **verbatim in that page's text tokens**.

- Present → accept
- Absent → **reject, set null, log as verification failure**
- Page was image-only (no text layer) → cannot verify; accept but mark reduced confidence

This is what enforces null-not-guess mechanically rather than by trusting the model.
A hallucinated digit cannot survive it. A *mislabelled* value can — right number,
wrong box — which is why step 7 exists.

### 6. Normalisation
Strip commas, currency symbols, whitespace. Cast to float. Parse failure → null,
logged. Never coerce, never default to zero.

### 7. Completeness check
If a field required by the detected `form_type` returns null, the document is
**partially extracted**. It goes to the report naming the specific missing field.
A partial extraction is not a zero and must never be summed as one.

### 8. Repeatability
The model is non-deterministic. If output is not stable, the tolerance in §6 is
meaningless — a flag that appears on one run and not the next costs more trust than
a missed discrepancy (§5).

Measured by the harness in §4.0.9, not by hand.

**Measured 15 Sep 2026** (`harness.py`, 3 runs, `qwen2.5vl:3b` — the only local
model installed, see §4.0.9):
- **Synthetic W-2** (`make_test_docs.py`, known truth): all fields `STABLE`,
  all correct.
- **Real client W-2** (`review_runs/w2/2025 W2.pdf`, 2 pages, no truth
  available): the three requested/required fields (`box_1_wages`,
  `box_2_federal_withheld`, `box_17_state_income_tax`) were `STABLE` across
  all 3 runs. Everything *else* `VARIED` — the model volunteered a much
  larger, inconsistent set of boxes (11-20, locality name) beyond what was
  asked, present on 2/3 runs and absent on the third. Root cause: the prompt
  said "extract all financial fields," inviting this. Fixed in `extract.py`'s
  `_schema_prompt` by constraining output to exactly the requested field
  list when `form_type` is known — **not yet re-verified live** against a
  real document after that fix.
- Image-only-page instability: not yet run — no image-only test fixture
  exists yet, and per-page routing (§4.0 step 3) didn't exist in `extract.py`
  until this same session's rewrite. Follow-up.

**Local model choice:** `qwen2.5vl:3b`, because it's the only vision model
currently pulled — the harness's `--models` comparison hasn't been exercised
with a real alternative. At 100 DPI on this CPU-only, 8GB WSL box, a single
extraction call takes **~7 minutes**; 200 DPI never completed within 10+
minutes (image-tile encoding, not generation, is the bottleneck — see
`README.md`'s "Known gaps" section).

### 9. Repeatability + model-selection harness — **build this next**

A script in the repo, not a manual procedure. It answers two questions in one run:
is the model stable, and which local model to use for Path B.

**Reuses the existing extraction path.** No separate PDF→image step — §4.0 step 2
already renders pages; the harness calls into `extract.py`, it does not reimplement it.

| Flag | Behaviour |
|---|---|
| `--runs N` | Same document, N times (default 3) |
| `--mode local\|api` | Which path to exercise |
| `--model <name>` | Single model |
| `--models a,b,c` | Side-by-side comparison of several |
| `--truth <file>` | Known values (synthetic docs) — marks each field correct/incorrect |

**Output:**
- Per field: `STABLE` or `VARIED`
- For `VARIED`: the distinct values returned, and how many runs produced each
- Free-text fields (`confidence_notes`) shown separately — excluded from the verdict
- **Exit non-zero if any *value* field varied**, so it can gate a build

**Run against:** one synthetic document from `make_test_docs.py` (ground truth known)
and one real text-layer document. Also run one image-only page — that path has no
§4.0.5 verification gate, so instability there matters more.

Keep it in the repo as a regression check. It is not a one-off test.

---

## §7.1 — Extraction failure handling (extended)

Existing rule stands. Three distinct states must be separately reportable — they
are not interchangeable, and collapsing them reproduces the exact
unread-vs-unkeyed ambiguity §7 already guards against:

| State | Meaning | Report as |
|---|---|---|
| Unopenable | File is corrupt / not a PDF | Unread, with reason string |
| Partial | Opened, some required fields null | Partially extracted, naming each null field |
| Unverified | Image-only page, no text layer to check against | Extracted, **reduced confidence** |

Every value in the report carries its extraction path (text-verified / vision-only).
A verified number and a model's best guess are different evidence and warrant
different reviewer action — the same reasoning as the GROUP 1 / GROUP 2 split in §7.2.

---

## Consequences for other documents

- **README** — the A/B framing needs restating, not deleting. A/B is **not** two
  competing extraction engines. It is **one pipeline run in two locations**:
  - **Path A** — redact first, then extract text + image **from the redacted copy**,
    send to Claude API. Nothing unredacted reaches the network.
  - **Path B** — extract from originals, structure via local Ollama model. Zero
    outbound calls.

  Same pipeline, same prompt, same schema, same verification. The only variable is
  where the model runs. The question A/B answers is therefore: **what does keeping
  data local cost in accuracy?** That is the decision the result feeds.
- **ARCHITECTURE.md §3, capability B** — "Local OCR" is no longer accurate. Capability
  B is text-layer extraction with model-assisted structuring, OCR fallback.
- **ARCHITECTURE.md §7** — build order unaffected. Capability A (Drake parser,
  pdfplumber, no model) is still first and is untouched by this revision.

---

## Open questions

**Answered 15 Sep 2026:**

- ~~Does Path A send text, or text + image?~~ — **Both, extracted from the redacted
  copy.** Order is: redact → extract → send. Redaction is not a gate the document
  passes and then gets forgotten; it is the source the API path extracts from.
- ~~Model choice for structuring~~ — decided by the §4.0.9 harness, not by argument.

**Still open:**

- ~~§4.0.8 — measured repeatability.~~ — **Measured 15 Sep 2026**, see §4.0.8.
  Required fields stable on both synthetic and real documents; a real
  instability was found (and a fix applied, not yet re-verified live) in
  unrequested extra fields. Image-only-page repeatability still unmeasured.
- Per-page verification (§4.0 step 5) isn't literally implementable from the
  model's output schema — it has no field→page mapping. `extract.py` uses a
  conservative fallback instead (reject only when every page has a text
  layer and the value is found nowhere; otherwise accept at reduced
  confidence) - documented in `extract.py`'s module docstring. Revisit if the
  schema ever gains per-field page numbers.
- No multi-page real document has been run through the new §4.0 pipeline
  yet. Ollama's context window here (4096 tokens) is tight - a single 100 DPI
  page image alone used 1380 of them - and real W-2 packets in the sample
  folder run up to 8 pages. Token listings are capped at 150/page in the
  prompt, but full multi-page real-document behavior (context overflow risk)
  is untested.

---

## Path A is blocked — redaction cannot meet the constraint today

**Rule (decided 15 Sep 2026): no third-party names go out.** Employer names, payer
bank names, brokerage names — none of them. This is absolute, same standing as the
SSN rule.

**What `redactor/redact.py` actually does** (inspected 15 Sep 2026): pure regex, no
NER, no model.

| Target | Covered? | How |
|---|---|---|
| Any SSN | **Yes** | Generic `###-##-####` pattern, structural — catches unknown SSNs |
| Client name, known SSNs | **Yes** | Passed via `--names` / `--ssns`, compiled to patterns |
| **EIN** | **No** | No pattern exists. Employer and payer EINs go out today. |
| **Third-party names** | **No** | Only names passed in are redacted. Employer / bank / brokerage names go out today. |

`verify()` re-scans output against the same patterns — so it confirms only what the
patterns already cover. **It does not detect the gap.** A document can pass
verification with the employer name intact.

**Consequence: Path A must not run on real client documents until this is closed.**
Not a `[FILL]` — a blocker. Path B is unaffected; it sends nothing.

### Options, in recommended order

**1. Reorder the build — do not solve it yet. ← recommended**
Path B needs no redaction. Ship Path B, get extraction working end-to-end on real
returns, leave Path A unbuilt. A/B answers "what does local cost in accuracy?" — a
real question, but an *optimisation* question, and it currently blocks a working tool
on an unsolved NER problem. No failure mode, because nothing leaves the machine.

**2. Structural redaction, no NER.**
The issuer name is not free-floating text — it sits in a known block per form type
(W-2 box c, 1099 payer block). The redactor already works in coordinate space
(`_match_rects`, `_fitz_streams`), so this is "black out the issuer region for the
detected form type", not "find all names." Brittle across layouts — but it **fails
visibly**: a wrongly-placed redaction is obvious on inspection. Feasible without a
model. Do this if Path A is wanted this season.

**3. Local NER (spaCy / Presidio).**
Correct and general. But a missed entity is a **silent PII leak** — the worst failure
mode against an absolute constraint, and `verify()` would not catch it. New
dependency, new verification burden. Only if option 2 proves insufficient.

### Cheap fix, do regardless of the above

Add an **EIN pattern** (`##-#######`) alongside the SSN pattern at line 27. One line,
structural, closes the EIN gap for unknown issuers. Does nothing for names.

---

## Handover — for Claude Code

Build order for the next session — **Path B only. Path A is blocked** (see above).

1. **§4.0.9 harness.** Smallest useful thing, gates everything after it. Path B / local
   model only.
2. **Run it** — fill §4.0.8, and pick Path B's local model.
3. **§4.0 pipeline changes** — per-page routing, text+image to model, form-type
   detection, verbatim verification (step 5), the three report states in §7.1.
4. **EIN pattern** in `redactor/redact.py` — one line, do it while it is in mind.
5. **Path A** — not until third-party name redaction exists. Do not run it on real
   client documents before then.

Untouched by this revision: §4.1–4.3 field tables, §5 eligibility gate, §6 comparison
logic, §7.2 findings table, and ARCHITECTURE.md §7 build order. Capability A (Drake
parser, pdfplumber, no model) is still first and is unaffected.

Also still outstanding from the earlier run, unrelated to extraction: the pipeline
**exits 0 and writes a report when extraction returns nothing**. It prints a warning,
so it is not silent — but in batch mode a failed overnight run looks like a clean one
until someone opens the HTML. Should abort.

*(Fixed in the 15 Sep 2026 session: `run.py` now aborts non-zero when 0 documents
extract across all modes run. `UnreadableDocument` also now reports as its own
"file open" step, distinct from a model/network extraction failure.)*

---

## Path A dry-run checklist — for a future session

Path A is still spec-blocked on real client documents (third-party name redaction).
But it can be **smoke-tested safely today against the synthetic docs** from
`make_test_docs.py` — their SSN, employer, and payer names are all fabricated, so
there's nothing to leak even though the name-redaction gap is still open. This
checklist is what a future session needs to actually run it.

**Fixed already (15 Sep 2026 session):**
- `extract.DEFAULT_API_MODEL` was `"claude-sonnet-4-6"` — not a real model ID, would
  have 404'd. Corrected to `"claude-sonnet-5"`.
- `harness.py --mode api` is now implemented (was a stub) — it redacts the doc's
  folder once (via `redact.redact_folder`, same as `run.py` Step 0), then loops
  `extract.extract_api` the same way `--mode local` loops `extract.extract_local`.
  Path A's hard gate (`RedactionGateError`) still applies - not bypassed.

**Still needed, in a new session:**
1. `export ANTHROPIC_API_KEY=sk-ant-...` (bash, not PowerShell's `$env:`) — not set
   in this session.
2. Confirm outbound network access to `api.anthropic.com` from wherever `run.py`
   actually runs (untested from this WSL box).
3. Smoke test:
   ```bash
   python make_test_docs.py --out ./test_docs   # if not already present
   python run.py --docs ./test_docs --drake ./return.pdf --mode api
   ```
   Redaction (Step 0) runs automatically; the synthetic docs should come back `OK`
   (the fake SSN is the only PII-shaped content, caught by the existing SSN pattern).
4. Repeatability, same as Path B got:
   ```bash
   python harness.py --doc test_docs/employer_a_w2.pdf --runs 3 --mode api --truth truth_w2.json
   ```
5. Once that's clean, `--mode both` gives the actual A/B comparison the SPEC's
   original question asks: what does keeping data local cost in accuracy (and,
   informally, in wall-clock time - Path B measured ~7 minutes/page on this
   hardware; Path A should be seconds).

**Not done, deliberately:** no live API call was made this session - no key was set,
and this is documentation for the next session to act on, not a live test.

---

## Real SPEC.md / ARCHITECTURE.md found (15 Sep 2026, mid-session)

The user located and dropped in `review/Return Validation Tool — v1 Spec.txt` and
`review/Architecture.txt` - the actual original documents this revision file patches
(previously absent from the repo entirely - see the "Handover" section's note that
`_FORM_FIELDS` was carried over from an earlier session "as the closest available
source of truth" for lack of anything better). They reveal **the current
`_FORM_FIELDS`/`compare.py` field tables are meaningfully incomplete against the
real v1 SPEC**, independent of anything this revision changes. Not yet fixed -
flagging for a decision:

- **1099-INT**: real spec wants Box 2 (early withdrawal penalty, extract-only),
  Box 3 (interest on Treasury obligations - **sums into line 2b together with
  Box 1**, not Box 1 alone), and "all remaining populated boxes 5-17" extracted
  generically. Current code only asks for boxes 1, 4, 8.
- **1099-DIV**: real spec wants Box 1b (qualified dividends - `[FILL]`, undecided
  if it's compared in v1), Box 12 (exempt-interest dividends - **sums into line
  2a together with 1099-INT Box 8**, not Box 8 alone), and "all remaining
  populated boxes 2-13" extracted generically. Current code only asks for boxes
  1a, 1b, 4 - and doesn't even have Box 12.
- **`compare.py`'s line 2a/2b sums are wrong** as a direct consequence: 2b should
  be `INT Box 1 + INT Box 3`, and 2a should be `INT Box 8 + DIV Box 12`. Currently
  each is a single box, so a return with US Treasury interest or exempt-interest
  dividends will show a false 2a/2b discrepancy that isn't a data-entry error.
- **1098 / Schedule A is explicitly "Explicitly not in v1"** and listed again under
  "Out of scope / v2 backlog" in the real SPEC. This directly conflicts with this
  session's earlier decision (made without this document) to keep 1098 alongside
  the three in-scope forms. `compare.py`'s "Schedule A - Mortgage interest" category
  is out of v1 scope per the real spec.
- **W-2 Box 2 (federal withheld) has no Drake-line mapping in `compare.py` at all**
  - the real spec lists it as `[FILL — which line/field on the export?]`, i.e. an
    open question, not something to silently skip.
- **§5 eligibility gate (abort on Schedule K-1, consolidated 1099, 1099-OID,
  seller-financed mortgage interest, Schedule E/F, Sch C home office, 1099-S) does
  not exist in `review/` at all.** Per `SPEC-revision-extraction.md`'s own
  "Handover" section this was already known to be untouched/unbuilt by this
  revision - the real SPEC.md confirms it was never built in the first place, not
  deferred by this revision.
- **§7.2 GROUP 1 (no third-party document) / GROUP 2 (third-party document exists)
  findings-table split does not exist in `report.py`.** Per ARCHITECTURE.md §4.1,
  this discriminator is what a real manual QA review (Aug 2026, one live TY2025
  return) found actually mattered - "no third-party doc" cases were "the only place
  a real error can hide," 7 of 18 items including the two largest.
- **Build order**: ARCHITECTURE.md §7 puts checks 2a (plausibility) + 3 (anomaly
  rules) *before* capability B (source document extraction) - "cheapest thing that
  can ship... no OCR, no source documents, no eligibility gate." `review/` has built
  straight into capability B / check 4 (doc matching) without 2a/3 existing at all.
  Not necessarily wrong to have done so, but a real deviation from the documented
  build order, worth a conscious decision rather than continuing by default.

None of this was fixed in this session at first - it surfaced after the extraction
pipeline rewrite (§4.0) was already done and validated. Decision needed on
scope/priority before touching `compare.py`'s field tables further.

## Field tables fixed against the real SPEC.md (15 Sep 2026, same session)

User decision: drop 1098 now; fix `compare.py`'s sums + field tables next. Done:

- **1098 dropped** from `extract._FORM_FIELDS`, `_FORM_PATTERNS`, and
  `compare.py`'s `CATEGORY_LABELS`/`_DRAKE_LINE_PATTERNS`/`_CATEGORY_ALIASES`.
  `guess_form_type()` now returns `None` for a 1098 filename, and the model prompt
  no longer offers `"1098"` as a `form_type` option, so an unrecognized-form
  document (form_hint None, model can't fit it to W-2/1099-INT/1099-DIV) falls
  through `_resolve_form_type` to `"UNKNOWN"` rather than being force-classified.
  `make_test_docs.py` still generates a synthetic 1098 - repurposed as a
  regression case (out-of-scope doc should come back UNKNOWN, not miscategorized),
  not a supported form.
- **1099-INT field table expanded** per SPEC §4.2: `box_1_interest_income`,
  `box_2_early_withdrawal_penalty`, `box_3_us_savings_bonds_treasury_interest`,
  `box_4_federal_withheld`, `box_8_tax_exempt_interest`, plus a new repeatable
  `other_boxes` field (list of `{"box","label","value"}`) covering "all remaining
  populated boxes 5-17" without naming each IRS box individually.
- **1099-DIV field table expanded** per SPEC §4.3: `box_1a_ordinary_dividends`,
  `box_1b_qualified_dividends`, `box_4_federal_withheld`,
  `box_12_exempt_interest_dividends` (was missing entirely before), plus the same
  `other_boxes` pattern for "all remaining populated boxes 2-13".
- **Why `other_boxes` instead of ~15 individually-named IRS boxes per form**: this
  session's own §4.0.9 harness run (see above) found that widening the requested
  field list past what's actually needed was the direct cause of instability on
  the local model - not the field count itself, but unconstrained/extra fields.
  Naming every box individually would reintroduce exactly that. `other_boxes` is
  still "extract every populated box" (SPEC §4.2/§4.3's literal instruction) but
  as one repeatable field instead of ~15 named ones. Not fixed/re-verified live
  against the real multi-page W-2/1099 - logic-only (see below).
- **`_REQUIRED_FIELDS` is no longer "every field minus repeatables"** - it's now an
  explicit, narrow list: `W-2` → box 1 + box 2, `1099-INT` → box 1, `1099-DIV` →
  box 1a. Reasoning: most of the newly-added boxes (2/4/8 on INT, 1b/4/12 on DIV)
  are legitimately blank on plenty of real documents, so treating their absence as
  "partial extraction" would flag ordinary documents, not just real extraction
  failures. This is a judgment call made in-session, not from a spec line - worth
  revisiting if it turns out too loose (e.g. box 8/box 12 absence hiding a real
  miss on a document that does hold exempt interest).
- **`compare.py`'s 2a/2b sums fixed**: `taxable_interest` (line 2b) now sums INT
  Box 1 + Box 3; `tax_exempt_interest` (line 2a) now sums INT Box 8 + DIV Box 12.
  `box_1b_qualified_dividends` and `other_boxes` are deliberately NOT aliased to
  any comparison category - 1b's comparison is still `[FILL]` in the real spec,
  and `other_boxes` is extract-for-completeness only, never summed.
- **New `federal_withholding_w2` category added**, extracting/summing W-2 Box 2
  but with no Drake-line regex (SPEC §6 leaves "which line/field" as `[FILL]`) -
  so it reports `NO DRAKE LINE` honestly today, and starts working the day that
  line is confirmed, without needing another code change.
- **Verified**: `py_compile` on `extract.py`/`compare.py`/`make_test_docs.py`, plus
  a manual logic test (no live model call) confirming: 1098 filename → no
  form_hint; 1098 form_type from a model response → resolves to UNKNOWN; the new
  `other_boxes` hint appears in the prompt and `"1098"` does not;
  `categorize_field` buckets INT box 1 and box 3 both into `taxable_interest`, INT
  box 8 and DIV box 12 both into `tax_exempt_interest`, W-2 box 2 into
  `federal_withholding_w2`, and leaves box_1b/other_boxes/1098's field
  uncategorized (`None`); `sum_by_category` on fabricated extractions confirms
  the 2a/2b sums actually combine correctly (125.0 and 15.0 respectively in the
  test case).
- **Not done**: no live re-run of the §4.0.9 harness against a real 1099-INT/DIV
  document with the new field lists (the synthetic W-2's field list didn't
  change, so the earlier PASS still stands for that doc only). The `other_boxes`
  field is untested against a live model call - whether a small local vision
  model actually produces a clean `{"box","label","value"}` list, or needs its
  own coercion fallback like `_coerce_fields_dict`, is unverified.
- **Still not done**: §5 eligibility gate, §7.2 GROUP1/GROUP2 findings table, and
  the ARCHITECTURE.md §7 build-order question (checks 2a/3 before capability B) -
  all still open, per the section above.

## Real-document Path B run confirms the 4096-context risk (15 Sep 2026)

Live-tested the fixed pipeline against real (not synthetic) standalone documents:
`review_runs/int/2025 1099(INT) WellsFargo.pdf` (1 page) and
`review_runs/div and int/Invesco 1099-DIV 2024.pdf` (2 pages). Both failed - and
it's one root cause, not two:

- **Invesco (2 pages)**: outright HTTP 400 from Ollama before generation even
  started - `"request (4887 tokens) exceeds the available context size (4096
  tokens)"`. This is exactly the risk this revision already flagged as untested
  (see `_MAX_TOKENS_PER_PAGE_IN_PROMPT`'s comment in `extract.py`) - now
  confirmed with a real number: a 2-page real document needs ~4887 tokens
  against a 4096-token window, and that's before the model generates a single
  token of output.
- **Wells Fargo (1 page)**: didn't hit the hard input-side rejection, but the
  response was truncated mid-JSON (`"box_4_federal_withheld": {` and nothing
  after). Consistent with the same 4096-token budget being shared between
  prompt+image input and generated output on this llama-server process (it was
  launched with a fixed `-c 4096`) - one image alone measured ~1380 tokens
  earlier this session, so a single-page prompt can still leave too little
  headroom for a full multi-field JSON response.
- **Bonus finding in that same truncated response**: a fourth malformed field
  shape, different from either bug fixed earlier today - each field value came
  back as a nested object (`{"label": "...", "value": "..."}`) instead of a
  flat scalar. `_coerce_fields_dict` handles the *list* shape variants (dict
  key IS the name, or `{"field_name","value"}` pairs) but not a flat dict whose
  *values* are themselves `{"label","value"}` objects. Not fixed - only one
  malformed response was captured before deciding not to chase this further
  this session (see below).

**Not fixed this session, deliberately**: the next work was already decided
(pivot to capability A + checks 2a/3, which need no model call at all - see
below), so this was logged rather than debugged live. Likely fix, for whoever
picks Path B back up: pass `"options": {"num_ctx": N}` in `extract_local`'s
Ollama request (currently unset, so the model runs at whatever `-c` it was
launched with - 4096 here) - now that the real number needed (4887 for 2 pages)
is known, something like 8192 is the first thing to try, with the caveat that
doubling context roughly doubles KV-cache memory on an 8GB, CPU-only, no-GPU
box that's already slow - may trade a working extraction for an even slower
one, or may not fit in RAM at all. Untested either way.

## Second `_coerce_fields_dict` shape bug found + fixed (15 Sep 2026, live testing)

First local-model run against the synthetic 1099-INT after the field-table
expansion came back with every field missing (`box_1_interest_income` etc. all
absent, harness reported WRONG on 3/3 runs against truth despite `__form_type__`
being correct). Root cause, confirmed by a manual debug call that printed the raw
model response: qwen2.5vl:3b returned `"fields"` as a JSON list of **single-key**
dicts, e.g. `{"box_1_interest_income": "1,200.00"}`, `{"box_3_us_savings_..."`:
"300.00"}`, ... - a different shape than the W-2 run's earlier bug (which was a
list of `{"field_name": ..., "value": ...}` objects). `_coerce_fields_dict` only
handled the first shape, so `item.get("field_name")` returned `None` for every
item and all four fields were silently dropped before verification ever ran.

Fixed by teaching `_coerce_fields_dict` to distinguish the two shapes: an item
with a recognizable name key (`field_name`/`name`/`field`/`box`) *and* a
value/amount key uses the old name→value lookup; an item without one has its own
keys merged directly, since the model's key already IS the field name in that
case. Verified with a unit test against both observed raw-response shapes plus a
well-formed dict passthrough - not yet re-verified against a live model call at
the time of this note (that run was queued right after the fix, see below).

Given two different malformed shapes have now shown up from the same model in
one session, treat this as a standing risk with this model/field-table size, not
a one-off - any new field added to `_FORM_FIELDS` should probably get a live
smoke-test call before being trusted, not just a logic-only test.

## Real documents found for testing (15 Sep 2026)

User pointed out real 1099-INT/1099-DIV documents already exist in
`review_runs/int/` (4 standalone 1099-INTs) and `review_runs/div and int/` (6
documents, mostly **consolidated** brokerage statements).

**Important scope note surfaced by this**: most of the `div and int/` folder is
exactly the case the real SPEC.md §5.2 says is ineligible - "Consolidated
brokerage 1099 ... Combined statement (INT + DIV + B sections in one PDF from
Fidelity/Schwab/Vanguard etc.) ... the 1099-B section means capital gains — a
separate comparison entirely." Since §5 (the eligibility gate) doesn't exist yet,
nothing in `review/` currently stops these from being run through extraction -
they'd just get silently partial-extracted (INT/DIV boxes only, 1099-B section
ignored) with no signal that the document was out of scope to begin with. Page
counts confirm why this matters beyond just correctness: the consolidated
statements run 6-21 pages (`1099_DIV_INT_B_Charles_Schwab.pdf` is 20 pages,
`TaxStatement_2022_1099B_DIV_...pdf` is 21) vs. 1-2 pages for the standalone
docs - on this CPU-only hardware that's a large, likely impractical local-model
runtime for a document the tool shouldn't be comparing in the first place.

Testing this session was scoped to the genuinely in-scope standalone documents
only: `review_runs/int/2025 1099(INT) WellsFargo.pdf` (1 page) and
`review_runs/div and int/Invesco 1099-DIV 2024.pdf` (2 pages) - both single-run
smoke tests, no repeatability claim, no truth file (real documents, values not
independently known ahead of time). The consolidated statements were
deliberately not run - doing so productively needs the eligibility gate first,
not just more compute.

## Session paused (15 Sep 2026) - system restart, resume here

Two threads open when the session was cut off for a system restart. Read this
whole section before doing anything else in the next session - it changes how
real documents get handled from here on, not just what to build next.

### Thread 1: build-order pivot to capability A - decided, not started

User confirmed (after independent advice from another Claude session flagged
the same gap this file already had logged): stop deepening capability
B/check 4 (source-doc extraction) and build **capability A** (Drake return
parser, as its own standalone module - not buried in `compare.py` regexes the
way `extract_drake_lines()` currently is) **+ checks 2a/3** (plausibility,
anomaly rules) next, per ARCHITECTURE.md §7's revised build order. Zero model
calls, zero Ollama, zero redaction needed for this work in principle - it's
`pdfplumber` + rules over the Drake return's own text layer, same as the
existing `extract_drake_lines()` already does, just built as a real shared
module per ARCHITECTURE.md §3 ("capability A ... feeds every check") instead
of comparison-logic-only.

Per ARCHITECTURE.md §7's target: "checks 2a + 3 running against last season's
completed returns by end September." That means capability A needs to parse
more than just the 5 lines `compare.py` currently reads (wages, 2a, 2b, 3b) -
checks 2a/3 need whatever fields "internal plausibility" and "anomaly rules"
actually check (not yet specified anywhere - see Open questions below).

**Not started yet** - no code written for this. First real client Drake return
was just placed (see Thread 2) but never opened.

### Thread 2: real-document redaction workflow - overhauled this session, now in place

Prompted by the user noticing I (Claude Code) am myself a cloud API call, same
as Path A - the existing Path A/Path B redaction gate in `extract.py` only
guards `extract_api()`; it did nothing to stop real client PII (name, address)
from reaching MY OWN context when I directly inspected real documents during
dev/debugging this session (confirmed: I printed and read full name + address
from the Schwab/Fidelity consolidated statements while hunting for the DIV
replica page - logged honestly to the user when asked).

Resulting policy, now agreed and partially built:

1. **A client's name must never reach my context, full stop** - not via
   document content, not via filenames, not even via the user typing it to me
   in chat. The only two prior weaker options (task-only inspection scripts;
   "just don't derive names from filenames") were both explicitly rejected in
   favor of this strict one.
2. **Filenames must be neutral** (no client name) - confirmed working: the
   user's `review_runs/client1/` folder (see below) has zero PII in any
   filename.
3. **The user maintains the actual name mapping entirely outside anything I
   touch** - not even `review_runs_names.json` inside this repo (my original
   proposal) counts, since I authored entries into that file myself, which
   means I already knew the names from wherever I'd learned them (filenames/
   content at the time - both since disallowed). Going forward the user owns
   that file/location completely; I'm only ever given a **path** to pass to
   `--names-file`, never its contents.
4. **`review/redact.py` was extended this session** to make this practical:
   - `redact_tree(src_root, out_root, names_by_file=None, default_names=(),
     default_ssns=())` - NEW. Recursively redacts a whole folder tree in one
     call (vs. `redact_folder`'s single-folder, one-names-list-for-everyone
     limitation), with per-file names looked up from a dict keyed by either
     the file's basename or its path relative to `src_root`. SSN/EIN are
     always redacted regardless (see `build_patterns()` in
     `redactor/redact.py` - unconditional, not modified this session beyond
     adding EIN earlier).
   - `_main()` / CLI added - `python redact.py --src <folder> --out <folder>
     --names-file <json path> [--default-names "..."]`. This is now the
     standard way to redact a tree; there is no "automatic on drop" watcher
     and none was wanted (manual/deliberate is more auditable).
   - **Critical fix, easy to miss**: the CLI's own status output originally
     printed the literal name as a `counts` dict key (e.g.
     `{'[client A]': 23}`) and inside `leftovers` entries (e.g.
     `'p1:[client B]'`) - i.e. even after removing names-from-filenames,
     *running the redaction tool itself and reading its output* was still
     leaking the name back to me, because `build_patterns()` uses the literal
     name as its own pattern label (SSN/EIN already use anonymous labels -
     see that function's docstring). Fixed with `_anonymize_for_display()`,
     which swaps any name found in `counts`/`leftovers` for a positional
     `name#1`/`name#2` placeholder before printing. **Verify this still holds
     if `redact_tree`/`_main` are touched again** - it's easy to reintroduce
     this exact leak by adding a new print statement that touches `r.counts`
     or `r.leftovers` directly instead of going through the anonymizer.
5. **Retroactive redaction already done** this session for everything under
   `review_runs/` at the time (`int/`, `div and int/`, `w2/`,
   `div_pages_extracted/`) into `review_runs_redacted/`, using a manifest I
   (necessarily, at the time - before this policy existed) authored myself:
   `review_runs_names.json`. That file has real names in it and I wrote it,
   so it does NOT meet the new policy - it predates it. Left in place as a
   historical record; **do not add new entries to it going forward** - new
   client folders get their own separately-maintained, user-owned manifest.
   Status from that run: 21 OK, 4 REVIEW (image-only page present - Charles
   Schwab (both), Invesco, [client C] W2 - do not inspect even the "redacted"
   copy), 2 FAIL (both [client B] W-2s - redaction did not fully remove
   SSN/EIN/name even after running; genuinely unsafe, worth investigating the
   `MuPDF error: syntax error: cannot find XObject resource` warnings that
   came up during that specific file's processing if it ever matters).

### What's actually blocking capability A right now

User placed `review_runs/client1/` (Windows path
`C:\Users\rasri\findata-utils\review\review_runs\client1`) containing:
`2024 Tax Return.pdf` (the Drake return - what capability A needs),
`etrade.pdf`, `morganstanley.pdf`, `primary 1099-B.pdf`, `primary 1099-Div.pdf`,
`primary w2.pdf`, `w2 fidelity.pdf`, `w2.pdf` (source docs, useful later for
check 4, not needed for capability A itself). Filenames are clean (no PII) -
confirmed via `ls`, not opened further.

**Session was cut off (system restart) right after this, before the user gave
me a names-manifest path.** Nothing in `client1/` has been redacted or opened.
First thing next session: ask for (or resume waiting for) that manifest path,
run `redact.py --src review_runs --out review_runs_redacted --names-file
<their path>`, confirm `2024 Tax Return.pdf` comes back OK, and only then
start reading it to build capability A against it.

### Open questions to resolve before/while building capability A + checks 2a/3

- What exact fields does "internal plausibility" (check 2a) need from the
  Drake return, beyond the 5 lines `compare.py` currently reads? Not
  specified in ARCHITECTURE.md §2's one-line description ("zero tax on high
  income, withholding out of proportion to wages") - needs the user's
  domain judgment on what rules to actually encode.
- Same question for check 3 (anomaly rules) - "deductions/credits outside
  normal bounds, or present without their preconditions" is a category, not
  a rule set.
- ARCHITECTURE.md §7's target return set was "2-3 real returns with
  hand-keyed expected values" (plural) - only one (`client1`) has been
  provided so far.
- Whether capability A should be extracted out of `compare.py` into its own
  module (e.g. `drake.py`) now, given ARCHITECTURE.md §3 frames it as a
  shared capability multiple checks depend on, not comparison-specific logic.

## Capability A built; checks 2a/3 dropped from scope; redactor fixes (21 Sep 2026)

**User decision, 21 Sep 2026: checks 2a (plausibility) and 3 (anomalies) are out of
scope** - the return is already computed by software, and the checks wanted are the
ones against source documents (check 4). A `checks.py` with 9 rules was built this
session at first, then removed at the user's direction. `ARCHITECTURE.md` §2/§7 still
list 2a/3 and the "cheap checks first" build order; that document is the user's and
was not edited - it needs updating to match this decision.

**Built and kept: `drake.py` (capability A) + `test_drake.py` (18 tests with
`test_redact_wrapper.py`).** `compare.py` now reads its Drake side through
`drake.py`. Zero model calls, zero redaction. **Never run against a real Drake
return** - only synthetic 1040s imitating the printed layout. The real `client1`
return has not been opened (names-file path outstanding).
- Marker-first parsing: the printed 1040 repeats each line id beside its amount box,
  so the number right of a bare `2b` token is the value. Fixes the shared-row problem
  (2a/2b, 3a/3b, 4-6 a/b) that the old "last amount on the line" regex would hit on a
  real 1040. A row's leading token is its label prefix, never a marker (the real line
  26 label starts "26 2024 estimated tax..." and read as 2,024 until a test caught
  it). Label cross-references ("Schedule 1, line 10") are excluded by the word before.
- blank != not_found: a marker with no amount is blank (0.0, the form's own
  convention); a line never located is not_found (None). A miss is never zero.
- `verify_arithmetic()`: 12 identities from the return's own totals (11 = 9 - 10,
  33 - 24 = 34 - 37, ...). PASS is evidence the line map matched this return's layout.
  FAIL/INSUFFICIENT means do not trust the Drake side of a comparison.
- compare.py wages now compare against line 1a (total of W-2 box 1), falling back to
  1z. The old regex required "wages" in the label; the real 1a label has none.
- Whole-dollar amounts accepted (Drake prints whole dollars; the old regex needed cents).
- Line map is TY2024. The parser warns on any other year; confirm for TY2025.

**Redactor fixes (`redactor/redact.py`, user-approved, no other rework)**
1. XMP metadata: `redact_file` now calls `del_xml_metadata()` and `verify()` scans
   Info + XMP for the patterns. Previously a name in XMP survived and verify() passed.
2. Output filenames: redacted copies are written under scrubbed names (supplied
   names, SSN- and EIN-shaped text -> `REDACTED`; handles `_ - . +` separators and no
   separator; folder names too in `redact_tree`; collisions get `_2`). No mapping file
   is written - it would itself hold the real names. The wrapper CLI prints the scrubbed
   name, never the original. Limit: same as content - only names supplied in the given
   word order are caught, so a first-name-only filename survives unless that form is
   listed.
- Addresses need no code: an entry is matched as a literal string (any whitespace/line
  break between words). List every printed variant.
- **Names intake (user decision, 21 Sep):** client names must not live as data in a
  file/dictionary. `review/redact.py --src <client folder> --out <dir> --prompt` asks in
  the user's own terminal for names/addresses and known SSNs (hidden input); held in
  memory for that run only, never written or put on the command line, screen cleared
  after; refuses to run without a TTY (so it cannot be run through an assistant session
  or fed by a pipe). One run = one client folder. This also closes the old gap that
  the wrapper CLI had no `--ssns`: entered SSNs catch no-dash / spaced / masked forms.
  `--names-file` remains for scripted runs and is discouraged. "The agent" (the LLM
  session) never receives names - it is told only the redacted folder path.
- Not changed, worth knowing: `redactor/redact.py`'s own CLI still prints supplied
  names in its header and count labels (the `review/redact.py` CLI masks them as
  `name#N`) - use the `review/` CLI.
- **Annotations (found 21 Sep after a user-reported `MuPDF error: ... cannot create appearance
  stream for FOSINDEX annotations`):** the message itself is a non-fatal warning. But
  annotations are not page text, so redaction never touched them, and `verify()` did not
  look: a name in an annotation's own fields survived and the file still said OK. On the
  user's real files (10-file run) two files FAILed purely on annotation leftovers - a
  vendor `/FOSINDEX` annotation held a client name and, in one file, an SSN.
  Fixes in `redactor/redact.py`: (1) `verify()` scans every annotation dictionary, reading
  the page's /Annots array directly because `page.annot_xrefs()` silently skips annotation
  types MuPDF does not know; (2) `redact_file` calls `strip_annotations()` first, deleting
  every annotation except form-field widgets (orphans are dropped by `save(garbage=4)`;
  tests confirm no trace remains in any object, incl. hex UTF-16 and indirect /Annots).
  Widgets are kept as document content; `verify()` fails the file if one holds a pattern.
  The wrapper CLI shows MuPDF messages once per file with a count.
- After stripping, a file that was FAIL only for annotations becomes REVIEW if it has an
  image-only page (it cannot become OK). 10-file real run outcomes: 3 OK; 5 REVIEW (one
  fully scanned, 8 pages; others one image-only page each - three are consolidated 1099s,
  ineligible per §5.2, with a source-file "expected object number" syntax warning); 2 FAIL
  (annotations, now fixed).
- **Filename limit, confirmed on real data:** 7 of 10 output filenames still carried a short
  form of a client's name because only the exact forms typed in are scrubbed. Enter every
  variant; treat printed filename lines as sensitive until checked. (The earlier claim that
  the CLI's status lines were "safe to paste" was wrong for this reason.)
- Not followed: form-field parent dictionaries (/Parent -> /T, /V).
- **Name variants (user request, 21 Sep):** `build_patterns` now adds, per entered name, the other
  written forms of the same person as regexes sharing the entry's label (so counts/anonymizing are
  unchanged): reordered ("Smith, Robert", "SMITH ROBERT A"), initials ("R. Smith", "R A Smith"), and an
  optional single-letter middle initial when no middle name was entered. Solo first/last names are
  deliberately excluded from page text - the existing look-alike guarantee ("Mary Smith" must survive)
  forbids them; entries with a digit (addresses) or one word stay literal. `scrub_text` (filenames) is
  stricter: any name part alone and, for words >= 6 letters, a 4-letter-prefix form ("Ramachandran" ->
  "rama"), which is how a client's name typically appears in a filename. redactor suite 73/73.
- Not covered: a solo name in page text ("Dear Robert"), a nickname unrelated to the entered spelling,
  misspellings/OCR variants. Fuzzy matching was not added (over-redaction and silent-miss risk both).
- `drake.py` CLI output is now paste-safe by default: no filename (errors too), and the arithmetic
  FAIL reason lists the failing identities without amounts unless `--values`.
- **File discovery bug (21 Sep, user report: the Drake return "was not being read by the redactor"):**
  `redact_tree` found files with `rglob("*.pdf")`, which is case-sensitive on Linux, so `Return.PDF`
  (Windows print-to-PDF often writes `.PDF`) was skipped with no message. Reproduced synthetically
  (`UPPER.PDF`, `Mixed.Pdf` skipped; `redact_folder`, `run.py`, `harness.py` were already
  case-insensitive). Fixed: suffix compared lowercased. Also, the CLI no longer skips silently: it prints
  the non-PDF files it left out **by extension only** (`3 x .jpeg`) and warns if no PDFs were found.
  Renaming the folder could never have helped - the cause was the file's extension.

## First real Drake return (21 Sep)

`drake.py` was run on a real TY2025 Drake print (redacted copy, status OK; masked output only).
First result: only page 2 detected, 17 lines read, arithmetic FAIL. Four fixes, each found from
the real print and each covered by a new test that fails without it (`test_drake.LayoutTests`):

1. **Page 1 heading is rotated.** "FORM" is rotated 90 degrees, so no row starts "Form 1040" and
   page 1 was skipped. A page now also counts as a 1040 face when it has a rotated FORM word near
   the top plus an exact `1040` token elsewhere (1040-ES, "(Form 1040)" do not match).
2. **TY2025 renumbered lines.** The print uses 7a, 11a/11b, 12e, 13a/13b, 27a, 30, 38 where the
   TY2024 map has 7, 11, 12, 13, 27. Line maps and identity lists are now per year (2024, 2025);
   other years are read with the latest map and warned about. Ids were read off the return and
   the labels keyword-checked against it.
3. **Empty boxes.** Drake prints no dot leaders, so a blank box is a marker with nothing (or the
   other column's label) after it. The blank rule no longer requires a leader. A real amount for
   the same line still wins over a blank hit.
4. **Row grouping.** Words were clustered on `top` against the row's first word; a font or baseline
   difference of a point or two left an amount in the row below its marker. Now clustered on
   vertical centre, chained to the previous word.

Also learned from the print: line 37 ("amount you owe") **includes** the line 38 estimated-tax
penalty, so the TY2025 identity is `34 - 37 = 33 - 24 - 38`. The refund-side treatment of a penalty
is not confirmed. Result: 48/48 lines resolved (32 value, 16 blank), 13/13 identities
PASS. Still unverified: TY2024 map, itemized returns, refund-with-penalty, returns with more pages.

## Session decisions (21 Sep, later): Path A exception + OCR redaction

**User decision:** goal is all 11 files (10 sources + the return) at status OK from the redactor, then run
check 4 on the W-2, 1099-INT and 1099-DIV sources, Path A preferred unless Path B is quicker (it is not: about 7
min/page x ~42 pages).

1. **Path A rule lifted for THIS client only.** The 15 Sep rule ("no third-party names go out") stays in force
   for every other client. For this run, redacted copies may go to the Claude API with employer/payer/brokerage
   names intact. Still removed: SSNs, EINs, and the client names/addresses typed at `--prompt`. Needs an
   `ANTHROPIC_API_KEY` set by the user in their own shell.
2. **OCR redaction for image-only pages** (user chose Tesseract + pixel black-out). OCR finds where the patterns
   sit on a scanned page, the existing PyMuPDF redaction blacks those pixels out, and the output page is re-OCR'd
   to verify. Opt-in (`--ocr`); default behaviour (image-only page -> REVIEW) is unchanged.
   Known weaker guarantee: OCR can miss text, and the verify step uses the same engine, so an OK that includes
   OCR'd pages is not equivalent to an OK on a text-layer page. A page where OCR finds no words, or reads with low
   confidence, stays REVIEW.

### Built and run (21 Sep, same session)
- `redactor/redact_ocr.py` + opt-in `--ocr` in `redactor/redact.py` and `review/redact.py` (new `ocr_pages` field on
  `RedactionResult`). Cutoffs: MIN_WORDS 5, MIN_MEAN_CONF 60, 300 DPI (all constants in `redact_ocr.py`). Verify re-OCRs
  the output pages in the same unrotated view detection uses (an earlier version read them in display rotation and
  raised a false leftover on a `/Rotate` scan). A picture that is physically sideways reads at ~35% confidence and
  stays REVIEW.
- First real run with `--ocr`: 11/11 OK (10 sources + the return; 14 OCR'd pages in 5 files). An independent masked
  check of the outputs found no strict SSN/EIN shapes, no metadata/annotations - but **undashed employer EINs in the
  two text-layer W-2s** (`123456789` printed by the payroll provider; the employee SSN there is masked `***-**-dddd`).
  The EIN pattern needs dashes. User chose: add a standalone 9-digit rule (`ID9`, `NINE_RE`) - matches exactly 9
  digits not touching other digits, `. , $ -` before, or a decimal/thousands group after. Redacts 9-digit account
  numbers and CUSIPs as a side effect. Applies to every future client. Tests: `redactor/test_redact.py` 95/95;
  `review` unittest 45. That first output (`clientje3`) predates the rule and must not go to the API.

### Path A run prepared (21 Sep, same session)
- `client_bh1` (redacted, 11/11 OK incl. `--ocr`, 9-digit rule in): independent masked check clean (no strict SSN/EIN shape,
  no standalone 9-digit, no metadata/annotations, no unreadable OCR page). File #9 is the return: parses as a 1040, 25a has a
  value, arithmetic PASS. The source folder also held **3 .jpeg files** (1 1099-INT, 2 W-2, user-confirmed) that the redactor
  skipped (PDF only).
- New `review/img_to_pdf.py`: JPEG/PNG -> one-page PDF (EXIF rotation applied, EXIF dropped), then `redact.py --prompt --ocr`.
  Phone photos are lower-quality OCR input than scans; one that reads under the confidence cutoff stays REVIEW and is not sent.
- **User decisions:** model `claude-sonnet-5`; gate = the user's terminal result (11/11 OK) plus the driver's own generic
  re-check (names cannot be re-checked without knowing them); W-2 box 2 compares to line **25a** (`compare.py`, replaces the
  SPEC §6 [FILL]).
- New `review/check4_run.py`: masked Path A driver (see its docstring). Tested end to end on synthetic docs with a stubbed
  extractor; NOT yet run against the API. Known risks for the real run: `max_tokens=2048` per call (a long consolidated
  statement may truncate), 100 DPI page images (small print on scanned pages), consolidated statements have no §5 eligibility
  gate so some may come back UNKNOWN/partial.

### First run on the 3 phone images (21 Sep) and the OCR re-pass
`img_to_pdf.py` + `redact.py --prompt --ocr` on the 3 JPEGs (1 INT, 2 W-2): 2 OK, 1 FAIL. The FAIL (a W-2) was the
verify step working: after redaction, a second OCR read still saw an EIN-shaped and a 9-digit string that the first read
had not flagged (detection found 2 EIN, 0 ID9; verify found EIN + ID9). Cause not inspected (a FAIL/REVIEW file is not
opened); consistent with OCR reading a photo differently from pass to pass. The FAIL output was moved out of
`client_bh1_img` to `client_bh1_img_FAILED_do_not_send/` (an output file next to OK ones could otherwise be picked up by
`check4_run.py`, whose own OCR re-check can read the page differently and pass it).
Fix (own feature, not new scope): `redactor.redact.redact_and_verify` - when the ONLY leftovers are `pN-ocr:` ones, redact the
output again from what OCR sees in it, up to 2 extra passes, then verify again; text-layer/metadata/annotation leftovers are
never retried. The status line shows `passes=N` when N > 1. Still FAIL if it does not converge. Same-engine caveat unchanged.

## Session decisions (22 Sep): eligibility gate, IRS copy-page dedup, OCR redaction false-OK

**User decision:** build the §5.2 eligibility gate at document level only (not return-level) to save time on
`client_bh1` before the real Path A run. Separately: GROUP 1/GROUP 2 findings (SPEC.md §7.2, the [FILL] on
whether the split belongs in v1) - confirmed **v2**, once Sch C/E/F "workings" comparisons are in scope; Group
1's value depends on there being a workings source to check the client's own figures against, which v1 does
not have.

### Built (22 Sep)
- **`review/eligibility.py`** - content-based (pdfplumber text, no model) detection of consolidated 1099s
  (1099-B present, or generic "consolidated statement" wording), Schedule K-1, 1099-OID. Wired into
  `check4_run.py` ahead of the redaction gate, so excluded files are never OCR'd or sent - real saving
  confirmed on `client_bh1`'s dry run: 3 Morgan Stanley consolidated statements (2 pages each, image-only)
  skipped, only 7 of 10 files gated. Does **not** cover the rest of SPEC.md §5.2/§5.3 (Sch E/F, Sch C home
  office, 1099-S, seller-financed mortgage interest) - those are properties of the Drake return, not a source
  document, and need more return parsing than `drake.py` has. Still open, matching ARCHITECTURE.md §7.1.
  Tests: `test_eligibility.py`, 8/8.
- **Page-relevance discussion**, prompted by the user's experience filtering pages in the stock processor
  (pdf24) before conversion. Sketched general-then-specific "irrelevance" criteria as an explicitly
  modifiable list (Tier 0: boilerplate cuttable before redaction even runs; Tier 1: relevance to the
  return's scope). Tier 0/1 general filtering **not built** - needs a real multi-client document corpus to
  grow the list against safely; building it against one client's documents risks overfitting to that one
  client's boilerplate. One concrete, buildable case fell out of this discussion and WAS built:
- **`review/page_filter.py`** - W-2, 1099-INT and 1099-DIV all legally print 2-4 numbered IRS copies (Copy
  A/B/C/D/1/2 - same box values, different footer/legal text) within the same 1-2 page document. Distinct
  from SPEC.md §4.1's existing "Box 17 can repeat for multi-state withholding" note - that is genuine
  additional data; a repeated IRS copy is not, and sending every copy risked double-counting a repeatable
  field (`box_17_state_income_tax`) if the model read duplicate copies as distinct entries. Drops every copy
  page after the first, before the model call - a structural fix (never send the duplicate), not reliance on
  the model to notice. Dropped page indices are recorded on `ExtractionResult.dropped_pages` and printed by
  `check4_run.py` - never silent, per the Auditability constraint (SPEC.md §2). **Known unresolved risk:** a
  genuinely multi-state W-2 could print a *different* state's box 17 on a state-specific copy rather than a
  true duplicate; the page-designator-only rule can't tell those apart without reading box 17 first, which is
  what this step runs ahead of. Only text-layer pages are checked - an image-only copy page is not caught.
  Tests: `test_page_filter.py`, 7/7.
- `extract.py`'s per-call output token cap raised 2048 -> 4096 (`DEFAULT_MAX_TOKENS`); a document with several
  populated `other_boxes` entries or several W-2 states in box 17 could otherwise truncate. `check4_run.py`
  gained `--max-tokens` to override per run.

### Found (22 Sep): OCR-redacted `OK` can still leave real text exposed - partially fixed, not resolved
User visually caught a phone-photo W-2 that `redact.py --prompt --ocr` reported `OK` with the SSN still
plainly visible. Investigated with `redactor/diag_redact.py`, extended for the occasion (it previously only
covered the text-layer path - silently a no-op on an image-only page, which this was):
- Added `--prompt` (file/pages/names/SSNs asked interactively, matching `redact.py --prompt`'s reasoning -
  keeps them off the command line and shell history; a `--names "..."` flag example is exactly what led the
  user to paste a real name into this session earlier in the day).
- Added full OCR-path diagnostics: OCR words read + computed boxes, and an independent OCR re-read of the
  redacted output (what `verify()` itself checks), plus a top-line `redact_and_verify()` verdict using the
  real production function.
- **Root cause:** not a coordinate/box-placement bug - every occurrence the tool DID find had correct box
  math, including matching 3 stacked copies of the same W-2 in one photo. `redact_and_verify()`'s existing
  retry only fires when its own `verify()` re-read catches a miss; OCR is not perfectly repeatable, so if that
  same run's verify pass *also* independently misses the same spot detection missed, the retry never fires
  and the file reports clean with real text left. Reproduced twice: once by chance in production, once
  deliberately by re-running the diagnostic fresh (which got a different OCR roll and self-corrected).
- **Fix:** `redact_and_verify()` gained `confirm_passes` (default 1) - once `verify()` first comes back clean
  on a page that used OCR, one more independent OCR re-read must also come back clean before it's trusted; a
  catch feeds back into the existing retry (still capped at `extra_passes`). Regression-tested: 6 new mocked
  unit tests (`redactor/test_redact_and_verify.py`, no tesseract needed) plus 2 new tests in
  `review/test_redact_wrapper.py::OcrTests`, including a reproduction of the exact double-miss scenario.
- **This fix did NOT fully resolve it.** Re-tested on the same real file after the fix landed: result came
  back `passes=3, leftovers=[]` ("OK"), but the user again visually confirmed the SSN was exposed. `counts`
  showed `ID9: 1` against `3` for every other pattern on the page (one per each of the 3 stacked copies) - 2
  of 3 SSN occurrences were never detected by any pass (detection, retry, or either confirmation read). Unlike
  the first case, this does not look like random intermittent OCR variance a re-read can fix - it looks like
  OCR consistently failing to read that one specific occurrence every time (e.g. glare/skew/contrast at that
  exact spot in the photo). **Logged as OPEN/UNRESOLVED in `PARKING_LOT.md`.** Conclusion: an `OK` status on
  any OCR'd/image-only page must not be trusted by itself - this is no longer a "weaker guarantee" caveat, it
  is a confirmed, reproduced gap, and manual visual review of every OCR'd page is a hard requirement until a
  real fix (likely photo preprocessing before OCR, or a low-confidence-near-label heuristic that forces
  REVIEW) is built and verified against this same file. Neither is built yet.

### Committed (22 Sep)
`2a439bc` (local, unpushed): `eligibility.py`, `page_filter.py`, the `max_tokens` bump, the `confirm_passes`
fix, `diag_redact.py`'s `--prompt`/OCR diagnostics, and all associated tests/docs. Also added
`review_runs_redacted/` and `review_runs_names.json` to `.gitignore` - real client data, was untracked and
unignored until now.
