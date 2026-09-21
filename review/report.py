"""Step 3 - single HTML report per run.

Sections: redaction (Step 0, for traceability), extraction trace, comparison
results, and (mode=both) an A/B summary. Any document that never got a usable
extraction is listed explicitly under "Unread documents" - never dropped.
"""
import html
import json
from pathlib import Path


def _field_diffs(a_fields: dict, l_fields: dict) -> list:
    diffs = []
    for key in sorted(set(a_fields) | set(l_fields)):
        av, lv = a_fields.get(key), l_fields.get(key)
        if key not in a_fields:
            diffs.append((key, "missing in api", av, lv))
        elif key not in l_fields:
            diffs.append((key, "missing in local", av, lv))
        elif isinstance(av, (int, float)) and isinstance(lv, (int, float)):
            if abs(av - lv) > 0.01:
                diffs.append((key, "value differs", av, lv))
        elif av != lv:
            diffs.append((key, "value differs", av, lv))
    return diffs


def compute_ab_summary(api_results: list, local_results: list, unread: list) -> list[dict]:
    api_by_file = {r.source_file: r for r in api_results}
    local_by_file = {r.source_file: r for r in local_results}
    api_unread = {u["source_file"] for u in unread if u["mode"] == "api"}
    local_unread = {u["source_file"] for u in unread if u["mode"] == "local"}
    all_files = sorted(set(api_by_file) | set(local_by_file) | api_unread | local_unread)

    rows = []
    for f in all_files:
        a, l = api_by_file.get(f), local_by_file.get(f)
        diffs = _field_diffs(a.fields, l.fields) if (a and l) else []
        rows.append({
            "source_file": f,
            "api_read": f not in api_unread,
            "local_read": f not in local_unread,
            "api_time_ms": a.extraction_time_ms if a else None,
            "local_time_ms": l.extraction_time_ms if l else None,
            "agree": (a is not None and l is not None and not diffs),
            "diffs": diffs,
        })
    return rows


def _esc(x) -> str:
    return html.escape(str(x))


def _status_badge(status: str) -> str:
    cls = {
        "OK": "badge-ok", "MATCH": "badge-ok", "EXTRACTED": "badge-ok",
        "REVIEW": "badge-warn", "REDUCED CONFIDENCE": "badge-warn",
        "FAIL": "badge-bad", "FLAG": "badge-bad", "NO DRAKE LINE": "badge-warn",
        "PARTIAL": "badge-bad",
    }.get(status, "badge-warn")
    return f'<span class="badge {cls}">{_esc(status)}</span>'


def _money(v) -> str:
    if v is None:
        return "-"
    return f"${v:,.2f}"


def _render_redaction(redaction_results: list) -> str:
    rows = []
    for r in redaction_results:
        detail = r.error or (", ".join(f"{k}={v}" for k, v in r.counts.items()) or "no matches")
        if r.no_text_pages:
            detail += f" | no text layer p{r.no_text_pages}"
        if r.leftovers:
            detail += f" | STILL PRESENT: {', '.join(r.leftovers)}"
        rows.append(
            f"<tr><td>{_esc(r.source_file)}</td><td>{_status_badge(r.status)}</td>"
            f"<td>{_esc(detail)}</td></tr>"
        )
    return f"""
    <section>
      <h2>Step 0 - Redaction</h2>
      <table>
        <thead><tr><th>File</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>{''.join(rows) or '<tr><td colspan="3">No documents</td></tr>'}</tbody>
      </table>
    </section>"""


_CONFIDENCE_TAG = {
    "verified": "",  # the normal case - no extra marker needed
    "reduced": " <em>(unverified - no text layer on this page)</em>",
    "rejected": " <em>(rejected - not found in document text)</em>",
}


def _render_extraction(extractions_by_mode: dict) -> str:
    blocks = []
    for mode, results in extractions_by_mode.items():
        rows = []
        for ex in results:
            field_lines = [
                f"{_esc(k)}: {_esc(v)}{_CONFIDENCE_TAG.get(ex.field_confidence.get(k, ''), '')}"
                for k, v in ex.fields.items()
            ]
            fields_html = "<br>".join(field_lines) or "<em>none</em>"
            if ex.missing_required:
                fields_html += f"<br><strong>missing required:</strong> {_esc(', '.join(ex.missing_required))}"
            rows.append(
                f"<tr><td>{_esc(ex.source_file)}</td><td>{_esc(ex.form_type)}</td>"
                f"<td>{_status_badge(ex.status.upper())}</td>"
                f"<td>{fields_html}</td><td>{ex.extraction_time_ms} ms</td></tr>"
            )
        blocks.append(f"""
      <h3>Path {'A (Claude API)' if mode == 'api' else 'B (Local)'}</h3>
      <table>
        <thead><tr><th>File</th><th>Form type</th><th>Status</th><th>Fields</th><th>Time</th></tr></thead>
        <tbody>{''.join(rows) or '<tr><td colspan="5">No documents extracted</td></tr>'}</tbody>
      </table>""")
    return f"""
    <section>
      <h2>Step 1 - Extraction trace</h2>
      {''.join(blocks)}
    </section>"""


def _render_comparison(comparisons_by_mode: dict) -> str:
    blocks = []
    for mode, rows in comparisons_by_mode.items():
        trs = []
        for row in rows:
            contrib = "<br>".join(
                f"{_esc(f)}: {_esc(fn)} = {_money(v)}" for f, fn, v in row.contributions
            ) or "<em>no contributing fields</em>"
            trs.append(
                f"<tr><td>{_esc(row.label)}</td><td>{_money(row.source_total)}</td>"
                f"<td>{_money(row.drake_line)}</td>"
                f"<td>{_money(row.diff) if row.diff is not None else '-'}</td>"
                f"<td>{_status_badge(row.status)}</td><td>{contrib}</td></tr>"
            )
        blocks.append(f"""
      <h3>Path {'A (Claude API)' if mode == 'api' else 'B (Local)'}</h3>
      <table>
        <thead><tr><th>Category</th><th>Source total</th><th>Drake line</th>
        <th>Diff</th><th>Status</th><th>Contributing fields</th></tr></thead>
        <tbody>{''.join(trs) or '<tr><td colspan="6">No comparison data</td></tr>'}</tbody>
      </table>""")
    return f"""
    <section>
      <h2>Step 2 - Comparison results</h2>
      {''.join(blocks)}
    </section>"""


def _render_ab_summary(ab_rows: list) -> str:
    if not ab_rows:
        return ""
    trs = []
    for row in ab_rows:
        if not (row["api_read"] and row["local_read"]):
            agree_cell = _status_badge("FAIL") + " missing extraction"
        else:
            agree_cell = _status_badge("MATCH" if row["agree"] else "FLAG")
        diffs_html = "<br>".join(
            f"{_esc(k)} ({_esc(reason)}): api={_esc(av)} local={_esc(lv)}"
            for k, reason, av, lv in row["diffs"]
        ) or ("<em>none</em>" if row["agree"] else "")
        api_time = f"{row['api_time_ms']} ms" if row["api_time_ms"] is not None else "-"
        local_time = f"{row['local_time_ms']} ms" if row["local_time_ms"] is not None else "-"
        trs.append(
            f"<tr><td>{_esc(row['source_file'])}</td>"
            f"<td>{'yes' if row['api_read'] else 'UNREAD'}</td>"
            f"<td>{'yes' if row['local_read'] else 'UNREAD'}</td>"
            f"<td>{agree_cell}</td><td>{api_time}</td><td>{local_time}</td>"
            f"<td>{diffs_html}</td></tr>"
        )
    return f"""
    <section>
      <h2>Step 3 - A/B summary</h2>
      <table>
        <thead><tr><th>File</th><th>API read?</th><th>Local read?</th><th>Agree?</th>
        <th>API time</th><th>Local time</th><th>Differences</th></tr></thead>
        <tbody>{''.join(trs)}</tbody>
      </table>
    </section>"""


def _render_unread(unread: list) -> str:
    if not unread:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(u['source_file'])}</td><td>{_esc(u['mode'])}</td>"
        f"<td>{_esc(u.get('step', ''))}</td><td>{_esc(u['reason'])}</td></tr>"
        for u in unread
    )
    return f"""
    <section>
      <h2>Unread documents</h2>
      <table>
        <thead><tr><th>File</th><th>Mode</th><th>Step</th><th>Reason</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>"""


_CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; margin: 0;
       background: #f7f7f8; color: #1a1a1a; padding: 24px 16px 64px; }
.wrap { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin-bottom: 4px; }
h2 { font-size: 1.15rem; margin-top: 40px; border-bottom: 2px solid #ddd; padding-bottom: 6px; }
h3 { font-size: 1rem; margin-top: 24px; color: #444; }
.meta { color: #555; font-size: 0.9rem; margin-bottom: 24px; }
.meta div { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 8px; background: #fff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
th, td { border: 1px solid #e2e2e2; padding: 8px 10px; text-align: left; vertical-align: top;
         font-size: 0.88rem; }
th { background: #f0f0f2; font-weight: 600; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.78rem;
         font-weight: 600; color: #fff; }
.badge-ok { background: #1a8a4a; }
.badge-bad { background: #c62828; }
.badge-warn { background: #b8860b; }
"""


def build_report(*, run_meta: dict, redaction_results: list, extractions_by_mode: dict,
                  unread: list, comparisons_by_mode: dict, ab_rows: list | None,
                  out_path: Path) -> Path:
    meta_html = "".join(f"<div><strong>{_esc(k)}:</strong> {_esc(v)}</div>" for k, v in run_meta.items())
    body = f"""<title>Tax Review Report</title>
<style>{_CSS}</style>
<div class="wrap">
  <h1>Tax Document Review Report</h1>
  <div class="meta">{meta_html}</div>
  {_render_redaction(redaction_results)}
  {_render_extraction(extractions_by_mode)}
  {_render_comparison(comparisons_by_mode)}
  {_render_ab_summary(ab_rows or [])}
  {_render_unread(unread)}
</div>"""
    out_path.write_text(body, encoding="utf-8")
    return out_path
