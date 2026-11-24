"""
validation_engine.py - checks data against rules and reports every problem.

How it works
  * A rule is a small dictionary:
        {"rule": "email", "columns": ["email"], "params": {}}
  * validate(df, rules) runs every rule on the real data and returns a
    ValidationResult: counts, a per-rule summary and a row-by-row issue list.
  * Format rules (email, phone, numeric, date, range, text length, allowed
    values, regex) ignore EMPTY cells - use the "not_missing" rule to demand
    a value. This keeps each rule responsible for exactly one thing.
  * Validation never changes the data. It only reports.

No eval(), no uploaded code is ever run. The only user-supplied "program" is
an optional regular expression (custom rule), which is matched as text.

Limitations (shown in the app too)
  * Phone numbers and dates are written very differently around the world.
    The phone rule checks the digit count (default 7-15, the international
    maximum) and allowed characters; it cannot know whether a number really
    exists. Tighten it with your own digit range or a regex rule.
  * Dates are parsed with a day-first / month-first choice. Text such as
    05/06/2024 is genuinely ambiguous, so choose the order that fits your data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.data_utils import (
    DATE_LIKE_REGEX,
    EMAIL_REGEX,
    blank_mask,
    is_numeric_column,
    is_text_series,
    looks_like_date,
    parse_dates_flexible,
    parse_numeric_series,
    row_numbers,
    value_to_text,
)

MAX_ISSUES_STORED = 20000
MAX_REGEX_LENGTH = 200
PHONE_CHARS = re.compile(r"^\+?[\d\s\-().]+$")

# What the UI needs to build a form for each rule.
# params: name, label, type (int|float|text|bool|list), default
RULE_CATALOG: dict[str, dict] = {
    "not_missing": {
        "label": "Required value (not missing)", "columns": "multi", "params": [],
        "description": "The cell must not be empty, blank or missing.",
    },
    "email": {
        "label": "Email address", "columns": "multi", "params": [],
        "description": "Must look like name@domain.tld (letters, digits, . _ % + - before the @).",
    },
    "phone": {
        "label": "Phone number", "columns": "multi",
        "params": [
            {"name": "min_digits", "label": "Minimum digits", "type": "int", "default": 7},
            {"name": "max_digits", "label": "Maximum digits", "type": "int", "default": 15},
        ],
        "description": "Only digits, spaces and + - ( ) . are allowed, and the digit count must be in range.",
    },
    "numeric": {
        "label": "Numeric value", "columns": "multi", "params": [],
        "description": "The value must be a plain number (no letters or symbols).",
    },
    "date": {
        "label": "Date value", "columns": "multi",
        "params": [
            {"name": "date_format", "label": "Exact format (optional, e.g. %d/%m/%Y)", "type": "text", "default": ""},
            {"name": "dayfirst", "label": "Day comes before month (e.g. 05/06 = 5 June)", "type": "bool", "default": False},
        ],
        "description": "The value must be a real calendar date (31/04/2024 is rejected).",
    },
    "duplicates": {
        "label": "No duplicate records", "columns": "multi_optional", "params": [],
        "description": "Flags rows that repeat an earlier row. Leave the columns empty to compare whole rows.",
    },
    "range": {
        "label": "Minimum / maximum value", "columns": "multi",
        "params": [
            {"name": "min", "label": "Minimum (optional)", "type": "float", "default": None},
            {"name": "max", "label": "Maximum (optional)", "type": "float", "default": None},
        ],
        "description": "Numbers must lie between the minimum and maximum.",
    },
    "text_length": {
        "label": "Text length", "columns": "multi",
        "params": [
            {"name": "min_length", "label": "Minimum length", "type": "int", "default": 0},
            {"name": "max_length", "label": "Maximum length", "type": "int", "default": 255},
        ],
        "description": "Number of characters (after trimming spaces) must be in range.",
    },
    "allowed_values": {
        "label": "Allowed values", "columns": "multi",
        "params": [
            {"name": "values", "label": "Allowed values (comma separated)", "type": "list", "default": ""},
            {"name": "case_sensitive", "label": "Case sensitive", "type": "bool", "default": False},
        ],
        "description": "The value must be one of the listed values.",
    },
    "regex": {
        "label": "Custom pattern (regular expression)", "columns": "multi",
        "params": [{"name": "pattern", "label": "Pattern the whole value must match", "type": "text", "default": ""}],
        "description": "Custom column validation, e.g. ^[A-Z]{3}-\\d{4}$ for codes like ABC-1234.",
    },
    "required_columns": {
        "label": "Required columns exist", "columns": "multi", "params": [],
        "description": "Checks that the chosen columns are present in the dataset.",
    },
}


@dataclass
class ValidationResult:
    total_rows: int = 0
    rules_run: int = 0
    invalid_rows: int = 0
    valid_rows: int = 0
    validity_pct: float | None = None
    cells_checked: int = 0
    cells_failed: int = 0
    issues: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["row", "column", "rule", "value", "error"]))
    summary: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["rule", "column", "checked", "failed", "passed_pct"]))
    schema_issues: list = field(default_factory=list)
    truncated: bool = False
    notes: list = field(default_factory=list)

    @property
    def cell_validity_pct(self) -> float | None:
        if not self.cells_checked:
            return None
        return round(100 * (self.cells_checked - self.cells_failed) / self.cells_checked, 2)


# --------------------------------------------------------------------------
# Rule helpers
# --------------------------------------------------------------------------
def make_rule(rule: str, columns, **params) -> dict:
    """Convenience builder:  make_rule('range', ['age'], min=0, max=120)."""
    if rule not in RULE_CATALOG:
        raise ValueError(f"Unknown rule: {rule}")
    if isinstance(columns, str):
        columns = [columns]
    return {"rule": rule, "columns": list(columns or []), "params": params}


def describe_rule(rule: dict) -> str:
    """Human-readable one-liner for a rule."""
    label = RULE_CATALOG.get(rule["rule"], {}).get("label", rule["rule"])
    cols = ", ".join(rule.get("columns") or []) or "all columns"
    extras = {k: v for k, v in (rule.get("params") or {}).items() if v not in (None, "", [])}
    extra_text = f" [{', '.join(f'{k}={v}' for k, v in extras.items())}]" if extras else ""
    return f"{label} on {cols}{extra_text}"


def _present(series: pd.Series) -> pd.Series:
    return ~blank_mask(series)


def _text_of(series: pd.Series) -> pd.Series:
    """Cells as stripped text (missing cells become empty text)."""
    return series.map(lambda v: "" if (v is None or (not isinstance(v, str) and pd.isna(v))) else value_to_text(v).strip())


# --------------------------------------------------------------------------
# One checker per rule. Each returns (checked_mask, failed_mask, errors)
# where `errors` is a message string or a Series of messages.
# --------------------------------------------------------------------------
def _check_not_missing(series, params, df):
    checked = pd.Series(True, index=series.index)
    return checked, blank_mask(series), "Value is missing or blank"


def _check_email(series, params, df):
    checked = _present(series)
    text = _text_of(series)
    ok = text.map(lambda t: bool(EMAIL_REGEX.match(t)) and ".." not in t)
    return checked, checked & ~ok, "Not a valid email address"


def _check_phone(series, params, df):
    checked = _present(series)
    lo, hi = int(params.get("min_digits", 7)), int(params.get("max_digits", 15))
    text = _text_of(series)

    def valid(t: str) -> bool:
        if not PHONE_CHARS.match(t):
            return False
        if "+" in t[1:]:
            return False
        digits = sum(ch.isdigit() for ch in t)
        return lo <= digits <= hi

    ok = text.map(valid)
    return checked, checked & ~ok, f"Phone number must have {lo}-{hi} digits and only digits, spaces, + - ( ) ."


def _check_numeric(series, params, df):
    checked = _present(series)
    ok = parse_numeric_series(series).notna()
    return checked, checked & ~ok, "Not a valid number"


def _check_date(series, params, df):
    checked = _present(series)
    fmt = (params.get("date_format") or "").strip() or None
    parsed = parse_dates_flexible(series, dayfirst=bool(params.get("dayfirst", False)), date_format=fmt)
    ok = parsed.notna()
    if fmt is None and not pd.api.types.is_datetime64_any_dtype(series):
        ok = ok & series.map(looks_like_date).astype(bool)
    message = f"Not a valid date (expected format {fmt})" if fmt else "Not a recognised calendar date"
    return checked, checked & ~ok, message


def _check_range(series, params, df):
    checked = _present(series)
    numbers = parse_numeric_series(series)
    lo, hi = params.get("min"), params.get("max")
    not_number = checked & numbers.isna()
    low_bad = (numbers < lo) if lo is not None else pd.Series(False, index=series.index)
    high_bad = (numbers > hi) if hi is not None else pd.Series(False, index=series.index)
    low_bad, high_bad = low_bad.fillna(False).astype(bool), high_bad.fillna(False).astype(bool)
    failed = not_number | low_bad | high_bad
    messages = pd.Series("", index=series.index, dtype=object)
    messages[not_number] = "Not a number"
    messages[low_bad] = f"Below the minimum of {lo}"
    messages[high_bad] = f"Above the maximum of {hi}"
    return checked, failed & checked, messages


def _check_text_length(series, params, df):
    checked = _present(series)
    lo, hi = int(params.get("min_length", 0)), int(params.get("max_length", 255))
    lengths = _text_of(series).str.len()
    failed = checked & ((lengths < lo) | (lengths > hi))
    return checked, failed, f"Text length must be between {lo} and {hi} characters"


def _check_allowed(series, params, df):
    checked = _present(series)
    raw = params.get("values", [])
    allowed = [a.strip() for a in (raw.split(",") if isinstance(raw, str) else raw) if str(a).strip()]
    case_sensitive = bool(params.get("case_sensitive", False))
    pool = set(allowed if case_sensitive else [a.lower() for a in allowed])
    text = _text_of(series)
    ok = text.map(lambda t: (t if case_sensitive else t.lower()) in pool)
    return checked, checked & ~ok, "Not one of the allowed values"


def _check_regex(series, params, df):
    checked = _present(series)
    pattern = params.get("pattern", "")
    if not pattern or len(pattern) > MAX_REGEX_LENGTH:
        raise ValueError(f"Pattern must be 1-{MAX_REGEX_LENGTH} characters long.")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"The pattern is not a valid regular expression: {exc}") from None
    ok = _text_of(series).map(lambda t: bool(compiled.fullmatch(t)))
    return checked, checked & ~ok, f"Does not match the pattern {pattern}"


CHECKERS = {
    "not_missing": _check_not_missing,
    "email": _check_email,
    "phone": _check_phone,
    "numeric": _check_numeric,
    "date": _check_date,
    "range": _check_range,
    "text_length": _check_text_length,
    "allowed_values": _check_allowed,
    "regex": _check_regex,
}


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def validate(df: pd.DataFrame, rules: list[dict]) -> ValidationResult:
    """Run all rules on `df` and collect the results. Never modifies `df`."""
    result = ValidationResult(total_rows=int(len(df)))
    if not rules:
        result.notes.append("No validation rules were selected.")
        return result
    if df.shape[0] == 0 or df.shape[1] == 0:
        result.notes.append("The dataset has no rows or no columns, so nothing could be validated.")
        return result

    labels = row_numbers(df)
    issue_frames: list[pd.DataFrame] = []
    summary_rows: list[dict] = []
    row_failed = pd.Series(False, index=df.index)

    for rule in rules:
        key = rule.get("rule")
        columns = list(rule.get("columns") or [])
        params = rule.get("params") or {}
        if key not in RULE_CATALOG:
            result.notes.append(f"Unknown rule '{key}' was skipped.")
            continue
        result.rules_run += 1
        title = RULE_CATALOG[key]["label"]

        # ---- dataset-level rule
        if key == "required_columns":
            missing_cols = [c for c in columns if c not in df.columns]
            for c in missing_cols:
                result.schema_issues.append(f"Required column '{c}' is missing from the dataset.")
            summary_rows.append({"rule": title, "column": ", ".join(columns), "checked": len(columns),
                                 "failed": len(missing_cols), "passed_pct": _pass_pct(len(columns), len(missing_cols))})
            continue

        # ---- duplicates (works on a set of columns)
        if key == "duplicates":
            use = [c for c in columns if c in df.columns]
            unknown = [c for c in columns if c not in df.columns]
            for c in unknown:
                result.notes.append(f"Duplicate check skipped unknown column '{c}'.")
            dup = df.duplicated(subset=use or None, keep="first")
            checked_n, failed_n = int(len(df)), int(dup.sum())
            scope = ", ".join(use) if use else "all columns"
            summary_rows.append({"rule": title, "column": scope, "checked": checked_n, "failed": failed_n,
                                 "passed_pct": _pass_pct(checked_n, failed_n)})
            result.cells_checked += checked_n
            result.cells_failed += failed_n
            row_failed |= dup
            if failed_n:
                issue_frames.append(pd.DataFrame({
                    "row": labels[dup].to_numpy(), "column": scope, "rule": title,
                    "value": "(duplicate row)", "error": f"Repeats an earlier row (compared on: {scope})",
                }))
            continue

        # ---- column-level rules
        if not columns:
            result.notes.append(f"Rule '{title}' has no columns selected and was skipped.")
            continue
        for col in columns:
            if col not in df.columns:
                result.notes.append(f"Rule '{title}': column '{col}' was not found and was skipped.")
                continue
            series = df[col]
            try:
                checked, failed, errors = CHECKERS[key](series, params, df)
            except ValueError as exc:
                result.notes.append(f"Rule '{title}' on '{col}' could not run: {exc}")
                continue
            checked = checked.astype(bool)
            failed = failed.fillna(False).astype(bool) & checked
            checked_n, failed_n = int(checked.sum()), int(failed.sum())
            summary_rows.append({"rule": title, "column": col, "checked": checked_n, "failed": failed_n,
                                 "passed_pct": _pass_pct(checked_n, failed_n)})
            result.cells_checked += checked_n
            result.cells_failed += failed_n
            row_failed |= failed
            if failed_n:
                message = errors[failed] if isinstance(errors, pd.Series) else errors
                issue_frames.append(pd.DataFrame({
                    "row": labels[failed].to_numpy(), "column": col, "rule": title,
                    "value": series[failed].map(lambda v: "" if pd.isna(v) else str(v)).to_numpy(),
                    "error": message.to_numpy() if isinstance(message, pd.Series) else message,
                }))

    result.summary = pd.DataFrame(summary_rows, columns=["rule", "column", "checked", "failed", "passed_pct"])
    if issue_frames:
        issues = pd.concat(issue_frames, ignore_index=True).sort_values(["row", "column"], kind="stable").reset_index(drop=True)
        if len(issues) > MAX_ISSUES_STORED:
            issues = issues.head(MAX_ISSUES_STORED)
            result.truncated = True
            result.notes.append(f"Only the first {MAX_ISSUES_STORED:,} issues are listed (counts above are complete).")
        result.issues = issues
    result.invalid_rows = int(row_failed.sum())
    result.valid_rows = result.total_rows - result.invalid_rows
    result.validity_pct = round(100 * result.valid_rows / result.total_rows, 2) if result.total_rows else None
    return result


def _pass_pct(checked: int, failed: int) -> float:
    return round(100 * (checked - failed) / checked, 2) if checked else 100.0


# --------------------------------------------------------------------------
# Automatic rule suggestions (used when the user has not chosen any rules)
# --------------------------------------------------------------------------
_NON_NEGATIVE_WORDS = ("qty", "quantity", "price", "amount", "salary", "stock", "units", "cost", "total", "revenue", "age")


def suggest_rules(df: pd.DataFrame, phone_min: int = 7, phone_max: int = 15) -> list[dict]:
    """
    Suggest sensible rules from column names and contents. Used by the
    one-click "suggest rules" button and by the data quality score when the
    user has not defined rules of their own. Suggestions are heuristics and
    are always shown to the user.
    """
    rules: list[dict] = []
    for col in df.columns:
        name = str(col).lower()
        series = df[col]
        present = series[_present(series)]
        if present.empty:
            continue
        if "email" in name or "e-mail" in name or "e_mail" in name:
            rules.append(make_rule("email", [col]))
            continue
        if any(w in name for w in ("phone", "mobile", "contact_no", "telephone", "tel_", "cell")):
            rules.append(make_rule("phone", [col], min_digits=phone_min, max_digits=phone_max))
            continue
        if is_text_series(series):
            sample = present.head(500)
            numeric_share = parse_numeric_series(sample).notna().mean()
            date_share = sample.map(looks_like_date).mean()
            if date_share >= 0.6:
                rules.append(make_rule("date", [col], date_format="", dayfirst=_guess_dayfirst(sample)))
            elif numeric_share >= 0.6 and not any(w in name for w in ("id", "code", "zip", "pin", "postal")):
                rules.append(make_rule("numeric", [col]))
                if any(w in name for w in _NON_NEGATIVE_WORDS):
                    rules.append(make_rule("range", [col], min=0))
        elif is_numeric_column(series):
            if any(w in name for w in _NON_NEGATIVE_WORDS):
                params = {"min": 0}
                if name in ("age",) or name.endswith("_age") or name.startswith("age_"):
                    params["max"] = 120
                rules.append(make_rule("range", [col], **params))
    return rules


def _guess_dayfirst(sample: pd.Series) -> bool:
    """If any slash/dash date has a first number above 12 it must be the day."""
    first_big, second_big = False, False
    for value in sample.astype(str):
        m = re.match(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}", value)
        if m:
            first_big |= int(m.group(1)) > 12
            second_big |= int(m.group(2)) > 12
    return first_big and not second_big
