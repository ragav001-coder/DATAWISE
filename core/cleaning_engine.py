"""
cleaning_engine.py - every data-cleaning operation lives here.

Golden rules of this module
  1. Functions NEVER change the DataFrame you pass in. They work on a copy and
     return  (new_dataframe, info).
  2. `info` is a dictionary that describes what happened (operation name,
     columns, parameters, rows/cells changed, columns that were skipped and
     why, conversion errors). The app stores it in the cleaning history.
  3. Nothing is changed silently: when an operation cannot be applied to a
     column (for example "mean" on a text column) the column is listed in
     info["skipped"] with a reason instead of being damaged.
"""

from __future__ import annotations

import re
from typing import Callable

import numpy as np
import pandas as pd

from core.data_utils import (
    FALSE_TOKENS,
    TRUE_TOKENS,
    blank_mask,
    collapse_spaces_text,
    is_missing_scalar,
    is_numeric_column,
    is_text_series,
    parse_dates_flexible,
    parse_numeric_series,
)

CASE_MODES = ("lower", "upper", "title")
FILL_METHODS = ("mean", "median", "zero", "mode", "custom")
TARGET_TYPES = ("string", "integer", "float", "date", "datetime", "boolean")
MAX_ERRORS_SHOWN = 200


# --------------------------------------------------------------------------
# Small internal helpers
# --------------------------------------------------------------------------
def _make_info(
    operation: str,
    before: pd.DataFrame,
    after: pd.DataFrame,
    columns=None,
    params: dict | None = None,
    cells_changed: int = 0,
    rows_affected: int | None = None,
    skipped: list | None = None,
    errors: list | None = None,
    notes: list | None = None,
    status: str = "applied",
) -> dict:
    if rows_affected is None:
        rows_affected = abs(len(before) - len(after))
    errors = errors or []
    return {
        "operation": operation,
        "columns": [str(c) for c in (columns or [])],
        "params": params or {},
        "rows_before": int(len(before)),
        "rows_after": int(len(after)),
        "rows_affected": int(rows_affected),
        "cells_changed": int(cells_changed),
        "skipped": skipped or [],  # list of {"column": ..., "reason": ...}
        "errors": errors[:MAX_ERRORS_SHOWN],
        "error_count": int(len(errors)),
        "notes": notes or [],
        "status": status,  # applied | nothing_to_do | blocked
    }


def _split_columns(df: pd.DataFrame, columns) -> tuple[list, list]:
    """Return (columns that exist, skipped entries for ones that do not)."""
    if columns is None:
        return list(df.columns), []
    if isinstance(columns, str):
        columns = [columns]
    found, skipped = [], []
    for col in columns:
        if col in df.columns:
            found.append(col)
        else:
            skipped.append({"column": str(col), "reason": "Column not found"})
    return found, skipped


def _finish_cell_op(operation, before, after, columns, params, cells, changed_rows, skipped, notes=None):
    status = "applied" if cells > 0 else "nothing_to_do"
    return _make_info(
        operation,
        before,
        after,
        columns=columns,
        params=params,
        cells_changed=cells,
        rows_affected=int(changed_rows.sum()) if len(changed_rows) else 0,
        skipped=skipped,
        notes=notes,
        status=status,
    )



def _set_cells(series: pd.Series, mask: pd.Series, values) -> pd.Series:
    """
    Return a copy of `series` where the cells selected by the boolean `mask`
    are replaced by `values` (same order as the True positions). Works for both
    object and the newer pandas string dtype.
    """
    full = series.to_numpy(dtype=object, copy=True)
    full[np.asarray(mask, dtype=bool)] = list(values)
    return pd.Series(full, index=series.index, name=series.name, dtype=series.dtype)

# --------------------------------------------------------------------------
# A. Missing values
# --------------------------------------------------------------------------
def missing_mask(series: pd.Series, treat_blank_as_missing: bool = True) -> pd.Series:
    """Missing = NaN/None. Optionally also empty / whitespace-only text."""
    return blank_mask(series) if treat_blank_as_missing else series.isna().astype(bool)


def missing_summary(df: pd.DataFrame, treat_blank_as_missing: bool = True) -> pd.DataFrame:
    """Per-column missing counts (only columns that have missing values)."""
    rows = []
    total = len(df)
    for col in df.columns:
        n = int(missing_mask(df[col], treat_blank_as_missing).sum())
        if n:
            rows.append({"column": col, "missing": n, "missing_pct": round(100 * n / total, 1) if total else 0.0})
    return pd.DataFrame(rows, columns=["column", "missing", "missing_pct"])


def drop_missing_rows(df, columns=None, how="any", treat_blank_as_missing=True):
    """
    Remove rows that have missing values.
    columns=None -> look at all columns. how='any' -> drop if ANY listed
    column is missing; how='all' -> drop only if ALL listed columns are missing.
    """
    work = df.copy()
    cols, skipped = _split_columns(work, columns)
    if not cols:
        return work, _make_info("Remove rows with missing values", df, work, columns, {"how": how}, skipped=skipped, status="nothing_to_do")
    masks = pd.concat([missing_mask(work[c], treat_blank_as_missing) for c in cols], axis=1)
    drop = masks.any(axis=1) if how == "any" else masks.all(axis=1)
    work = work.loc[~drop].copy()
    params = {"how": how, "treat_blank_as_missing": treat_blank_as_missing}
    status = "applied" if int(drop.sum()) else "nothing_to_do"
    return work, _make_info("Remove rows with missing values", df, work, cols, params, skipped=skipped, status=status)


def fill_missing(df, columns, method, custom_value=None, treat_blank_as_missing=True):
    """
    Fill missing values column by column, choosing a method that fits the type.

    method: 'mean' | 'median' | 'zero'  (number columns only)
            'mode'                       (any column - most frequent value)
            'custom'                     (any column - your own value)
    Columns the method cannot be used on are skipped and reported.
    """
    if method not in FILL_METHODS:
        raise ValueError(f"Unknown fill method: {method}")
    work = df.copy()
    cols, skipped = _split_columns(work, columns)
    total_cells = 0
    changed_rows = np.zeros(len(work), dtype=bool)

    for col in cols:
        series = work[col]
        mask = missing_mask(series, treat_blank_as_missing)
        count = int(mask.sum())
        if count == 0:
            continue
        numeric = is_numeric_column(series)

        if method in ("mean", "median", "zero") and not numeric:
            skipped.append({"column": str(col), "reason": f"'{method}' needs a numeric column (this one is text)"})
            continue
        if method == "mean":
            value = series.mean()
        elif method == "median":
            value = series.median()
        elif method == "zero":
            value = 0
        elif method == "mode":
            candidates = series[~mask]
            modes = candidates.mode(dropna=True)
            if modes.empty:
                skipped.append({"column": str(col), "reason": "No values to calculate the most frequent value"})
                continue
            value = modes.iloc[0]
        else:  # custom
            if custom_value is None or (isinstance(custom_value, str) and custom_value == ""):
                skipped.append({"column": str(col), "reason": "No custom value was provided"})
                continue
            value = custom_value
            if numeric:
                try:
                    value = float(custom_value)
                    if ptypes_is_integer(series) and float(value).is_integer():
                        value = int(value)
                except (TypeError, ValueError):
                    skipped.append({"column": str(col), "reason": f"'{custom_value}' is not a number, but this column is numeric"})
                    continue
        if value is None or is_missing_scalar(value):
            skipped.append({"column": str(col), "reason": "The fill value could not be calculated"})
            continue

        if numeric and pd.api.types.is_integer_dtype(series) and method in ("mean", "median") and not float(value).is_integer():
            work[col] = series.astype("float64")
        if numeric and pd.api.types.is_integer_dtype(work[col]) and float(value).is_integer():
            value = int(value)
        work[col] = work[col].where(~mask, value)
        total_cells += count
        changed_rows |= mask.to_numpy()

    params = {"method": method, "custom_value": custom_value, "treat_blank_as_missing": treat_blank_as_missing}
    return work, _finish_cell_op("Fill missing values", df, work, cols, params, total_cells, changed_rows, skipped)


def ptypes_is_integer(series: pd.Series) -> bool:
    return bool(pd.api.types.is_integer_dtype(series))


# --------------------------------------------------------------------------
# B. Duplicates
# --------------------------------------------------------------------------
def count_duplicates(df: pd.DataFrame, subset=None) -> int:
    """How many rows repeat an earlier row (first copy not counted)."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return 0
    cols, _ = _split_columns(df, subset) if subset else (None, [])
    return int(df.duplicated(subset=cols or None, keep="first").sum())


def get_duplicate_rows(df: pd.DataFrame, subset=None) -> pd.DataFrame:
    """Every row that belongs to a duplicate group (including the first copy)."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return df.iloc[0:0]
    cols, _ = _split_columns(df, subset) if subset else (None, [])
    mask = df.duplicated(subset=cols or None, keep=False)
    result = df.loc[mask]
    if cols:
        result = result.sort_values(by=cols, kind="stable")
    else:
        result = result.sort_values(by=list(df.columns), kind="stable")
    return result


def remove_duplicates(df, subset=None, keep="first"):
    """Remove duplicate rows. keep='first' | 'last'. subset=None -> whole row."""
    if keep not in ("first", "last"):
        raise ValueError("keep must be 'first' or 'last'")
    work = df.copy()
    cols, skipped = _split_columns(work, subset) if subset else (None, [])
    if subset and not cols:
        return work, _make_info("Remove duplicate rows", df, work, subset, {"keep": keep}, skipped=skipped, status="nothing_to_do")
    work = work.drop_duplicates(subset=cols or None, keep=keep)
    params = {"keep": keep, "subset": cols or "all columns"}
    status = "applied" if len(work) < len(df) else "nothing_to_do"
    return work, _make_info("Remove duplicate rows", df, work, cols or [], params, skipped=skipped, status=status)


# --------------------------------------------------------------------------
# C. Text cleaning
# --------------------------------------------------------------------------
def _apply_text_op(df, columns, func: Callable[[pd.Series], pd.Series], operation: str, params: dict):
    """
    Run `func` (string Series -> string Series) on the TEXT cells of the chosen
    columns. Numbers, dates and missing cells are left untouched.
    """
    work = df.copy()
    cols, skipped = _split_columns(work, columns)
    total_cells = 0
    changed_rows = np.zeros(len(work), dtype=bool)
    used = []

    for col in cols:
        series = work[col]
        if not is_text_series(series):
            skipped.append({"column": str(col), "reason": "Not a text column"})
            continue
        is_str = series.map(lambda v: isinstance(v, str)).astype(bool)
        if not is_str.any():
            continue
        old_values = series[is_str].to_numpy(dtype=object)
        new_series = func(pd.Series(old_values, dtype="string"))
        new_values = np.array(list(new_series.astype(object)), dtype=object)
        changed = np.array([a != b for a, b in zip(old_values, new_values)], dtype=bool)
        if not changed.any():
            used.append(col)
            continue
        work[col] = _set_cells(series, is_str, new_values)
        total_cells += int(changed.sum())
        positions = np.flatnonzero(is_str.to_numpy())
        changed_rows[positions[changed]] = True
        used.append(col)

    return work, _finish_cell_op(operation, df, work, used or cols, params, total_cells, changed_rows, skipped)


def trim_spaces(df, columns):
    """Remove spaces at the start and end of text cells."""
    return _apply_text_op(df, columns, lambda s: s.str.strip(), "Trim leading/trailing spaces", {})


def collapse_spaces(df, columns):
    """Replace runs of spaces/tabs inside text with a single space."""
    return _apply_text_op(df, columns, lambda s: s.str.replace(r"[ \t ]{2,}", " ", regex=True), "Remove repeated spaces", {})


def change_case(df, columns, mode):
    """Change text case: 'lower', 'upper' or 'title'."""
    if mode not in CASE_MODES:
        raise ValueError(f"mode must be one of {CASE_MODES}")
    funcs = {"lower": lambda s: s.str.lower(), "upper": lambda s: s.str.upper(), "title": lambda s: s.str.title()}
    return _apply_text_op(df, columns, funcs[mode], f"Convert text to {mode} case", {"mode": mode})


def replace_values(df, columns, old_value, new_value, whole_cell=True, case_sensitive=True):
    """
    Replace text. whole_cell=True replaces cells that are exactly `old_value`;
    False replaces `old_value` wherever it appears inside the text.
    """
    if old_value is None or old_value == "":
        raise ValueError("The value to replace cannot be empty. Use 'replace blank text' for blanks.")
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(("^" + re.escape(old_value) + "$") if whole_cell else re.escape(old_value), flags)
    replacement = "" if new_value is None else str(new_value)
    params = {"old": old_value, "new": new_value, "whole_cell": whole_cell, "case_sensitive": case_sensitive}
    return _apply_text_op(df, columns, lambda s: s.str.replace(pattern, lambda m: replacement, regex=True), "Replace text values", params)


def remove_characters(df, columns, characters: str):
    """Delete every occurrence of each character in `characters` (e.g. '#$%')."""
    if not characters:
        raise ValueError("Please enter at least one character to remove.")
    pattern = "[" + re.escape(characters) + "]"
    return _apply_text_op(df, columns, lambda s: s.str.replace(pattern, "", regex=True), "Remove unwanted characters", {"characters": characters})


def replace_blank_text(df, columns, new_value=None):
    """
    Cells that are empty or only spaces become `new_value`.
    new_value=None turns them into real missing values (NaN).
    """
    work = df.copy()
    cols, skipped = _split_columns(work, columns)
    total, changed_rows, used = 0, np.zeros(len(work), dtype=bool), []
    for col in cols:
        series = work[col]
        if not is_text_series(series):
            skipped.append({"column": str(col), "reason": "Not a text column"})
            continue
        mask = series.map(lambda v: isinstance(v, str) and v.strip() == "").astype(bool)
        if not mask.any():
            continue
        fill = np.nan if new_value is None or new_value == "" else new_value
        work[col] = series.where(~mask, fill)
        total += int(mask.sum())
        changed_rows |= mask.to_numpy()
        used.append(col)
    params = {"new_value": "missing (NaN)" if new_value in (None, "") else new_value}
    return work, _finish_cell_op("Replace blank text", df, work, used or cols, params, total, changed_rows, skipped)


def suggest_category_groups(series: pd.Series) -> dict:
    """
    Find values that differ only by upper/lower case or spacing
    ('Chennai', 'CHENNAI', ' chennai ') and propose one standard spelling:
    the variant that appears most often. Returns {old_value: standard_value}.
    """
    values = series[series.map(lambda v: isinstance(v, str)).astype(bool)]
    values = values[values.str.strip() != ""]
    if values.empty:
        return {}
    counts = values.value_counts()
    groups: dict[str, list[str]] = {}
    for value in counts.index:
        groups.setdefault(collapse_spaces_text(value).lower(), []).append(value)
    mapping = {}
    for variants in groups.values():
        if len(variants) < 2:
            continue
        # most frequent variant after trimming spaces is the standard spelling
        tidy_counts: dict[str, int] = {}
        for v in variants:
            tidy = collapse_spaces_text(v)
            tidy_counts[tidy] = tidy_counts.get(tidy, 0) + int(counts[v])
        standard = max(tidy_counts, key=lambda k: (tidy_counts[k], k))
        for v in variants:
            if v != standard:
                mapping[v] = standard
    return mapping


def standardize_categories(df, column, mapping: dict):
    """
    Replace values using a mapping {old: new} (exact match on the cell text).
    Typical use: map 'M', 'male', 'MALE' to 'Male'.
    """
    work = df.copy()
    if column not in work.columns:
        info = _make_info("Standardize categories", df, work, [column], {"mapping": mapping}, skipped=[{"column": str(column), "reason": "Column not found"}], status="nothing_to_do")
        return work, info
    series = work[column]
    if not is_text_series(series):
        info = _make_info("Standardize categories", df, work, [column], {"mapping": mapping}, skipped=[{"column": str(column), "reason": "Not a text column"}], status="nothing_to_do")
        return work, info
    clean_map = {str(k): v for k, v in (mapping or {}).items() if str(k) != str(v)}
    mask = series.map(lambda v: isinstance(v, str) and v in clean_map).astype(bool)
    if mask.any():
        work[column] = _set_cells(series, mask, [clean_map[v] for v in series[mask]])
    info = _finish_cell_op("Standardize categories", df, work, [column], {"mapping": clean_map}, int(mask.sum()), mask.to_numpy(), [])
    return work, info


# --------------------------------------------------------------------------
# D. Column names
# --------------------------------------------------------------------------
def clean_column_name(name, lowercase=True, spaces_to_underscore=True, remove_special=True) -> str:
    text = str(name).strip()
    if lowercase:
        text = text.lower()
    if spaces_to_underscore:
        text = re.sub(r"\s+", "_", text)
    if remove_special:
        text = re.sub(r"[^\w]", "", text)
        text = re.sub(r"_+", "_", text).strip("_")
    return text or "column"


def preview_column_names(columns, lowercase=True, spaces_to_underscore=True, remove_special=True) -> list[tuple[str, str]]:
    """Return [(old_name, new_name)] with duplicates made unique (name_2, name_3...)."""
    result, used = [], set()
    for old in columns:
        base = clean_column_name(old, lowercase, spaces_to_underscore, remove_special)
        new, n = base, 1
        while new in used:
            n += 1
            new = f"{base}_{n}"
        used.add(new)
        result.append((str(old), new))
    return result


def clean_column_names(df, lowercase=True, spaces_to_underscore=True, remove_special=True):
    """Normalise column names. Duplicates created by cleaning get _2, _3 suffixes."""
    work = df.copy()
    pairs = preview_column_names(work.columns, lowercase, spaces_to_underscore, remove_special)
    work.columns = [new for _, new in pairs]
    renamed = {old: new for old, new in pairs if old != new}
    params = {"lowercase": lowercase, "spaces_to_underscore": spaces_to_underscore, "remove_special": remove_special, "renamed": renamed}
    status = "applied" if renamed else "nothing_to_do"
    info = _make_info("Clean column names", df, work, list(renamed), params, cells_changed=0, rows_affected=0, status=status)
    info["columns_renamed"] = len(renamed)
    return work, info


# --------------------------------------------------------------------------
# E. Data type conversion
# --------------------------------------------------------------------------
def convert_column_type(df, column, target, on_error="abort", dayfirst=False, date_format=None, clean_symbols=False):
    """
    Convert one column to string / integer / float / date / datetime / boolean.

    on_error='abort'        -> if ANY value cannot be converted, change nothing
                               and report the offending values (default, safest).
    on_error='set_missing'  -> values that cannot be converted become missing;
                               they are still listed in info["errors"].
    clean_symbols=True lets integer/float conversion read '1,200' or 'Rs 45'.
    """
    if target not in TARGET_TYPES:
        raise ValueError(f"target must be one of {TARGET_TYPES}")
    work = df.copy()
    params = {"target": target, "on_error": on_error, "dayfirst": dayfirst, "date_format": date_format, "clean_symbols": clean_symbols}
    if column not in work.columns:
        info = _make_info("Convert data type", df, work, [column], params, skipped=[{"column": str(column), "reason": "Column not found"}], status="blocked")
        return work, info

    series = work[column]
    present = ~blank_mask(series)
    converted, failed = _convert_series(series, target, dayfirst, date_format, clean_symbols)
    failed = failed & present

    errors = [
        {"row": int(i) + 1 if isinstance(i, (int, np.integer)) else str(i), "value": str(series.loc[i])}
        for i in series.index[failed][:MAX_ERRORS_SHOWN]
    ]
    all_errors = [{"row": 0, "value": ""}] * int(failed.sum())  # for the count only
    if failed.any() and on_error == "abort":
        info = _make_info("Convert data type", df, work, [column], params, rows_affected=0, errors=all_errors, status="blocked",
                          notes=[f"{int(failed.sum())} value(s) cannot be converted to {target}. Nothing was changed."])
        info["errors"] = errors
        info["error_count"] = int(failed.sum())
        return work, info

    old_dtype = str(series.dtype)
    work[column] = converted
    changed = int(present.sum())
    notes = []
    if failed.any():
        notes.append(f"{int(failed.sum())} value(s) could not be converted and were set to missing.")
    info = _make_info("Convert data type", df, work, [column], params, cells_changed=changed,
                      rows_affected=changed, errors=all_errors, notes=notes,
                      status="applied" if changed else "nothing_to_do")
    info["errors"] = errors
    info["error_count"] = int(failed.sum())
    info["dtype_before"], info["dtype_after"] = old_dtype, str(work[column].dtype)
    return work, info


def _convert_series(series, target, dayfirst, date_format, clean_symbols):
    """Return (converted_series, failed_mask). `failed` marks cells that could not convert."""
    missing = blank_mask(series)

    if target == "string":
        out = series.astype(object).map(lambda v: v if is_missing_scalar(v) else _text_value(v))
        return out, pd.Series(False, index=series.index)

    if target in ("integer", "float"):
        numbers = parse_numeric_series(series, clean_symbols=clean_symbols)
        failed = numbers.isna() & ~missing
        if target == "integer":
            not_whole = numbers.notna() & (numbers != numbers.round())
            failed = failed | not_whole
            numbers = numbers.where(~not_whole)
            return numbers.round().astype("Int64"), failed
        return numbers.astype("float64"), failed

    if target in ("date", "datetime"):
        parsed = parse_dates_flexible(series, dayfirst=dayfirst, date_format=date_format)
        failed = parsed.isna() & ~missing
        if target == "date":
            parsed = parsed.dt.normalize()
        return parsed, failed

    # boolean
    def to_bool(value):
        if is_missing_scalar(value):
            return pd.NA
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        token = str(value).strip().lower()
        if token in TRUE_TOKENS:
            return True
        if token in FALSE_TOKENS:
            return False
        return pd.NA

    result = series.map(to_bool)
    failed = result.isna() & ~missing
    return result.astype("boolean"), failed


def _text_value(value) -> str:
    from core.data_utils import value_to_text
    return value_to_text(value)


# --------------------------------------------------------------------------
# F. Outliers
# --------------------------------------------------------------------------
def iqr_bounds(series: pd.Series, k: float = 1.5):
    """
    IQR rule: Q1 = 25th percentile, Q3 = 75th percentile, IQR = Q3 - Q1.
    Values below Q1 - k*IQR or above Q3 + k*IQR are outliers (k=1.5 is standard).
    Returns (lower, upper) or (None, None) if it cannot be calculated.
    """
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 4:
        return None, None
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    spread = q3 - q1
    return float(q1 - k * spread), float(q3 + k * spread)


def detect_outliers_iqr(series: pd.Series, k: float = 1.5) -> tuple[pd.Series, float | None, float | None]:
    """Return (outlier_mask, lower_bound, upper_bound)."""
    numbers = pd.to_numeric(series, errors="coerce")
    lower, upper = iqr_bounds(numbers, k)
    if lower is None:
        return pd.Series(False, index=series.index), None, None
    mask = ((numbers < lower) | (numbers > upper)).fillna(False)
    return mask.astype(bool), lower, upper


def detect_outliers_zscore(series: pd.Series, threshold: float = 3.0) -> tuple[pd.Series, float | None, float | None]:
    """
    Z-score rule: z = (value - mean) / standard deviation. |z| above the
    threshold (3 is common) is an outlier. Equivalent bounds are returned as
    mean -/+ threshold * std. Works best with 30+ values and a roughly bell-
    shaped distribution.
    """
    numbers = pd.to_numeric(series, errors="coerce")
    values = numbers.dropna()
    if len(values) < 3:
        return pd.Series(False, index=series.index), None, None
    std = float(values.std(ddof=1))
    if not std or np.isnan(std):
        return pd.Series(False, index=series.index), None, None
    mean = float(values.mean())
    z = (numbers - mean) / std
    mask = (z.abs() > threshold).fillna(False)
    return mask.astype(bool), mean - threshold * std, mean + threshold * std


def outlier_report(df, columns=None, method="iqr", parameter=None) -> pd.DataFrame:
    """One row per numeric column: bounds, outlier count and percentage."""
    cols = columns if columns is not None else [c for c in df.columns if is_numeric_column(df[c])]
    rows = []
    for col in cols:
        if col not in df.columns or not is_numeric_column(df[col]):
            continue
        if method == "zscore":
            mask, low, high = detect_outliers_zscore(df[col], parameter or 3.0)
        else:
            mask, low, high = detect_outliers_iqr(df[col], parameter or 1.5)
        non_null = int(df[col].notna().sum())
        rows.append({
            "column": col, "method": "Z-score" if method == "zscore" else "IQR",
            "lower_bound": None if low is None else round(low, 4),
            "upper_bound": None if high is None else round(high, 4),
            "outliers": int(mask.sum()),
            "outlier_pct": round(100 * mask.sum() / non_null, 2) if non_null else 0.0,
        })
    return pd.DataFrame(rows, columns=["column", "method", "lower_bound", "upper_bound", "outliers", "outlier_pct"])


def handle_outliers(df, column, method="iqr", parameter=None, action="cap"):
    """
    Apply an outlier action chosen by the user.
    action='remove' -> delete the rows that contain outliers in `column`
    action='cap'    -> pull outliers back to the nearest bound (winsorising)
    Nothing happens unless this function is called explicitly.
    """
    if action not in ("remove", "cap"):
        raise ValueError("action must be 'remove' or 'cap'")
    work = df.copy()
    params = {"method": method, "parameter": parameter, "action": action}
    if column not in work.columns or not is_numeric_column(work[column]):
        info = _make_info("Handle outliers", df, work, [column], params, skipped=[{"column": str(column), "reason": "Not a numeric column"}], status="blocked")
        return work, info
    if method == "zscore":
        mask, low, high = detect_outliers_zscore(work[column], parameter or 3.0)
    else:
        mask, low, high = detect_outliers_iqr(work[column], parameter or 1.5)
    count = int(mask.sum())
    if low is None or count == 0:
        return work, _make_info("Handle outliers", df, work, [column], params, status="nothing_to_do",
                                notes=["No outliers found with these settings."])
    if action == "remove":
        work = work.loc[~mask].copy()
        return work, _make_info("Remove outliers", df, work, [column], params, status="applied")
    series = work[column]
    capped = pd.to_numeric(series, errors="coerce").clip(lower=low, upper=high)
    if pd.api.types.is_integer_dtype(series):
        capped = capped.round().astype(series.dtype if series.isna().sum() == 0 else "Int64")
    work[column] = capped
    return work, _make_info("Cap outliers", df, work, [column], params, cells_changed=count, rows_affected=count)


# --------------------------------------------------------------------------
# G. Standardisation
# --------------------------------------------------------------------------
def standardize_dates(df, column, output_format="%Y-%m-%d", dayfirst=False, date_format=None, on_error="abort"):
    """
    Rewrite a date column in ONE text format (default ISO: 2024-03-15).
    Unparseable values block the operation unless on_error='set_missing'.
    """
    work = df.copy()
    params = {"output_format": output_format, "dayfirst": dayfirst, "date_format": date_format, "on_error": on_error}
    if column not in work.columns:
        return work, _make_info("Standardize dates", df, work, [column], params, skipped=[{"column": str(column), "reason": "Column not found"}], status="blocked")
    series = work[column]
    missing = blank_mask(series)
    parsed = parse_dates_flexible(series, dayfirst=dayfirst, date_format=date_format)
    failed = parsed.isna() & ~missing
    if failed.any() and on_error == "abort":
        info = _make_info("Standardize dates", df, work, [column], params, rows_affected=0, status="blocked",
                          notes=[f"{int(failed.sum())} value(s) are not recognised as dates. Nothing was changed."])
        info["errors"] = [{"row": int(i) + 1, "value": str(series.loc[i])} for i in series.index[failed][:MAX_ERRORS_SHOWN] if isinstance(i, (int, np.integer))]
        info["error_count"] = int(failed.sum())
        return work, info
    text = parsed.dt.strftime(output_format)
    work[column] = text.where(parsed.notna(), np.nan)
    changed = int(parsed.notna().sum())
    return work, _make_info("Standardize dates", df, work, [column], params, cells_changed=changed, rows_affected=changed,
                            status="applied" if changed else "nothing_to_do",
                            notes=[f"{int(failed.sum())} value(s) set to missing."] if failed.any() else [])


def standardize_numeric(df, column, decimals=None, clean_symbols=True, on_error="abort"):
    """Read numbers written as text ('Rs 1,200', '$45') and store them as real numbers."""
    work, info = convert_column_type(df, column, "float", on_error=on_error, clean_symbols=clean_symbols)
    if info["status"] == "applied" and decimals is not None:
        work[column] = work[column].round(int(decimals))
    info["operation"] = "Standardize numeric values"
    info["params"]["decimals"] = decimals
    return work, info


def normalize_numeric(df, columns, method="minmax"):
    """
    Add scaled copies of numeric columns (original columns are kept).
    minmax -> (x - min) / (max - min)  gives values from 0 to 1
    zscore -> (x - mean) / std         gives mean 0 and std 1
    """
    if method not in ("minmax", "zscore"):
        raise ValueError("method must be 'minmax' or 'zscore'")
    work = df.copy()
    cols, skipped = _split_columns(work, columns)
    added = []
    for col in cols:
        if not is_numeric_column(work[col]):
            skipped.append({"column": str(col), "reason": "Not a numeric column"})
            continue
        values = pd.to_numeric(work[col], errors="coerce").astype("float64")
        if method == "minmax":
            span = values.max() - values.min()
            if not span or np.isnan(span):
                skipped.append({"column": str(col), "reason": "All values are equal - cannot scale"})
                continue
            scaled = (values - values.min()) / span
        else:
            std = values.std(ddof=1)
            if not std or np.isnan(std):
                skipped.append({"column": str(col), "reason": "No variation - cannot scale"})
                continue
            scaled = (values - values.mean()) / std
        name, n = f"{col}_{method}", 1
        while name in work.columns:
            n += 1
            name = f"{col}_{method}_{n}"
        work[name] = scaled.round(6)
        added.append(name)
    info = _make_info("Normalize numeric columns", df, work, cols, {"method": method, "new_columns": added},
                      cells_changed=len(added) * len(work), rows_affected=len(work) if added else 0,
                      skipped=skipped, status="applied" if added else "nothing_to_do")
    return work, info


# --------------------------------------------------------------------------
# Custom rules (Module 6)
# --------------------------------------------------------------------------
# Each operation says what inputs the UI must ask for.
RULE_OPERATIONS = {
    "replace_value": {"label": "Replace a specific value", "value_label": "Value to find", "value2_label": "Replace with", "needs_value": True, "needs_value2": True, "kind": "text"},
    "replace_blank": {"label": "Replace blank text", "value_label": "Replace blanks with (leave empty for missing)", "value2_label": "", "needs_value": False, "needs_value2": False, "kind": "text"},
    "trim": {"label": "Trim spaces", "value_label": "", "value2_label": "", "needs_value": False, "needs_value2": False, "kind": "text"},
    "collapse_spaces": {"label": "Remove repeated spaces", "value_label": "", "value2_label": "", "needs_value": False, "needs_value2": False, "kind": "text"},
    "lower": {"label": "Change text to lowercase", "value_label": "", "value2_label": "", "needs_value": False, "needs_value2": False, "kind": "text"},
    "upper": {"label": "Change text to UPPERCASE", "value_label": "", "value2_label": "", "needs_value": False, "needs_value2": False, "kind": "text"},
    "title": {"label": "Change text to Title Case", "value_label": "", "value2_label": "", "needs_value": False, "needs_value2": False, "kind": "text"},
    "remove_characters": {"label": "Remove unwanted characters", "value_label": "Characters to remove (for example #$%)", "value2_label": "", "needs_value": True, "needs_value2": False, "kind": "text"},
    "convert_type": {"label": "Convert column type", "value_label": "Target type", "value2_label": "", "needs_value": True, "needs_value2": False, "kind": "any", "choices": list(TARGET_TYPES)},
    "fill_missing": {"label": "Fill missing values", "value_label": "Method", "value2_label": "Custom value (only for 'custom')", "needs_value": True, "needs_value2": False, "kind": "any", "choices": list(FILL_METHODS)},
    "set_allowed_values": {"label": "Allow only certain values", "value_label": "Allowed values (comma separated)", "value2_label": "Replace other values with (empty = missing)", "needs_value": True, "needs_value2": False, "kind": "text"},
    "clip_range": {"label": "Limit numbers to a range", "value_label": "Minimum (optional)", "value2_label": "Maximum (optional)", "needs_value": False, "needs_value2": False, "kind": "numeric"},
    "round_numbers": {"label": "Round numbers", "value_label": "Decimal places", "value2_label": "", "needs_value": True, "needs_value2": False, "kind": "numeric"},
}


def apply_rule(df: pd.DataFrame, rule: dict):
    """
    Apply one custom cleaning rule: {"column": str, "operation": key, "value": ..., "value2": ...}.
    Returns (new_df, info).
    """
    op = rule.get("operation")
    col = rule.get("column")
    value, value2 = rule.get("value"), rule.get("value2")
    if op not in RULE_OPERATIONS:
        raise ValueError(f"Unknown rule operation: {op}")

    if op == "replace_value":
        work, info = replace_values(df, [col], str(value), "" if value2 is None else str(value2))
    elif op == "replace_blank":
        work, info = replace_blank_text(df, [col], value if value not in ("", None) else None)
    elif op == "trim":
        work, info = trim_spaces(df, [col])
    elif op == "collapse_spaces":
        work, info = collapse_spaces(df, [col])
    elif op in ("lower", "upper", "title"):
        work, info = change_case(df, [col], op)
    elif op == "remove_characters":
        work, info = remove_characters(df, [col], str(value or ""))
    elif op == "convert_type":
        work, info = convert_column_type(df, col, str(value))
    elif op == "fill_missing":
        work, info = fill_missing(df, [col], str(value), custom_value=value2)
    elif op == "set_allowed_values":
        work, info = _set_allowed_values(df, col, value, value2)
    elif op == "clip_range":
        work, info = _clip_range(df, col, value, value2)
    else:  # round_numbers
        work, info = _round_numbers(df, col, value)

    info["rule"] = {"column": col, "operation": op, "value": value, "value2": value2}
    info["operation"] = f"Custom rule: {RULE_OPERATIONS[op]['label']}"
    return work, info


def apply_rules(df: pd.DataFrame, rules: list[dict]):
    """Apply several rules in order. Returns (new_df, [info, ...])."""
    work, infos = df.copy(), []
    for rule in rules:
        work, info = apply_rule(work, rule)
        infos.append(info)
    return work, infos


def _set_allowed_values(df, column, allowed_text, replacement):
    work = df.copy()
    allowed = [a.strip() for a in str(allowed_text or "").split(",") if a.strip()]
    params = {"allowed": allowed, "replace_with": replacement}
    if column not in work.columns or not allowed:
        return work, _make_info("Allow only certain values", df, work, [column], params, status="blocked",
                                skipped=[{"column": str(column), "reason": "Column not found or no allowed values given"}])
    series = work[column]
    present = ~blank_mask(series)
    from core.data_utils import value_to_text
    outside = series.map(lambda v: (not is_missing_scalar(v)) and value_to_text(v).strip() not in allowed).astype(bool) & present
    fill = np.nan if replacement in (None, "") else replacement
    if outside.any():
        converted = series.astype(object).where(~outside, fill)
        work[column] = converted
    info = _finish_cell_op("Allow only certain values", df, work, [column], params, int(outside.sum()), outside.to_numpy(), [])
    return work, info


def _to_float_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _clip_range(df, column, low, high):
    work = df.copy()
    params = {"min": low, "max": high}
    if column not in work.columns or not is_numeric_column(work[column]):
        return work, _make_info("Limit numbers to a range", df, work, [column], params, status="blocked",
                                skipped=[{"column": str(column), "reason": "Not a numeric column"}])
    try:
        lo, hi = _to_float_or_none(low), _to_float_or_none(high)
    except ValueError:
        return work, _make_info("Limit numbers to a range", df, work, [column], params, status="blocked",
                                notes=["Minimum and maximum must be numbers."])
    if lo is None and hi is None:
        return work, _make_info("Limit numbers to a range", df, work, [column], params, status="blocked",
                                notes=["Enter a minimum, a maximum, or both."])
    if lo is not None and hi is not None and lo > hi:
        return work, _make_info("Limit numbers to a range", df, work, [column], params, status="blocked",
                                notes=["Minimum cannot be greater than maximum."])
    series = work[column]
    numbers = pd.to_numeric(series, errors="coerce")
    outside = ((numbers < lo) if lo is not None else pd.Series(False, index=series.index)) | \
              ((numbers > hi) if hi is not None else pd.Series(False, index=series.index))
    outside = outside.fillna(False).astype(bool)
    clipped = numbers.clip(lower=lo, upper=hi)
    if pd.api.types.is_integer_dtype(series) and (lo is None or float(lo).is_integer()) and (hi is None or float(hi).is_integer()):
        clipped = clipped.astype(series.dtype)
    work[column] = clipped
    return work, _finish_cell_op("Limit numbers to a range", df, work, [column], params, int(outside.sum()), outside.to_numpy(), [])


def _round_numbers(df, column, decimals):
    work = df.copy()
    params = {"decimals": decimals}
    if column not in work.columns or not is_numeric_column(work[column]):
        return work, _make_info("Round numbers", df, work, [column], params, status="blocked",
                                skipped=[{"column": str(column), "reason": "Not a numeric column"}])
    try:
        digits = int(float(decimals))
    except (TypeError, ValueError):
        return work, _make_info("Round numbers", df, work, [column], params, status="blocked", notes=["Decimal places must be a whole number."])
    before = work[column]
    after = before.round(digits)
    changed = ((before != after) & before.notna()).to_numpy()
    work[column] = after
    return work, _finish_cell_op("Round numbers", df, work, [column], params, int(changed.sum()), changed, [])
