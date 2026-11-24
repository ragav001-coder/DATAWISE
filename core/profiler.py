"""
profiler.py - describes a dataset: one row of facts per column, plus totals.

The profile is the "health check" that every other part of the app builds on.
Everything is calculated from the real data; nothing is estimated or faked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.cleaning_engine import detect_outliers_iqr
from core.data_utils import (
    blank_mask,
    column_kind,
    count_blank_cells,
    count_duplicate_rows,
    is_numeric_column,
    is_text_series,
)

PROFILE_COLUMNS = [
    "column", "data_type", "total_records", "non_null", "missing", "missing_pct",
    "empty_strings", "unique_values", "duplicate_values", "min", "max", "mean",
    "median", "outliers_iqr", "common_values",
]


def overall_profile(df: pd.DataFrame) -> dict:
    """Dataset-level totals. Safe for empty DataFrames."""
    rows, cols = int(df.shape[0]), int(df.shape[1])
    total_cells = rows * cols
    blank_cells = count_blank_cells(df)
    kinds: dict[str, int] = {}
    for col in df.columns:
        kind = column_kind(df[col])
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "rows": rows,
        "columns": cols,
        "total_cells": total_cells,
        "missing_cells": blank_cells,
        "missing_pct": round(100 * blank_cells / total_cells, 2) if total_cells else 0.0,
        "duplicate_rows": count_duplicate_rows(df),
        "memory_kb": round(float(df.memory_usage(deep=True).sum()) / 1024, 1) if cols else 0.0,
        "dtype_counts": kinds,
    }


def _common_values(series: pd.Series, top: int = 3) -> str:
    present = series[~blank_mask(series)]
    if present.empty:
        return ""
    counts = present.astype(str).value_counts().head(top)
    return "; ".join(f"{value} ({count})" for value, count in counts.items())


def profile_column(series: pd.Series) -> dict:
    """All profile facts for a single column."""
    total = int(len(series))
    nulls = int(series.isna().sum())
    empty_strings = 0
    if is_text_series(series):
        empty_strings = int(series.map(lambda v: isinstance(v, str) and v.strip() == "").sum())
    missing = nulls + empty_strings
    non_null = total - missing
    present = series[~blank_mask(series)]
    try:
        unique = int(present.astype(str).nunique()) if not present.empty else 0
    except Exception:  # noqa: BLE001 - unhashable values
        unique = 0

    row = {
        "column": str(series.name),
        "data_type": column_kind(series),
        "total_records": total,
        "non_null": non_null,
        "missing": missing,
        "missing_pct": round(100 * missing / total, 2) if total else 0.0,
        "empty_strings": empty_strings,
        "unique_values": unique,
        # values that appear more than once (non-missing records minus distinct values)
        "duplicate_values": max(non_null - unique, 0),
        "min": np.nan, "max": np.nan, "mean": np.nan, "median": np.nan,
        "outliers_iqr": np.nan,
        "common_values": _common_values(series),
    }
    if is_numeric_column(series):
        numbers = pd.to_numeric(series, errors="coerce").dropna()
        if not numbers.empty:
            row.update(
                min=float(numbers.min()), max=float(numbers.max()),
                mean=round(float(numbers.mean()), 4), median=float(numbers.median()),
            )
            mask, _, _ = detect_outliers_iqr(series)
            row["outliers_iqr"] = int(mask.sum())
    return row


def profile_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """One row per column. Returns an empty table with headers for empty data."""
    if df.shape[1] == 0:
        return pd.DataFrame(columns=PROFILE_COLUMNS)
    rows = [profile_column(df[col].rename(col)) for col in df.columns]
    return pd.DataFrame(rows, columns=PROFILE_COLUMNS)


def dtype_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """How many columns of each type (for the data-type chart)."""
    counts = overall_profile(df)["dtype_counts"]
    return pd.DataFrame({"type": list(counts.keys()), "columns": list(counts.values())})
