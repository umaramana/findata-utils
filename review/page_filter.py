"""Page-level filtering within an in-scope document.

Distinct from eligibility.py, which excludes a whole document. This drops
specific pages from what's sent to the extraction model, while the document
is still redacted in full as normal - dropping a page here never changes
what gets PII-scanned, only what gets structured. Every drop is reported
(caller logs it), never silent - same principle as everywhere else in this
pipeline (§7.1, eligibility.py's reason strings).

First case (22 Sep): IRS copy duplicates. A W-2, 1099-INT, and 1099-DIV all
legally print 2-4 numbered copies (e.g. "Copy B - To Be Filed With
Employee's FEDERAL Tax Return", "Copy C - For EMPLOYEE'S RECORDS", "Copy 2 -
To Be Filed With Recipient's State..."). Same box values, different
footer/legal text, so an exact-text or exact-image duplicate check won't
catch them - but the copy designator itself is standard, well-known text.
Sending every copy to the model wastes payload and, worse, risks a
repeatable field (e.g. W-2 box_17_state_income_tax) being double-counted if
the model doesn't realize the copies are the same page repeated. This
removes that risk structurally by never sending more than one copy, rather
than relying on the model to notice.

Known risk, not solved here: a genuinely multi-state W-2 sometimes prints
one state's box 17 on "Copy B" and a *different* state's box 17 on a
state-specific copy (e.g. "Copy 2"). A page-count-only rule can't tell that
apart from a true duplicate without reading box 17 itself - which is the
verified value this filter runs before extraction ever produces. Callers
must log which pages were dropped (not just how many) so this is auditable,
not silently lost; see check4_run.py's per-file output.

Only applies to pages with a text layer - an image-only copy page isn't
caught yet (would need the redaction OCR pass reused here; see
PARKING_LOT.md). Meant to grow: add new cases in the same shape as this one.
"""
import re

_COPY_DESIGNATOR_RE = re.compile(r"\bcopy\s*[abcd12]\b", re.I)


def copy_pages_to_drop(page_texts: list[str]) -> list[int]:
    """0-based page indices to exclude from the model payload: every page
    after the first that carries an IRS copy designator (Copy A/B/C/D/1/2).
    Keeps the first copy encountered, in page order.

    page_texts[i] is page i's full text; pass "" for an image-only page -
    it's left alone (can't be checked for a designator without OCR here)."""
    copy_pages = [i for i, t in enumerate(page_texts) if t and _COPY_DESIGNATOR_RE.search(t)]
    return copy_pages[1:]
