"""Step 1 - field extraction. Two independent paths, one pipeline (§4.0).

Path A (extract_api): sends redacted page images to the Claude API.
Path B (extract_local): sends the original pages' text layer, as lines of
words with positions, to a local Ollama model - text only, no images (12 Nov
2026). A page with no text layer is UNREAD, never guessed. Fully local -
never imports or calls anything from `anthropic`.

Pipeline per document (SPEC-revision-extraction.md §4.0), steps 1-3 and 5-7
are code, step 4 is the only model call:
  1. pdfplumber word tokens (with x/y coordinates) per page.
  2. Page render to PNG, for the model's layout channel.
  3. Per-page routing: text+image / image-only / (whole file) unreadable.
  4. One model call per document: text tokens + images in, {form_type,
     fields} JSON out. Repeatable fields (e.g. multi-state W-2 box 17) are
     JSON lists of objects, not a single value.
  5. Verbatim verification - every value must appear in the document's
     text-layer tokens or it's rejected (set null, logged). A page with no
     text layer can't be checked - accepted, marked reduced confidence.
  6. Normalisation - strip commas/currency symbols, cast to float. Parse
     failure -> null, logged. Never coerce, never default to zero.
  7. Completeness check - a required field left null makes the whole
     document "partially extracted", naming the field. Never summed as zero
     (compare.py already skips non-numeric/None values, so this holds without
     compare.py needing to know about partial extraction explicitly).

Known gap: the model's output schema (step 4) has no per-field page number,
but step 5 as specified checks a value against "that page's" tokens
specifically. Without page attribution from the model, true per-page
verification isn't possible from this schema. See _verify_and_normalize's
docstring for the conservative policy used instead.

Both extract_api and extract_local return an ExtractionResult - see that
class for the full shape, including the §7.1 status ("extracted" / "partial"
/ "reduced confidence") and per-field confidence.
"""
import base64
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF - Path A page rendering
import pdfplumber  # §4.0 step 1 - text tokens with coordinates
import requests

import page_filter

DEFAULT_API_MODEL = "claude-sonnet-5"  # was "claude-sonnet-4-6" - not a real model ID, would 404
DEFAULT_OLLAMA_URL = "http://localhost:11434"
# Was 2048 - too tight for a document with several populated "other_boxes" entries (§4.2/§4.3's
# "extract every populated box") or several W-2 states in box_17. This is output-only (the request
# side has its own budget, _MAX_TOKENS_PER_PAGE_IN_PROMPT); raising it costs a little more only if
# the model actually generates that much. See check4_run.py's --max-tokens for a per-run override.
DEFAULT_MAX_TOKENS = 4096
# 200 DPI made local vision inference impractically slow on constrained
# hardware (CPU-only, low RAM) - each page tiles into many 512-token image
# batches for the vision encoder, and that tiling, not generation length, is
# the actual bottleneck. 100 DPI is still legible for form text and cuts
# tile count substantially; raise it back if a beefier Path B host allows.
DEFAULT_RENDER_DPI = 100
# Path B context sizing (12 Nov 2026). Ollama's default context silently cut
# real pages and it ignores an undersized num_ctx (answers "stop" anyway), so
# num_ctx is set on every call from the prompt: the spike measured ~2.3
# characters per token on line-grouped text; 2 is the safe side. The output
# budget is also num_predict. No per-page word cap - every word is sent.
_CHARS_PER_TOKEN = 2
_LOCAL_OUTPUT_TOKENS = 1024
# Words whose tops are within this many points of a line's first word share the line.
_LINE_TOLERANCE = 3
# Path A only (word@(x,y) prompt). Path B has no cap since 12 Nov 2026; Path A
# still cuts every real IRS page (180-480 words) - see PARKING_LOT.md.
_MAX_TOKENS_PER_PAGE_IN_PROMPT = 150

# A failed gate on any item of these fields makes the document "partial"
# (decision of 12 Nov 2026); other optional fields are named but don't.
_PARTIAL_IF_ANY_ITEM_FAILS = {"box_17_state_income_tax"}

SYSTEM_PROMPT = (
    "You label fields on a single US tax document page image, using the "
    "provided text tokens as ground truth for exact wording and values. "
    "You structure - you never sum, never compare to another document, "
    "never guess. Copy every value exactly as printed. If a value is not "
    "present, omit its field or use null - never invent one. "
    "Return only JSON, no preamble."
)

# Path B is text only - the model never sees an image.
LOCAL_SYSTEM_PROMPT = (
    "You label fields on a US tax document from its text layer, given as "
    "lines of words with each line's position on the page (y = height from "
    "the top, x = where the line starts). "
    "You structure - you never sum, never compare to another document, "
    "never guess. Copy every value exactly as printed. If a value is not "
    "present, omit its field or use null - never invent one. "
    "Return only JSON, no preamble."
)

# Field names the model is asked to use per form type, so compare.py can map
# extracted fields to Drake return lines deterministically. Sourced from the
# real "Return Validation Tool - v1 Spec" §4.1-4.3 (found and added to this
# repo 2026-09-15; an earlier session had guessed these against no spec at
# all). 1098 is dropped - real SPEC.md §1/§10 explicitly puts it out of v1
# scope, which this session had gotten wrong before that document turned up.
#
# §4.2/§4.3 say "extract every populated box" (INT boxes 5-17, DIV boxes
# 2-13), not just the comparison-relevant ones. Rather than name all ~15
# per form individually, those are folded into one repeatable "other_boxes"
# field (list of {"box", "label", "value"}) - naming each one would widen
# the requested-field list well past what this session's harness run found
# stable on a small local vision model (unrequested/extra fields were the
# actual source of instability, not the count of requested ones - see
# SPEC-revision-extraction.md §4.0.9 notes). The boxes that drive a
# comparison (or are explicitly named in §4.1-4.3's table) are still named
# fields, since those need individually-verified values, not a bag of extras.
_FORM_FIELDS = {
    "W-2": ["box_1_wages", "box_2_federal_withheld", "box_17_state_income_tax"],
    "1099-INT": [
        "box_1_interest_income",              # sums into line 2b
        "box_2_early_withdrawal_penalty",
        "box_3_us_savings_bonds_treasury_interest",  # sums into line 2b
        "box_4_federal_withheld",
        "box_8_tax_exempt_interest",           # sums into line 2a (with DIV box 12)
        "other_boxes",                         # boxes 5-17 except account number
    ],
    "1099-DIV": [
        "box_1a_ordinary_dividends",           # compares to line 3b
        "box_1b_qualified_dividends",          # SPEC §4.3 [FILL] - extracted, not yet compared
        "box_4_federal_withheld",
        "box_12_exempt_interest_dividends",    # sums into line 2a (with INT box 8)
        "other_boxes",                         # boxes 2-13 except account number
    ],
}

# Repeatable fields are lists of objects (e.g. {"state": "NC", "amount":
# "3100.00"}) rather than a single value - multi-state W-2 box 17 is the
# motivating case (§4.0 step 4). Anything not listed here is a scalar field.
_REPEATABLE_FIELDS = {
    "W-2": {"box_17_state_income_tax"},
    "1099-INT": {"other_boxes"},
    "1099-DIV": {"other_boxes"},
}

# Fields whose absence makes a document "partially extracted" (§4.0 step 7).
# NOT "every field minus repeatables" - real-world 1099s legitimately leave
# most boxes blank (box 2/4/8 on a 1099-INT, 1b/4/12 on a 1099-DIV are often
# zero or absent), so treating them as required would flag ordinary documents
# as partial. Required is narrowed to the field(s) that are (a) effectively
# always populated on a real document of that type and (b) drive a required
# comparison - i.e. absence there is much more likely a genuine extraction
# miss than a blank box. Everything else in _FORM_FIELDS is "extract if
# present."
_REQUIRED_FIELDS = {
    "W-2": ["box_1_wages", "box_2_federal_withheld"],
    "1099-INT": ["box_1_interest_income"],
    "1099-DIV": ["box_1a_ordinary_dividends"],
}

_FORM_PATTERNS = [
    ("W-2", re.compile(r"\bw ?-?2\b")),
    ("1099-INT", re.compile(r"\b1099 ?-?int\b")),
    ("1099-DIV", re.compile(r"\b1099 ?-?div\b")),
]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_MONEY_STRIP_RE = re.compile(r"[,$\s]")


class RedactionGateError(RuntimeError):
    """Raised when code tries to send an unverified/unredacted file to the cloud path."""


class UnreadableDocument(RuntimeError):
    """File would not open at all (§3.1: unreadable files are a first-class
    output category - must be reported with a reason, never counted as
    zero). Distinct from RedactionGateError and from a model/network
    failure - callers should report this as its own step, not lump it in
    with "extraction failed"."""


class ExtractionFailed(RuntimeError):
    """The model's reply can't be used - not valid JSON, the wrong shape, cut
    short, or the prompt is too long for the model. Never turned into empty
    fields; run.py reports it as FAIL in the unread list."""


@dataclass
class ExtractionResult:
    form_type: str
    source_file: str
    extraction_mode: str  # "api" | "local"
    extraction_time_ms: int
    fields: dict = field(default_factory=dict)  # field_name -> float | list[dict] | None
    field_confidence: dict = field(default_factory=dict)  # field_name -> "verified" | "reduced" | "rejected"
    missing_required: list = field(default_factory=list)  # required field names that came back null
    verification_failures: list = field(default_factory=list)  # field names rejected by step 5
    page_routes: list = field(default_factory=list)  # per page, in order: "text" | "image"
    dropped_pages: list = field(default_factory=list)  # 0-based indices excluded as IRS copy duplicates (page_filter.py)
    unread_pages: list = field(default_factory=list)  # {"source_file", "page" (1-based, original file), "reason"}
    parse_failures: list = field(default_factory=list)  # money fields answered with something that isn't a number

    @property
    def status(self) -> str:
        """§7.1 report state. Unopenable files never reach this class at all
        - they're raised as UnreadableDocument before an ExtractionResult can
        be built, and the caller (run.py) reports them as "unread".

        "partial" = a required field is missing (a required field that failed
        the gate or didn't parse is null, so it lands here), a box 17 item
        failed the gate, or a page is UNREAD. A rejected optional field is
        named in the failures but doesn't change the status."""
        if (self.missing_required or self.unread_pages
                or _PARTIAL_IF_ANY_ITEM_FAILS & set(self.verification_failures)):
            return "partial"
        if any(c == "reduced" for c in self.field_confidence.values()):
            return "reduced confidence"
        return "extracted"

    def to_dict(self):
        return {
            "form_type": self.form_type,
            "source_file": self.source_file,
            "extraction_mode": self.extraction_mode,
            "extraction_time_ms": self.extraction_time_ms,
            "fields": self.fields,
            "field_confidence": self.field_confidence,
            "missing_required": self.missing_required,
            "verification_failures": self.verification_failures,
            "page_routes": self.page_routes,
            "dropped_pages": self.dropped_pages,
            "unread_pages": self.unread_pages,
            "parse_failures": self.parse_failures,
            "status": self.status,
        }


def guess_form_type(filename: str) -> str | None:
    """Detect form type from a filename; None means "let the model identify it"."""
    norm = re.sub(r"[^a-z0-9]+", " ", filename.lower())
    for label, rx in _FORM_PATTERNS:
        if rx.search(norm):
            return label
    return None


# ---------------------------------------------------------------------------
# §4.0 step 1 - text tokens (with coordinates) per page
# ---------------------------------------------------------------------------

def extract_page_tokens(pdf_path: Path) -> list[list[dict]]:
    """Per-page list of {"text", "x0", "top"} word tokens via pdfplumber.

    Coordinates, not extract_text()'s flat string - extract_text() scrambles
    reading order on multi-column form layouts, and coordinates are what
    make box position legible to the model (§4.0 step 1). An empty per-page
    list means that page has no text layer (§4.0 step 3: image-only route).

    Raises UnreadableDocument if the file won't open at all - never returns
    an empty *document* result silently (§3.1)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return [
                [{"text": w["text"], "x0": round(w["x0"], 1), "top": round(w["top"], 1)}
                 for w in page.extract_words()]
                for page in pdf.pages
            ]
    except Exception as e:
        raise UnreadableDocument(f"{pdf_path.name}: file will not open ({type(e).__name__}: {e})") from e


def _page_route(tokens: list[dict]) -> str:
    return "text" if tokens else "image"


def _drop_copy_pages(page_tokens: list[list[dict]], page_routes: list[str], images: list) -> tuple:
    """Filters out IRS copy-duplicate pages (page_filter.py) before the model
    ever sees them. Returns (page_tokens, page_routes, images, dropped) -
    dropped is the 0-based indices removed, for the caller to log (never
    silent - see page_filter.py's module docstring on the multi-state risk)."""
    page_texts = [" ".join(t["text"] for t in tokens) for tokens in page_tokens]
    dropped = page_filter.copy_pages_to_drop(page_texts)
    if not dropped:
        return page_tokens, page_routes, images, []
    keep = [i for i in range(len(page_tokens)) if i not in dropped]
    return ([page_tokens[i] for i in keep], [page_routes[i] for i in keep],
            [images[i] for i in keep], dropped)


def _normalize_for_match(s) -> str:
    """Loose whitespace/comma/currency-insensitive normalization so a
    verbatim check (§4.0 step 5) doesn't fail over a stray space or a
    thousands-comma the model dropped."""
    return re.sub(r"\s+", "", str(s)).replace(",", "").replace("$", "")


def _page_text_blob_norm(tokens: list[dict]) -> str:
    return _normalize_for_match(" ".join(t["text"] for t in tokens))


def _page_lines(tokens: list[dict]) -> list[tuple[float, float, str]]:
    """Words grouped into lines by height: (top, x0 of first word, text), top to
    bottom, each line's words left to right. A word joins a line if its top is
    within _LINE_TOLERANCE of the line's first word."""
    rows = {}
    for t in sorted(tokens, key=lambda t: (t["top"], t["x0"])):
        key = next((k for k in rows if abs(k - t["top"]) <= _LINE_TOLERANCE), t["top"])
        rows.setdefault(key, []).append(t)
    out = []
    for top, words in sorted(rows.items()):
        words.sort(key=lambda w: w["x0"])
        out.append((top, words[0]["x0"], " ".join(w["text"] for w in words)))
    return out


# A space pdfplumber put inside one printed number: "75, 000.00", "$ 75,000.00", "75,000 .00".
_SPLIT_NUMBER_RE = re.compile(r"(?<=\d,) (?=\d{3}\b)|(?<=\$) (?=\d)|(?<=\d) (?=[.,]\d)")
_NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")


def _line_numbers(line: str) -> set[float]:
    """Every whole number printed on a line, as a float - "1,500.00" is 1500.0,
    never 500.0. Split numbers are joined back first."""
    joined = _SPLIT_NUMBER_RE.sub("", line).replace(",", "").replace("$", "")
    return {float(n) for n in _NUMBER_RE.findall(joined)}


# ---------------------------------------------------------------------------
# §4.0 steps 5-6 - verification + normalisation
# ---------------------------------------------------------------------------

def _to_float(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(_MONEY_STRIP_RE.sub("", str(raw)))
    except (ValueError, TypeError):
        return None


def _on_page(value, page_numbers: set[float], text_blobs_norm: list[str]) -> bool:
    """A number must equal a whole number on one of the text pages' lines
    (decision of 12 Nov 2026: never a fragment - "500.00" is not on a page
    showing "1,500.00"). Text (a state code, a box label) is still matched
    loosely against the page text, spaces/commas/$ ignored."""
    number = _to_float(value)
    if number is not None:
        return number in page_numbers
    return any(_normalize_for_match(value) in blob for blob in text_blobs_norm)


def _verify_and_normalize(raw_value, page_numbers: set[float], text_blobs_norm: list[str],
                          has_image_only_page: bool):
    """Returns (normalized_value, confidence) - confidence is "verified",
    "reduced", or "rejected".

    Policy (see module docstring for why this isn't strict per-page
    matching - the model's output has no per-field page number):
      - No text-bearing page in the document at all -> nothing can ever be
        verified; accept everything at "reduced" confidence.
      - Value found in ANY text-bearing page -> "verified".
      - Value not found, but has_image_only_page (Path A only: that model
        sees the page images) -> it might genuinely belong to that page;
        accept at "reduced" rather than reject. Path B passes False - a
        text-only model can't have read an image page.
      - Value not found otherwise -> the hallucination this gate exists to
        catch; reject (null), "rejected".

    Repeatable fields (list of dicts) are checked item-by-item; an item that
    fails, or is not a dict at all, is dropped from the list and the field is "rejected" (so it is
    named in the failures), even if other items pass."""
    if isinstance(raw_value, list):
        out_items, any_reduced, any_rejected = [], False, False
        for item in raw_value:
            if not isinstance(item, dict):
                any_rejected = True  # not a pair - dropped and named, never skipped silently
                continue
            matched = all(_on_page(v, page_numbers, text_blobs_norm) for v in item.values())
            norm_item = {k: (_to_float(v) if _to_float(v) is not None else v) for k, v in item.items()}
            if matched or not text_blobs_norm:
                out_items.append(norm_item)
                any_reduced = any_reduced or not text_blobs_norm or not matched
            elif has_image_only_page:
                out_items.append(norm_item)
                any_reduced = True
            else:
                any_rejected = True
        if any_rejected:
            return out_items, "rejected"
        return out_items, "reduced" if any_reduced else "verified"

    if raw_value is None:
        return None, "verified"
    if not text_blobs_norm:
        return _to_float(raw_value), "reduced"
    if _on_page(raw_value, page_numbers, text_blobs_norm):
        return _to_float(raw_value), "verified"
    if has_image_only_page:
        return _to_float(raw_value), "reduced"
    return None, "rejected"


def _is_parse_failure(raw_value) -> bool:
    """A money field answered with something that isn't a number ("N/A",
    "see attached"). Empty or null is a blank box, not a parse failure."""
    return (raw_value is not None and not isinstance(raw_value, list)
            and str(raw_value).strip() != "" and _to_float(raw_value) is None)


def _completeness(form_type: str, fields: dict) -> list[str]:
    """§4.0 step 7 - required fields left null after verification."""
    return [f for f in _REQUIRED_FIELDS.get(form_type, []) if fields.get(f) is None]


def _verify_normalize_and_check(form_type: str, raw_fields: dict, page_routes: list[str],
                                 page_tokens: list[list[dict]], image_pages_seen: bool = True) -> tuple:
    """image_pages_seen: the model was sent the page images (Path A), so a
    value not in the text may be read off an image-only page."""
    text_pages = [t for t, r in zip(page_tokens, page_routes) if r == "text"]
    text_blobs_norm = [_page_text_blob_norm(t) for t in text_pages]
    page_numbers = {n for t in text_pages for _, _, line in _page_lines(t) for n in _line_numbers(line)}
    has_image_only_page = image_pages_seen and "image" in page_routes

    money_fields = set(_FORM_FIELDS.get(form_type, [])) - _REPEATABLE_FIELDS.get(form_type, set())

    fields, confidence, failures, parse_failures = {}, {}, [], []
    for field_name, raw_value in raw_fields.items():
        if field_name in money_fields and _is_parse_failure(raw_value):
            fields[field_name], confidence[field_name] = None, "rejected"
            parse_failures.append(field_name)
            continue
        normalized, conf = _verify_and_normalize(raw_value, page_numbers, text_blobs_norm, has_image_only_page)
        fields[field_name] = normalized
        confidence[field_name] = conf
        if conf == "rejected":
            failures.append(field_name)

    missing = _completeness(form_type, fields)
    return fields, confidence, failures, missing, parse_failures


# ---------------------------------------------------------------------------
# §4.0 step 4 - model prompt (shared by both paths)
# ---------------------------------------------------------------------------

def _schema_prompt(form_hint: str | None) -> str:
    # §4.0.9 harness run against a real multi-box W-2 (2026-09-15) showed the
    # required fields rock-stable across repeats, but the model volunteered a
    # much larger, inconsistent set of extra boxes when told to "extract all
    # financial fields" - unrequested boxes appeared on 2/3 runs and not the
    # third. Constraining the output to exactly the field list removes that
    # source of instability at the root rather than filtering it out after -
    # but that constraint only means something once form_type is known, so
    # the no-hint branch (production default - §3.1, forms aren't pre-sorted)
    # still has to let the model extract whatever it finds on the first pass.
    if form_hint:
        field_names = _FORM_FIELDS.get(form_hint, [])
        repeatable = _REPEATABLE_FIELDS.get(form_hint, set())
        field_hint = f" Expected fields: {', '.join(field_names)}."
        if "other_boxes" in repeatable:
            field_hint += (
                ' "other_boxes" covers every other populated box on the form except the account '
                "number - return it as a JSON list of objects, e.g. "
                '[{"box": "5", "label": "Investment expenses", "value": "40.00"}], not a single value.'
            )
        if form_hint == "W-2" and "box_17_state_income_tax" in repeatable:
            field_hint += (
                ' box_17_state_income_tax repeats if the form shows it more than once - return it '
                'as a JSON list of objects, e.g. [{"state": "NC", "amount": "3100.00"}, '
                '{"state": "SC", "amount": "420.00"}], not a single value.'
            )
        extract_instruction = (
            f"This is a {form_hint}.{field_hint} Extract ONLY the fields listed above - "
            "do not add any field not listed, even if you see other boxes on the page."
        )
    else:
        extract_instruction = (
            "Identify which of these US tax forms this is: W-2, 1099-INT, or 1099-DIV, "
            "then extract its financial fields."
        )
    return (
        f"{extract_instruction} Return as JSON: "
        '{"form_type": "W-2" | "1099-INT" | "1099-DIV", "fields": {"field_name": value}}. '
        '"form_type" must be exactly one of those three strings, never the list itself.'
    )


def _pages_prompt_block(page_tokens: list[list[dict]], page_routes: list[str]) -> str:
    lines = []
    for i, (tokens, route) in enumerate(zip(page_tokens, page_routes), start=1):
        if route == "image":
            lines.append(f"Page {i}: no text layer - image only, read it visually.")
            continue
        shown = tokens[:_MAX_TOKENS_PER_PAGE_IN_PROMPT]
        token_list = ", ".join(f'"{t["text"]}"@({t["x0"]},{t["top"]})' for t in shown)
        truncated = " [...truncated]" if len(tokens) > _MAX_TOKENS_PER_PAGE_IN_PROMPT else ""
        lines.append(f"Page {i} text tokens (word@(x,y), not necessarily in reading order): {token_list}{truncated}")
    return "\n".join(lines)


def _user_prompt(form_hint: str | None, page_tokens: list[list[dict]], page_routes: list[str]) -> str:
    return f"{_schema_prompt(form_hint)}\n\n{_pages_prompt_block(page_tokens, page_routes)}"


def _local_user_prompt(form_hint: str | None, text_pages: list[tuple[int, list[dict]]]) -> str:
    """Path B: text pages only, as `y=<top> x=<x0>: words` lines (spike Option 2,
    12 Nov 2026). Pages are numbered as in the original file."""
    blocks = []
    for page_no, tokens in text_pages:
        lines = [f"y={round(top)} x={round(x0)}: {text}" for top, x0, text in _page_lines(tokens)]
        blocks.append(f"Page {page_no} text lines (y = height from top, x = line start):\n" + "\n".join(lines))
    return f"{_schema_prompt(form_hint)}\n\n" + "\n\n".join(blocks)


def _coerce_fields_dict(raw) -> dict:
    """The model doesn't always honor the {"field_name": value} dict shape.
    Two shape variants observed live so far on qwen2.5vl:3b, both handled here:

      1. (2026-09-15, W-2 run) A JSON list of {"field_name": ..., "value": ...}
         objects - likely because the box-17 repeatable-field example in the
         prompt shows a list-of-objects shape, and the model over-generalized
         that to every field, not just the repeatable one.
      2. (2026-09-15, 1099-INT run, after the field-table expansion added more
         named fields) A JSON list of single-key {field_name: value} dicts,
         e.g. {"box_1_interest_income": "1,200.00"} - here the model's own
         dict key already IS the field name, there's no separate name lookup.

    Distinguish them by whether the item carries a recognizable name key
    alongside a value/amount key (variant 1) - if not, the item's own keys
    are the field names to merge in directly (variant 2). Coerce back to a
    flat dict rather than reject/crash on a shape variant that's likely to
    recur with a small local model."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        out = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            has_value_key = "value" in item or "amount" in item
            name = item.get("field_name") or item.get("name") or item.get("field")
            if name is None and has_value_key:
                name = item.get("box")
            if name is not None and has_value_key:
                out[name] = item.get("value", item.get("amount"))
            else:
                out.update(item)
        return out
    return {}


def _parse_json_fields(text: str) -> dict:
    m = _JSON_FENCE_RE.search(text)
    payload = (m.group(1) if m else text).strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ExtractionFailed(f"model reply is not valid JSON ({e})") from e
    if not isinstance(data, dict) or "form_type" not in data or "fields" not in data:
        raise ExtractionFailed("model reply is missing form_type/fields keys")
    data["fields"] = _coerce_fields_dict(data["fields"])
    return data


def _resolve_form_type(data: dict, form_hint: str | None) -> str:
    """The model is asked to pick exactly one of the four known forms - if it
    echoes the enum back verbatim (observed on the local model) or returns
    something else unrecognised, that's not a usable form_type; fall back to
    the filename hint, or UNKNOWN if there wasn't one."""
    candidate = data.get("form_type")
    if candidate in _FORM_FIELDS:
        return candidate
    return form_hint or "UNKNOWN"


def _pdf_to_page_pngs(path: Path, dpi: int = DEFAULT_RENDER_DPI) -> list[bytes]:
    doc = fitz.open(path)
    try:
        return [page.get_pixmap(dpi=dpi).tobytes("png") for page in doc]
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Path A - Claude API
# ---------------------------------------------------------------------------

def extract_api(redaction, client, model: str = DEFAULT_API_MODEL, form_hint: str | None = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS) -> ExtractionResult:
    """redaction is a redact.RedactionResult. Refuses to run unless it's
    verified OK. Text tokens and images both come from the redacted copy,
    not the original - redaction is the source this path extracts from, not
    a gate the document passes and is then forgotten (per SPEC-revision
    "Path A is blocked" section, "Open questions" resolution)."""
    if redaction.status != "OK" or redaction.redacted_path is None:
        raise RedactionGateError(
            f"refusing cloud call on unverified file {redaction.source_file!r} "
            f"(redaction status={redaction.status!r}); redaction is the gate for Path A"
        )

    t0 = time.monotonic()
    page_tokens = extract_page_tokens(redaction.redacted_path)
    page_routes = [_page_route(t) for t in page_tokens]
    images = _pdf_to_page_pngs(redaction.redacted_path)
    page_tokens, page_routes, images, dropped_pages = _drop_copy_pages(page_tokens, page_routes, images)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                      "data": base64.standard_b64encode(png).decode("utf-8")}}
        for png in images
    ]
    content.append({"type": "text", "text": _user_prompt(form_hint, page_tokens, page_routes)})

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = _parse_json_fields(text)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    form_type = _resolve_form_type(data, form_hint)
    fields, confidence, failures, missing, parse_failures = _verify_normalize_and_check(
        form_type, data.get("fields", {}), page_routes, page_tokens
    )

    return ExtractionResult(
        form_type=form_type,
        source_file=redaction.source_file,
        extraction_mode="api",
        extraction_time_ms=elapsed_ms,
        fields=fields,
        field_confidence=confidence,
        missing_required=missing,
        verification_failures=failures,
        page_routes=page_routes,
        dropped_pages=dropped_pages,
        parse_failures=parse_failures,
    )


# ---------------------------------------------------------------------------
# Path B - local Ollama vision model
# ---------------------------------------------------------------------------

def resolve_local_vision_model(ollama_url: str = DEFAULT_OLLAMA_URL, override: str | None = None) -> str:
    """Find the installed local vision model. Never hardcodes a tag - checks
    what's actually pulled locally. Which model to use is decided by the
    §4.0.9 harness (SPEC-revision-extraction.md), not by a name guess here:
    if exactly one model is installed, use it; if several, the caller must
    disambiguate with --local-model (or the harness's --model/--models)."""
    if override:
        return override
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
    except requests.RequestException as e:
        raise RuntimeError(
            f"Could not reach Ollama at {ollama_url} ({e}). Is `ollama serve` running?"
        ) from e
    if not models:
        raise RuntimeError(
            "No models found in the local Ollama library. Run `ollama pull <name>` "
            "for a vision-capable model, then re-run, or pass --local-model <name>."
        )
    if len(models) > 1:
        raise RuntimeError(
            f"Multiple local models installed ({models}) and none specified. "
            "Pass --local-model <name> (or --model / --models to the harness) to pick one."
        )
    return models[0]


def _model_context_length(ollama_url: str, model: str) -> int | None:
    """The model's maximum context, from /api/show; None if Ollama doesn't say."""
    try:
        resp = requests.post(f"{ollama_url}/api/show", json={"model": model}, timeout=30)
        resp.raise_for_status()
        info = resp.json().get("model_info", {})
    except requests.RequestException:
        return None
    return next((v for k, v in info.items() if k.endswith(".context_length")), None)


def _check_reply(reply: dict, num_ctx: int) -> None:
    """A reply cut short can still parse as JSON with fields missing - that
    must never look like a blank box. Ollama doesn't flag an overflowed
    context (spike, 12 Nov 2026), so the token counts are checked too."""
    if reply.get("done_reason") == "length":
        raise ExtractionFailed(f"model reply was cut short at {reply.get('eval_count')} output tokens")
    used = (reply.get("prompt_eval_count") or 0) + (reply.get("eval_count") or 0)
    if used >= num_ctx:
        raise ExtractionFailed(f"prompt and reply filled the context ({used} of {num_ctx} tokens)")


def extract_local(src_path: Path, ollama_url: str = DEFAULT_OLLAMA_URL, model: str | None = None,
                   form_hint: str | None = None) -> ExtractionResult:
    """Path B, text only. Pages with no text layer are listed in unread_pages
    (original page numbers) and never sent; if no page has text, the model
    isn't called and every required field is named as missing."""
    model = resolve_local_vision_model(ollama_url, override=model)
    t0 = time.monotonic()
    page_tokens = extract_page_tokens(src_path)
    page_routes = [_page_route(t) for t in page_tokens]
    unread_pages = [{"source_file": src_path.name, "page": i + 1, "reason": "no text layer"}
                    for i, r in enumerate(page_routes) if r == "image"]
    page_numbers = list(range(1, len(page_tokens) + 1))
    page_tokens, page_routes, page_numbers, dropped_pages = _drop_copy_pages(page_tokens, page_routes, page_numbers)
    text_pages = [(n, t) for n, t, r in zip(page_numbers, page_tokens, page_routes) if r == "text"]

    raw_fields, form_type = {}, form_hint or "UNKNOWN"
    if text_pages:
        prompt = f"{LOCAL_SYSTEM_PROMPT}\n\n{_local_user_prompt(form_hint, text_pages)}"
        num_ctx = math.ceil(len(prompt) / _CHARS_PER_TOKEN) + _LOCAL_OUTPUT_TOKENS
        context_length = _model_context_length(ollama_url, model)
        if context_length and num_ctx > context_length:
            raise ExtractionFailed(f"{src_path.name}: prompt (~{num_ctx} tokens) is too long for "
                                   f"the model's context ({context_length} tokens)")
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "format": "json",
                  "options": {"num_ctx": num_ctx, "num_predict": _LOCAL_OUTPUT_TOKENS}},
            # Was sized for image pages (~405s/page at 100 DPI on this CPU-only
            # 8GB box); a text-only page measured ~108s in the spike.
            timeout=900,
        )
        resp.raise_for_status()
        reply = resp.json()
        _check_reply(reply, num_ctx)
        data = _parse_json_fields(reply.get("response", ""))
        form_type = _resolve_form_type(data, form_hint)
        raw_fields = data.get("fields", {})
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    fields, confidence, failures, missing, parse_failures = _verify_normalize_and_check(
        form_type, raw_fields, page_routes, page_tokens, image_pages_seen=False
    )

    return ExtractionResult(
        form_type=form_type,
        source_file=src_path.name,
        extraction_mode="local",
        extraction_time_ms=elapsed_ms,
        fields=fields,
        field_confidence=confidence,
        missing_required=missing,
        verification_failures=failures,
        page_routes=page_routes,
        dropped_pages=dropped_pages,
        unread_pages=unread_pages,
        parse_failures=parse_failures,
    )
