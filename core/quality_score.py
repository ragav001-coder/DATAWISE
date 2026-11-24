"""
quality_score.py - the transparent DATAWISE Data Quality Score (0 to 100).

HOW THE SCORE IS CALCULATED
---------------------------
Four categories are scored from 0 to 100. Higher is better.

 1. Completeness  = 100 x (1 - blank_cells / total_cells)
      A cell is blank if it is missing (NaN/None) or contains only spaces.

 2. Uniqueness    = 100 x (1 - duplicate_rows / total_rows)
      A duplicate row is a row identical to an EARLIER row (first copy is fine).

 3. Validity      = 100 x (1 - failed_checks / checks_performed)
      Checks come from validation rules (email format, phone format, numeric,
      date, minimum/maximum ...). If the user selected rules, those are used.
      Otherwise rules are suggested automatically from column names/contents
      (e.g. a column called "email" gets an email check). Empty cells are not
      counted here - they are already penalised in Completeness.
      If no rule applies to the data, Validity is "not applicable" and is left
      out of the overall score (the other weights are scaled up to 100%).

 4. Consistency   = 100 x (1 - inconsistent_cells / text_cells_examined)
      In text columns we look for: extra / repeated spaces, the same value
      written in different upper/lower case, numbers mixed with words in a
      mostly-numeric column, and dates written in more than one format.
      If the data has no text columns it is "not applicable".

OVERALL SCORE = weighted average of the applicable categories:
      Completeness 30%, Validity 30%, Uniqueness 20%, Consistency 20%
(Weights are re-scaled when a category is not applicable.)

Grades: 90-100 Excellent, 75-89 Good, 50-74 Fair, below 50 Poor.

An empty dataset (0 rows or 0 columns) has no score (None).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from core.cleaning_engine import suggest_category_groups
from core.data_utils import (
    blank_mask,
    count_blank_cells,
    count_duplicate_rows,
    date_shape,
    is_text_series,
    looks_like_date,
    parse_numeric_series,
)
from core.validation_engine import suggest_rules, validate

WEIGHTS = {"completeness": 0.30, "validity": 0.30, "uniqueness": 0.20, "consistency": 0.20}
CATEGORY_LABELS = {
    "completeness": "Completeness",
    "validity": "Validity",
    "uniqueness": "Uniqueness",
    "consistency": "Consistency",
}

SCORE_METHOD_TEXT = __doc__.split("HOW THE SCORE IS CALCULATED")[1].strip() if __doc__ else ""


def grade_for(score: float | None) -> str:
    if score is None:
        return "No data"
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


# --------------------------------------------------------------------------
# Consistency detection
# --------------------------------------------------------------------------
def consistency_issues(df: pd.DataFrame) -> tuple[list[dict], int, int]:
    """
    Look for formatting inconsistencies in text columns.
    Returns (issues, inconsistent_cell_count, examined_cell_count).
    A cell that has several problems is only counted once.
    """
    issues: list[dict] = []
    bad_total = examined_total = 0

    for col in df.columns:
        series = df[col]
        if not is_text_series(series):
            continue
        is_str = series.map(lambda v: isinstance(v, str)).astype(bool)
        texts = series[is_str]
        texts = texts[texts.str.strip() != ""]
        if texts.empty:
            continue
        examined_total += len(texts)
        bad = pd.Series(False, index=texts.index)

        # a) extra spaces
        spaces = texts.map(lambda s: s != s.strip() or bool(re.search(r"\s{2,}", s)))
        if spaces.any():
            issues.append({"column": col, "issue": "Extra or repeated spaces", "cells": int(spaces.sum())})
            bad |= spaces

        # b) same value in different case / spacing (only for category-like columns)
        unique_n = texts.nunique()
        if unique_n <= 50 or unique_n / len(texts) <= 0.5:
            mapping = suggest_category_groups(texts)
            if mapping:
                variant = texts.map(lambda s: s in mapping)
                issues.append({"column": col, "issue": "Same value written in different case/spacing", "cells": int(variant.sum())})
                bad |= variant

        # c) numbers mixed with words in a mostly numeric column
        stripped = texts.str.strip()
        numeric_ok = parse_numeric_series(stripped).notna()
        share = float(numeric_ok.mean())
        if 0.8 <= share < 1.0:
            not_numeric = ~numeric_ok
            issues.append({"column": col, "issue": "Non-numeric text in a mostly numeric column", "cells": int(not_numeric.sum())})
            bad |= not_numeric

        # d) dates written in several formats
        date_like = stripped.map(looks_like_date)
        date_share = float(date_like.mean())
        if date_share >= 0.8:
            shapes = stripped[date_like].map(date_shape)
            if shapes.nunique() > 1:
                dominant = shapes.value_counts().idxmax()
                other = pd.Series(False, index=texts.index)
                other[shapes.index] = shapes != dominant
                issues.append({"column": col, "issue": "Dates written in more than one format", "cells": int(other.sum())})
                bad |= other
            if date_share < 1.0:
                not_date = ~date_like
                issues.append({"column": col, "issue": "Non-date text in a date column", "cells": int(not_date.sum())})
                bad |= not_date

        bad_total += int(bad.sum())

    return issues, bad_total, examined_total


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def compute_quality_score(df: pd.DataFrame, rules: list[dict] | None = None, phone_range: tuple[int, int] = (7, 15)) -> dict:
    """
    Calculate the quality score for a DataFrame.

    rules=None  -> validity uses automatically suggested rules.
    rules=[...] -> validity uses exactly these rules (an empty list means none).
    """
    rows, cols = int(df.shape[0]), int(df.shape[1])
    result: dict = {
        "overall": None, "grade": grade_for(None), "rows": rows, "columns": cols,
        "categories": {}, "issues": [], "suggestions": [], "notes": [],
        "validity_rules_source": "none", "weights": dict(WEIGHTS),
    }
    if rows == 0 or cols == 0:
        result["notes"].append("The dataset has no rows or no columns, so no score can be calculated.")
        for key in WEIGHTS:
            result["categories"][key] = _category(key, None, "No data.", {})
        return result

    total_cells = rows * cols

    # ---- completeness
    blank_cells = count_blank_cells(df)
    completeness = 100 * (1 - blank_cells / total_cells)
    per_col = {c: int(blank_mask(df[c]).sum()) for c in df.columns}
    worst = sorted(((c, n) for c, n in per_col.items() if n), key=lambda x: -x[1])
    result["categories"]["completeness"] = _category(
        "completeness", completeness,
        f"{blank_cells:,} of {total_cells:,} cells are missing or blank.",
        {"blank_cells": blank_cells, "total_cells": total_cells, "worst_columns": worst[:5]},
    )
    if blank_cells:
        result["issues"].append({"category": "Completeness", "severity": _severity(blank_cells / total_cells),
                                 "description": f"{blank_cells:,} missing or blank cells (worst: {', '.join(c for c, _ in worst[:3])})", "count": blank_cells})

    # ---- uniqueness
    dups = count_duplicate_rows(df)
    uniqueness = 100 * (1 - dups / rows)
    result["categories"]["uniqueness"] = _category(
        "uniqueness", uniqueness, f"{dups:,} of {rows:,} rows repeat an earlier row.",
        {"duplicate_rows": dups, "total_rows": rows},
    )
    if dups:
        result["issues"].append({"category": "Uniqueness", "severity": _severity(dups / rows),
                                 "description": f"{dups:,} duplicate rows", "count": dups})

    # ---- validity
    if rules is None:
        active = suggest_rules(df, phone_range[0], phone_range[1])
        source = "auto" if active else "none"
    else:
        active, source = list(rules), ("user" if rules else "none")
    result["validity_rules_source"] = source
    # duplicates / required-value rules are measured by other categories
    active = [r for r in active if r["rule"] not in ("duplicates", "not_missing", "required_columns")]
    validation = validate(df, active) if active else None
    if validation is not None and validation.cells_checked > 0:
        validity = 100 * (1 - validation.cells_failed / validation.cells_checked)
        origin = "your validation rules" if source == "user" else "automatically suggested rules"
        result["categories"]["validity"] = _category(
            "validity", validity,
            f"{validation.cells_failed:,} of {validation.cells_checked:,} checks failed using {origin}.",
            {"checks": validation.cells_checked, "failed": validation.cells_failed, "rules": len(active), "source": source},
        )
        if validation.cells_failed:
            top = validation.summary[validation.summary["failed"] > 0].sort_values("failed", ascending=False).head(3)
            where = ", ".join(f"{r.column} ({r.failed})" for r in top.itertuples())
            result["issues"].append({"category": "Validity", "severity": _severity(validation.cells_failed / validation.cells_checked),
                                     "description": f"{validation.cells_failed:,} invalid values: {where}", "count": validation.cells_failed})
    else:
        result["categories"]["validity"] = _category(
            "validity", None,
            "No validation rule applies to this data yet, so validity is not scored. Add rules on the Validation page.", {},
        )

    # ---- consistency
    issues, bad_cells, examined = consistency_issues(df)
    if examined:
        consistency = 100 * (1 - bad_cells / examined)
        result["categories"]["consistency"] = _category(
            "consistency", consistency,
            f"{bad_cells:,} of {examined:,} text cells have formatting inconsistencies.",
            {"inconsistent_cells": bad_cells, "examined_cells": examined, "details": issues},
        )
        for item in sorted(issues, key=lambda i: -i["cells"])[:5]:
            result["issues"].append({"category": "Consistency", "severity": _severity(item["cells"] / examined),
                                     "description": f"{item['issue']} in '{item['column']}' ({item['cells']:,} cells)", "count": item["cells"]})
    else:
        result["categories"]["consistency"] = _category("consistency", None, "The data has no text columns, so consistency is not scored.", {})

    # ---- overall
    applicable = {k: v for k, v in result["categories"].items() if v["score"] is not None}
    weight_sum = sum(WEIGHTS[k] for k in applicable)
    overall = sum(v["score"] * WEIGHTS[k] for k, v in applicable.items()) / weight_sum if weight_sum else None
    result["overall"] = None if overall is None else round(overall, 1)
    result["grade"] = grade_for(result["overall"])
    for key, cat in result["categories"].items():
        cat["effective_weight"] = round(WEIGHTS[key] / weight_sum, 3) if (weight_sum and cat["score"] is not None) else 0.0
    result["suggestions"] = _suggestions(result, worst, dups, issues)
    result["issues"].sort(key=lambda i: {"high": 0, "medium": 1, "low": 2}[i["severity"]])
    return result


def _category(key: str, score: float | None, explanation: str, details: dict) -> dict:
    return {
        "label": CATEGORY_LABELS[key],
        "score": None if score is None else round(float(score), 1),
        "weight": WEIGHTS[key],
        "applicable": score is not None,
        "explanation": explanation,
        "details": details,
        "effective_weight": 0.0,
    }


def _severity(ratio: float) -> str:
    if ratio >= 0.10:
        return "high"
    if ratio >= 0.02:
        return "medium"
    return "low"


def _suggestions(result: dict, worst_cols, dups: int, consistency_list) -> list[str]:
    tips: list[str] = []
    cats = result["categories"]
    if cats["completeness"]["score"] is not None and cats["completeness"]["score"] < 100 and worst_cols:
        names = ", ".join(f"'{c}'" for c, _ in worst_cols[:3])
        tips.append(f"Handle missing values in {names}: fill them (mean/median/mode/custom) or remove the rows on the Cleaning page.")
    if dups:
        tips.append(f"Remove the {dups:,} duplicate rows (Cleaning page > Duplicates).")
    validity = cats.get("validity", {})
    if validity.get("score") is not None and validity["score"] < 100:
        tips.append("Review invalid values on the Validation page, then correct them or replace them with missing values.")
    if validity.get("score") is None:
        tips.append("Add validation rules (email, phone, numeric, date ...) so Validity can be measured.")
    cons = cats.get("consistency", {})
    if cons.get("score") is not None and cons["score"] < 100:
        tips.append("Run Smart Clean to trim spaces, unify upper/lower case and standardise date formats.")
    if not tips:
        tips.append("No issues were found. The data is ready for analysis.")
    return tips
