"""
recommendation_engine.py - rule-based "Smart Clean" (NOT generative AI).

This module looks at a dataset, applies fixed, readable rules and statistics
(Pandas, regular expressions, counting) and proposes cleaning steps. There is
no machine-learning model, no external API and no randomness: the same data
always gives the same recommendations.

Two kinds of recommendations are produced
  * actionable  - safe steps that can be applied automatically
                  (trim spaces, remove exact duplicates, convert a column that
                  is 100% numbers/dates, tidy column names ...)
  * advisory    - things that need a human decision (how to fill missing
                  values, what to do with outliers, invalid emails). These are
                  shown but never applied automatically.

How analyze_dataset() works
  It walks through the detectors in a fixed order on a *simulated copy* of the
  data. After each actionable step is found it is applied to the simulation,
  so later steps see the tidied data (for example duplicates are only counted
  after spaces and capitalisation were normalised). The real dataset is not
  touched until apply_recommendations() is called.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from core import cleaning_engine as ce
from core.data_utils import (
    FALSE_TOKENS,
    TRUE_TOKENS,
    blank_mask,
    count_duplicate_rows,
    is_numeric_column,
    is_text_series,
    looks_like_date,
    parse_numeric_series,
)
from core.validation_engine import suggest_rules, validate

# Columns whose digits must stay text (leading zeros, "+91", PIN codes ...)
_KEEP_AS_TEXT_WORDS = ("phone", "mobile", "contact", "tel", "zip", "postal", "pin", "code", "aadhaar", "ssn", "account")


# --------------------------------------------------------------------------
# Applying a recommendation
# --------------------------------------------------------------------------
def apply_recommendation(df: pd.DataFrame, rec: dict):
    """Run one actionable recommendation. Returns (new_df, info)."""
    op, p = rec["operation"], rec.get("params", {})
    if op == "trim_spaces":
        work, info = ce.trim_spaces(df, p["columns"])
    elif op == "collapse_spaces":
        work, info = ce.collapse_spaces(df, p["columns"])
    elif op == "blank_to_missing":
        work, info = ce.replace_blank_text(df, p["columns"], None)
    elif op == "standardize_categories":
        work, info = ce.standardize_categories(df, p["column"], p["mapping"])
    elif op == "convert_numeric":
        work, info = ce.convert_column_type(df, p["column"], p["target"], on_error="abort", clean_symbols=p.get("clean_symbols", False))
    elif op == "convert_date":
        work, info = ce.convert_column_type(df, p["column"], "date", on_error="abort", dayfirst=p.get("dayfirst", False))
    elif op == "convert_boolean":
        work, info = ce.convert_column_type(df, p["column"], "boolean", on_error="abort")
    elif op == "remove_duplicates":
        work, info = ce.remove_duplicates(df, None, "first")
    elif op == "clean_column_names":
        work, info = ce.clean_column_names(df)
    else:
        raise ValueError(f"Unknown recommendation operation: {op}")
    info["operation"] = f"Smart Clean: {rec['title']}"
    return work, info


def apply_recommendations(df: pd.DataFrame, recs: list[dict]):
    """
    Apply the chosen actionable recommendations in their original order.
    Returns (new_df, [info, ...]). Advisory items are ignored.
    """
    work, infos = df.copy(), []
    for rec in recs:
        if rec.get("kind") != "action":
            continue
        work, info = apply_recommendation(work, rec)
        infos.append(info)
    return work, infos


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------
def _rec(rec_id, title, description, operation, params, columns, cells=0, rows=0, review=False):
    return {
        "id": rec_id, "kind": "action", "title": title, "description": description,
        "operation": operation, "params": params, "columns": [str(c) for c in columns],
        "cells": int(cells), "rows": int(rows),
        # Items that rely on an assumption start unticked so the user decides.
        "default_selected": not review, "needs_review": review,
    }


def _advice(rec_id, title, description, columns, severity="medium"):
    return {
        "id": rec_id, "kind": "advisory", "title": title, "description": description,
        "operation": None, "params": {}, "columns": [str(c) for c in columns],
        "cells": 0, "rows": 0, "default_selected": False, "needs_review": True, "severity": severity,
    }


def analyze_dataset(df: pd.DataFrame, settings: dict | None = None) -> list[dict]:
    """Return an ordered list of recommendations for `df` (the data is not modified)."""
    settings = settings or {}
    recs: list[dict] = []
    if df.shape[0] == 0 or df.shape[1] == 0:
        return recs
    sim = df.copy()
    text_cols = [c for c in sim.columns if is_text_series(sim[c])]

    def step(rec):
        """Apply the recommendation to the simulation and record its real impact."""
        nonlocal sim
        new_sim, info = apply_recommendation(sim, rec)
        if info["status"] == "applied":
            rec["cells"], rec["rows"] = info["cells_changed"], info["rows_affected"]
            sim = new_sim
            recs.append(rec)
            return True
        return False

    # 1. leading / trailing spaces
    cols = [c for c in text_cols if _has_edge_spaces(sim[c])]
    if cols:
        r = _rec("trim", "Trim leading and trailing spaces",
                 f"Text in {len(cols)} column(s) starts or ends with spaces: {_names(cols)}.", "trim_spaces", {"columns": cols}, cols)
        step(r)

    # 2. repeated spaces inside text
    cols = [c for c in text_cols if _has_inner_repeats(sim[c])]
    if cols:
        r = _rec("collapse", "Remove repeated spaces",
                 f"Text in {len(cols)} column(s) contains double spaces: {_names(cols)}.", "collapse_spaces", {"columns": cols}, cols)
        step(r)

    # 3. blank strings -> real missing values
    cols = [c for c in text_cols if _has_blank_text(sim[c])]
    if cols:
        r = _rec("blank", "Turn blank text into missing values",
                 f"Empty or space-only cells in {_names(cols)} will be marked as missing so they are counted and handled consistently.",
                 "blank_to_missing", {"columns": cols}, cols)
        step(r)

    # 4. same category written differently (Chennai / CHENNAI / chennai)
    for col in [c for c in sim.columns if is_text_series(sim[c])]:
        series = sim[col]
        texts = series[series.map(lambda v: isinstance(v, str)).astype(bool)]
        if texts.empty or texts.nunique() > 30 or texts.nunique() / len(texts) > 0.5:
            continue
        mapping = ce.suggest_category_groups(series)
        if mapping:
            examples = ", ".join(f"'{k}' -> '{v}'" for k, v in list(mapping.items())[:3])
            r = _rec(f"cat_{col}", f"Standardize spelling in '{col}'",
                     f"The same value is written in different upper/lower case or spacing (e.g. {examples}). The most frequent spelling is used.",
                     "standardize_categories", {"column": col, "mapping": mapping}, [col])
            step(r)

    # 5. text columns that are really numbers / dates / yes-no
    for col in [c for c in sim.columns if is_text_series(sim[c])]:
        present = sim[col][~blank_mask(sim[col])]
        if present.empty or not present.map(lambda v: isinstance(v, str)).all():
            continue
        lowered = str(col).lower()
        if any(w in lowered for w in _KEEP_AS_TEXT_WORDS):
            continue
        # numbers
        plain = parse_numeric_series(present)
        if plain.notna().all() and not _has_leading_zeros(present):
            target = "integer" if (plain == plain.round()).all() else "float"
            r = _rec(f"num_{col}", f"Convert '{col}' to {target} numbers",
                     f"Every value in '{col}' is a valid number but is stored as text.", "convert_numeric",
                     {"column": col, "target": target, "clean_symbols": False}, [col])
            step(r)
            continue
        symbols = parse_numeric_series(present, clean_symbols=True)
        if symbols.notna().all() and present.str.contains(r"[₹$€£¥,]|(?i:rs\.?|inr)", regex=True).any() and not _has_leading_zeros(present):
            target = "integer" if (symbols == symbols.round()).all() else "float"
            r = _rec(f"numsym_{col}", f"Convert '{col}' to numbers (remove currency signs / commas)",
                     f"Values in '{col}' such as '1,200' or '$45' will be read as numbers.", "convert_numeric",
                     {"column": col, "target": target, "clean_symbols": True}, [col])
            step(r)
            continue
        # yes/no
        tokens = {v.strip().lower() for v in present}
        if len(tokens) >= 2 and tokens <= (TRUE_TOKENS | FALSE_TOKENS) and tokens - {"0", "1"}:
            r = _rec(f"bool_{col}", f"Convert '{col}' to True/False",
                     f"'{col}' only contains yes/no style values.", "convert_boolean", {"column": col}, [col])
            step(r)
            continue
        # dates
        if present.map(looks_like_date).all():
            order = _date_order(present)
            if order == "conflict":
                recs.append(_advice(f"date_{col}", f"Check date order in '{col}'",
                                    "Some dates are day-first and others month-first, so they cannot be converted safely. Review them manually.", [col], "high"))
                continue
            dayfirst = order == "day"
            if order == "unknown":
                description = (f"All values in '{col}' look like dates but the day/month order is ambiguous. "
                               "Month-first (05/06 = 6 May) is assumed. Tick this only if that is right, otherwise use Standardization with day-first.")
            else:
                description = f"All values in '{col}' are dates ({'day-first' if dayfirst else 'month-first'} order detected) and will become real date values."
            r = _rec(f"date_{col}", f"Convert '{col}' to dates", description, "convert_date",
                     {"column": col, "dayfirst": dayfirst}, [col], review=(order == "unknown"))
            step(r)

    # 6. exact duplicate rows (after the tidy-ups above)
    dups = count_duplicate_rows(sim)
    if dups:
        r = _rec("dups", "Remove exact duplicate rows", f"{dups:,} row(s) are identical to an earlier row. The first copy is kept.",
                 "remove_duplicates", {}, [])
        step(r)

    # 7. column names (applied last so earlier steps can still use the old names)
    pairs = ce.preview_column_names(sim.columns)
    changed = [(o, n) for o, n in pairs if o != n]
    if changed:
        examples = ", ".join(f"'{o}' -> '{n}'" for o, n in changed[:3])
        r = _rec("colnames", "Clean column names",
                 f"{len(changed)} column name(s) contain capitals, spaces or special characters (e.g. {examples}).",
                 "clean_column_names", {}, [o for o, _ in changed])
        r["cells"], r["rows"] = 0, 0
        recs.append(r)

    # ---- advisory items (never applied automatically)
    recs.extend(_advisories(sim, settings))
    return recs


def _advisories(sim: pd.DataFrame, settings: dict) -> list[dict]:
    advice: list[dict] = []
    missing = ce.missing_summary(sim, settings.get("treat_blank_as_missing", True))
    if not missing.empty:
        parts = []
        for r in missing.itertuples():
            how = "median or mean" if is_numeric_column(sim[r.column]) else "most frequent value or a custom label"
            parts.append(f"'{r.column}': {r.missing:,} missing ({how})")
        advice.append(_advice("missing", "Decide how to handle missing values",
                              "Missing values need a decision from you. Suggested options: " + "; ".join(parts[:6]) + ". Use the Missing values tab.",
                              list(missing["column"]), "high" if missing["missing_pct"].max() > 20 else "medium"))
    outliers = ce.outlier_report(sim, method="iqr", parameter=settings.get("iqr_multiplier", 1.5))
    outliers = outliers[outliers["outliers"] > 0]
    if not outliers.empty:
        parts = [f"'{r.column}': {r.outliers} value(s)" for r in outliers.itertuples()]
        advice.append(_advice("outliers", "Review possible outliers",
                              "Unusual numbers were found (IQR rule): " + "; ".join(parts[:6]) + ". They may be errors or genuine extremes, so review them on the Outliers tab before removing or capping.",
                              list(outliers["column"]), "medium"))
    rules = suggest_rules(sim, settings.get("phone_min_digits", 7), settings.get("phone_max_digits", 15))
    rules = [r for r in rules if r["rule"] in ("email", "phone", "numeric", "date", "range")]
    if rules:
        result = validate(sim, rules)
        if result.cells_failed:
            top = result.summary[result.summary["failed"] > 0].sort_values("failed", ascending=False).head(4)
            where = "; ".join(f"'{r.column}' ({r.rule}): {r.failed}" for r in top.itertuples())
            advice.append(_advice("invalid", "Review invalid values",
                                  f"{result.cells_failed:,} value(s) failed automatic checks - {where}. Open the Validation page to see each row.",
                                  list(top["column"]), "high"))
    return advice


# --------------------------------------------------------------------------
# Tiny detectors
# --------------------------------------------------------------------------
def _strings(series: pd.Series) -> pd.Series:
    return series[series.map(lambda v: isinstance(v, str)).astype(bool)]


def _has_edge_spaces(series) -> bool:
    s = _strings(series)
    return bool((s != s.str.strip()).any()) if not s.empty else False


def _has_inner_repeats(series) -> bool:
    s = _strings(series)
    return bool(s.str.contains(r"[ \t ]{2,}", regex=True).any()) if not s.empty else False


def _has_blank_text(series) -> bool:
    s = _strings(series)
    return bool((s.str.strip() == "").any()) if not s.empty else False


def _has_leading_zeros(present: pd.Series) -> bool:
    return bool(present.astype(str).str.strip().str.match(r"^[+-]?0\d").any())


def _names(cols, limit: int = 5) -> str:
    shown = ", ".join(f"'{c}'" for c in cols[:limit])
    return shown + (f" and {len(cols) - limit} more" if len(cols) > limit else "")


def _date_order(present: pd.Series) -> str:
    """'day' (day first), 'month', 'conflict' or 'unknown' for slash/dash dates."""
    first_big = second_big = False
    for value in present.astype(str):
        m = re.match(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}", value)
        if m:
            first_big |= int(m.group(1)) > 12
            second_big |= int(m.group(2)) > 12
    if first_big and second_big:
        return "conflict"
    if first_big:
        return "day"
    if second_big:
        return "month"
    return "unknown"
