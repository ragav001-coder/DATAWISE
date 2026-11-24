"""tables.py - one place to show DataFrames so they never crash Streamlit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.data_utils import arrow_safe


def show_table(df: pd.DataFrame, height: int | None = None, hide_index: bool = True, key: str | None = None) -> None:
    """Interactive table (sortable, searchable, resizable). Mixed-type columns are displayed as text."""
    if df is None or df.shape[1] == 0:
        st.caption("Nothing to show.")
        return
    kwargs = {"width": "stretch", "hide_index": hide_index}
    if height:
        kwargs["height"] = height
    if key:
        kwargs["key"] = key
    st.dataframe(arrow_safe(df), **kwargs)


def preview_table(df: pd.DataFrame, rows: int = 20, key: str | None = None) -> None:
    show_table(df.head(rows), height=min(520, 45 + 35 * min(rows, len(df))), hide_index=False, key=key)
    st.caption(f"Showing the first {min(rows, len(df)):,} of {len(df):,} rows.")


def dtype_table(df: pd.DataFrame) -> pd.DataFrame:
    """Column names with their stored data types and a sample value."""
    rows = []
    for col in df.columns:
        present = df[col].dropna()
        sample = "" if present.empty else str(present.iloc[0])
        rows.append({"column": col, "data type": str(df[col].dtype), "non-null": int(df[col].notna().sum()), "example": sample[:40]})
    return pd.DataFrame(rows)
