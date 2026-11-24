"""
report_generator.py - builds the downloadable reports and logs.

  * build_html_report()      -> one self-contained HTML data quality report
                                (open it in a browser, or press Ctrl+P and
                                 "Save as PDF" to get a PDF - no paid service)
  * validation_report_excel_bytes()
  * quality_report_excel_bytes()
  * history_to_csv_bytes() / history_to_json_bytes()

Every number in a report comes from the real dataset. All text that comes from
the user's data is HTML-escaped, so a malicious cell value cannot inject code
into the report.
"""

from __future__ import annotations

import base64
import html
import json

import pandas as pd

from core.data_utils import APP_NAME, APP_TAGLINE, APP_TITLE, APP_VERSION, COMPANY_NAME, DEVELOPER, format_bytes, now_str
from core.file_handler import dataframes_to_excel_bytes
from core.profiler import overall_profile, profile_dataframe
from core.quality_score import SCORE_METHOD_TEXT
from core.validation_engine import ValidationResult, describe_rule

HISTORY_COLUMNS = [
    "step", "timestamp", "operation", "columns", "parameters", "rows_before", "rows_after",
    "rows_affected", "cells_changed", "missing_before", "missing_after", "status", "notes",
]


# --------------------------------------------------------------------------
# History / comparison tables
# --------------------------------------------------------------------------
def history_to_dataframe(history: list[dict]) -> pd.DataFrame:
    rows = []
    for item in history:
        rows.append({
            "step": item.get("step"),
            "timestamp": item.get("timestamp"),
            "operation": item.get("operation"),
            "columns": ", ".join(item.get("columns", [])),
            "parameters": json.dumps(item.get("params", {}), ensure_ascii=False, default=str),
            "rows_before": item.get("rows_before"),
            "rows_after": item.get("rows_after"),
            "rows_affected": item.get("rows_affected"),
            "cells_changed": item.get("cells_changed"),
            "missing_before": item.get("missing_before"),
            "missing_after": item.get("missing_after"),
            "status": item.get("status"),
            "notes": " | ".join(item.get("notes", [])),
        })
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


def history_to_csv_bytes(history: list[dict]) -> bytes:
    return history_to_dataframe(history).to_csv(index=False).encode("utf-8-sig")


def history_to_json_bytes(history: list[dict]) -> bytes:
    return json.dumps(history, indent=2, ensure_ascii=False, default=str).encode("utf-8")


def build_comparison(original: pd.DataFrame, current: pd.DataFrame, original_score: dict, current_score: dict) -> pd.DataFrame:
    """Before / after table used in the app and in the report."""
    a, b = overall_profile(original), overall_profile(current)

    def score(s, key=None):
        if key is None:
            return s.get("overall")
        return s.get("categories", {}).get(key, {}).get("score")

    rows = [
        ("Rows", a["rows"], b["rows"]),
        ("Columns", a["columns"], b["columns"]),
        ("Missing or blank cells", a["missing_cells"], b["missing_cells"]),
        ("Duplicate rows", a["duplicate_rows"], b["duplicate_rows"]),
        ("Quality score (0-100)", score(original_score), score(current_score)),
        ("Completeness", score(original_score, "completeness"), score(current_score, "completeness")),
        ("Validity", score(original_score, "validity"), score(current_score, "validity")),
        ("Uniqueness", score(original_score, "uniqueness"), score(current_score, "uniqueness")),
        ("Consistency", score(original_score, "consistency"), score(current_score, "consistency")),
    ]
    table = pd.DataFrame(rows, columns=["metric", "before", "after"])
    table["change"] = [
        (None if (x is None or y is None) else round(float(y) - float(x), 1)) for x, y in zip(table["before"], table["after"])
    ]
    return table


# --------------------------------------------------------------------------
# Excel reports
# --------------------------------------------------------------------------
def validation_report_excel_bytes(result: ValidationResult, rules: list[dict], dataset_name: str) -> bytes:
    overview = pd.DataFrame({
        "item": ["Project", "Dataset", "Generated", "Total records", "Valid records", "Invalid records",
                 "Validation percentage (records passing all rules)", "Checks performed", "Checks failed"],
        "value": [APP_NAME, dataset_name, now_str(), result.total_rows, result.valid_rows, result.invalid_rows,
                  "" if result.validity_pct is None else f"{result.validity_pct}%", result.cells_checked, result.cells_failed],
    })
    rules_table = pd.DataFrame({"rule": [describe_rule(r) for r in rules]}) if rules else pd.DataFrame({"rule": []})
    sheets = {
        "Overview": overview,
        "Rules": rules_table,
        "Rule summary": result.summary,
        "Row-level issues": result.issues,
    }
    if result.schema_issues:
        sheets["Schema issues"] = pd.DataFrame({"issue": result.schema_issues})
    return dataframes_to_excel_bytes(sheets)


def quality_report_excel_bytes(dataset_name: str, original_score: dict, current_score: dict, comparison: pd.DataFrame,
                               profile_table: pd.DataFrame, history: list[dict]) -> bytes:
    def score_table(s):
        rows = [{"category": "Overall", "score": s.get("overall"), "weight": "", "explanation": s.get("grade", "")}]
        for cat in s.get("categories", {}).values():
            rows.append({"category": cat["label"], "score": cat["score"], "weight": f"{int(cat['weight'] * 100)}%", "explanation": cat["explanation"]})
        return pd.DataFrame(rows)

    info = pd.DataFrame({"item": ["Project", "Dataset", "Generated"], "value": [APP_NAME, dataset_name, now_str()]})
    return dataframes_to_excel_bytes({
        "Report info": info,
        "Score - original": score_table(original_score),
        "Score - current": score_table(current_score),
        "Before vs after": comparison,
        "Column profile": profile_table,
        "Cleaning history": history_to_dataframe(history),
    })


# --------------------------------------------------------------------------
# HTML report
# --------------------------------------------------------------------------
_CSS = """
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--blue:#2563eb;--purple:#7c3aed;--bg:#f8fafc;--good:#16a34a;--warn:#d97706;--bad:#dc2626}
*{box-sizing:border-box}body{font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--ink);margin:0;background:#fff;line-height:1.5}
.page{max-width:980px;margin:0 auto;padding:32px 28px}
.cover{background:linear-gradient(135deg,#0f172a 0%,#312e81 60%,#7c3aed 100%);color:#fff;border-radius:16px;padding:36px 40px;margin-bottom:28px}
.logo-card{display:inline-block;background:#fff;border-radius:12px;padding:10px 14px;margin-bottom:22px}
.logo-card img{display:block;height:auto;width:260px;max-width:100%}
.cover h1{margin:0 0 4px;font-size:34px;letter-spacing:.5px}.cover h2{margin:0 0 6px;font-weight:500;font-size:18px;opacity:.9}
.cover p{margin:2px 0;opacity:.85}.meta{margin-top:18px;font-size:13px;opacity:.85}
h3{font-size:20px;margin:30px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{border:1px solid var(--line);border-radius:12px;padding:14px;background:var(--bg)}
.card .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}.card .v{font-size:26px;font-weight:700}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eef2ff;color:#1e1b4b}.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}
.good{background:#dcfce7;color:#166534}.warn{background:#fef3c7;color:#92400e}.bad{background:#fee2e2;color:#991b1b}
.note{font-size:12px;color:var(--muted)}pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px;font-size:12px}
@media print{.page{padding:0}.cover{-webkit-print-color-adjust:exact;print-color-adjust:exact}h3{break-after:avoid}table{break-inside:auto}tr{break-inside:avoid}}
@media(max-width:700px){.grid{grid-template-columns:repeat(2,1fr)}}
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _table(headers: list[str], rows: list[list], limit: int | None = None) -> str:
    if not rows:
        return '<p class="note">Nothing to show.</p>'
    shown = rows[:limit] if limit else rows
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in shown)
    extra = f'<p class="note">Showing the first {limit:,} of {len(rows):,} rows.</p>' if limit and len(rows) > limit else ""
    return f"<table><tr>{head}</tr>{body}</table>{extra}"


def _score_cards(score: dict) -> str:
    def card(label, value):
        return f'<div class="card"><div class="k">{_e(label)}</div><div class="v">{_e(value)}</div></div>'
    cards = [card("Overall score", "n/a" if score.get("overall") is None else f"{score['overall']} ({score['grade']})")]
    for cat in score.get("categories", {}).values():
        cards.append(card(cat["label"], "n/a" if cat["score"] is None else cat["score"]))
    return '<div class="grid">' + "".join(cards) + "</div>"


def build_html_report(
    dataset_name: str,
    original: pd.DataFrame,
    current: pd.DataFrame,
    original_score: dict,
    current_score: dict,
    history: list[dict],
    validation: ValidationResult | None = None,
    validation_rules: list[dict] | None = None,
    recommendations: list[dict] | None = None,
    file_size: int | None = None,
    logo_bytes: bytes | None = None,
) -> str:
    """Create the full report as one HTML string."""
    generated = now_str()
    a, b = overall_profile(original), overall_profile(current)
    comparison = build_comparison(original, current, original_score, current_score)
    changed = len([h for h in history if h.get("status") == "applied"]) > 0

    # ---- cover
    if logo_bytes:
        logo_html = '<div class="logo-card"><img alt="DefineInfoTech logo" src="data:image/png;base64,' + base64.b64encode(logo_bytes).decode("ascii") + '"></div>'
    else:
        logo_html = f'<div class="logo-card"><strong>{_e(COMPANY_NAME)}</strong></div>'
    parts = [f"""<div class="cover">{logo_html}
<h1>{_e(APP_NAME)}</h1><h2>{_e(APP_TITLE)} - Data Quality Report</h2><p>{_e(APP_TAGLINE)}</p>
<div class="meta">Dataset: <strong>{_e(dataset_name)}</strong> &nbsp;|&nbsp; Generated: {_e(generated)} &nbsp;|&nbsp; Developer: {_e(DEVELOPER)} &nbsp;|&nbsp; Version {_e(APP_VERSION)}</div></div>"""]

    # ---- final status
    parts.append("<h3>1. Final status</h3>")
    o, c = original_score.get("overall"), current_score.get("overall")
    if c is None:
        status, tone = "No score available (empty dataset)", "warn"
    elif not changed:
        status, tone = f"Analysed only - no cleaning applied. Score {c} ({current_score['grade']})", ("good" if c >= 75 else "warn")
    elif o is not None and c > o:
        status, tone = f"Cleaned - quality score improved from {o} to {c} ({current_score['grade']})", "good"
    elif o is not None and c == o:
        status, tone = f"Cleaned - quality score unchanged at {c} ({current_score['grade']})", "warn"
    else:
        status, tone = f"Cleaned - quality score is now {c} (was {o}). Review the cleaning steps.", "warn"
    parts.append(f'<p><span class="pill {tone}">{_e(status)}</span></p>')

    # ---- dataset size
    parts.append("<h3>2. Dataset size</h3>")
    size_rows = [["Original upload", f"{a['rows']:,}", f"{a['columns']:,}", f"{a['total_cells']:,}"],
                 ["Current (cleaned) data", f"{b['rows']:,}", f"{b['columns']:,}", f"{b['total_cells']:,}"]]
    parts.append(_table(["Version", "Rows", "Columns", "Cells"], size_rows))
    if file_size:
        parts.append(f'<p class="note">Uploaded file size: {_e(format_bytes(file_size))}</p>')

    # ---- original quality
    parts.append("<h3>3. Original data quality summary</h3>")
    parts.append(_score_cards(original_score))
    parts.append(_table(["Category", "Score", "Weight", "What was measured"],
                        [[x["label"], "n/a" if x["score"] is None else x["score"], f"{int(x['weight'] * 100)}%", x["explanation"]] for x in original_score.get("categories", {}).values()]))
    if original_score.get("issues"):
        parts.append(_table(["Category", "Severity", "Issue"], [[i["category"], i["severity"], i["description"]] for i in original_score["issues"]]))

    # ---- cleaning operations
    parts.append("<h3>4. Cleaning operations</h3>")
    if history:
        parts.append(_table(["#", "Time", "Operation", "Columns", "Rows before", "Rows after", "Cells changed", "Missing before", "Missing after", "Status"],
                            [[h.get("step"), h.get("timestamp"), h.get("operation"), ", ".join(h.get("columns", [])[:6]), h.get("rows_before"), h.get("rows_after"),
                              h.get("cells_changed"), h.get("missing_before"), h.get("missing_after"), h.get("status")] for h in history]))
        parts.append('<p class="note">History covers this browser session only.</p>')
    else:
        parts.append('<p class="note">No cleaning operations were applied in this session.</p>')

    # ---- validation
    parts.append("<h3>5. Validation results</h3>")
    if validation is not None and validation.rules_run:
        pct = "n/a" if validation.validity_pct is None else f"{validation.validity_pct}%"
        parts.append(f'<div class="grid"><div class="card"><div class="k">Records</div><div class="v">{validation.total_rows:,}</div></div>'
                     f'<div class="card"><div class="k">Valid records</div><div class="v">{validation.valid_rows:,}</div></div>'
                     f'<div class="card"><div class="k">Invalid records</div><div class="v">{validation.invalid_rows:,}</div></div>'
                     f'<div class="card"><div class="k">Validation %</div><div class="v">{_e(pct)}</div></div></div>')
        if validation_rules:
            parts.append("<p><strong>Rules used:</strong></p><ul>" + "".join(f"<li>{_e(describe_rule(r))}</li>" for r in validation_rules) + "</ul>")
        parts.append(_table(["Rule", "Column", "Checked", "Failed", "Pass %"], validation.summary.values.tolist()))
        if len(validation.issues):
            parts.append("<p><strong>Sample of row-level issues</strong></p>")
            parts.append(_table(["Row", "Column", "Rule", "Value", "Problem"], validation.issues.head(50).values.tolist(), limit=50))
    else:
        parts.append('<p class="note">Validation was not run in this session. The quality score used automatically suggested rules.</p>')

    # ---- score
    parts.append("<h3>6. Data quality score (current data)</h3>")
    parts.append(_score_cards(current_score))
    parts.append(_table(["Category", "Score", "Weight used", "What was measured"],
                        [[x["label"], "n/a" if x["score"] is None else x["score"], f"{int(x.get('effective_weight', 0) * 100)}%", x["explanation"]] for x in current_score.get("categories", {}).values()]))
    parts.append("<details><summary>How the score is calculated</summary><pre>" + _e(SCORE_METHOD_TEXT) + "</pre></details>")

    # ---- before / after
    parts.append("<h3>7. Before and after comparison</h3>")
    parts.append(_table(["Metric", "Before", "After", "Change"], [[r.metric, _fmt(r.before), _fmt(r.after), _fmt(r.change)] for r in comparison.itertuples()]))

    # ---- column profile
    parts.append("<h3>8. Column profile (current data)</h3>")
    prof = profile_dataframe(current)
    parts.append(_table(["Column", "Type", "Missing", "Missing %", "Unique", "Min", "Max", "Mean"],
                        [[r.column, r.data_type, r.missing, r.missing_pct, r.unique_values, _fmt(r.min), _fmt(r.max), _fmt(r.mean)] for r in prof.itertuples()], limit=60))

    # ---- recommendations
    parts.append("<h3>9. Recommendations</h3>")
    tips = list(current_score.get("suggestions", []))
    for rec in (recommendations or []):
        if rec.get("kind") == "advisory":
            tips.append(f"{rec['title']}: {rec['description']}")
    parts.append("<ul>" + "".join(f"<li>{_e(t)}</li>" for t in tips) + "</ul>")

    parts.append(f'<p class="note">Generated by {_e(APP_NAME)} v{_e(APP_VERSION)} on {_e(generated)}. Smart Clean is rule-based automation (no generative AI). '
                 'Do not treat sample data as real business data.</p>')
    return ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_e(APP_NAME)} report - {_e(dataset_name)}</title><style>{_CSS}</style></head><body><div class='page'>"
            + "".join(parts) + "</div></body></html>")


def _fmt(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:,}" if isinstance(value, int) else str(value)
