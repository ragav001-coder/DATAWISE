"""
state.py - everything about Streamlit session state in one place.

Streamlit re-runs the whole script on every click. Anything that must survive
a click lives in st.session_state. This file defines WHAT is stored and the
only functions that change it, so pages stay simple.

Stored per browser session (nothing is saved on the server's disk, and it is
all lost when the session ends or the page is refreshed):
    original_df    the dataset exactly as uploaded (never modified)
    working_df     the copy that cleaning operations change
    history        list of cleaning steps (Module 10)
    undo_stack     a few earlier versions of working_df for "Undo last step"
    settings       user preferences (Settings page)
    validation_*   the rules chosen and the latest validation result
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.data_utils import count_blank_cells, now_str
from core.quality_score import compute_quality_score

MAX_UNDO = 8
MAX_UNDO_CELLS = 3_000_000  # skip snapshots for very large tables to save memory

DEFAULT_SETTINGS = {
    "preview_rows": 20,              # rows shown in previews
    "treat_blank_as_missing": True,  # empty / space-only text counts as missing
    "phone_min_digits": 7,           # automatic phone rule
    "phone_max_digits": 15,
    "iqr_multiplier": 1.5,           # outlier detection defaults
    "zscore_threshold": 3.0,
    "dayfirst": False,               # how ambiguous dates like 05/06/2024 are read
}


def init_state() -> None:
    """Create every key once. Safe to call on every run."""
    defaults = {
        "original_df": None, "working_df": None, "file_name": None, "file_size": None, "source": None,
        "load_id": 0, "data_version": 0, "history": [], "undo_stack": [],
        "validation_rules": [], "validation_result": None, "validation_meta": None,
        "recs": None, "recs_key": None, "cache": {}, "upload_cache": {},
        "settings": dict(DEFAULT_SETTINGS),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    for key, value in DEFAULT_SETTINGS.items():  # keep older sessions working
        st.session_state["settings"].setdefault(key, value)


def settings() -> dict:
    return st.session_state["settings"]


def has_data() -> bool:
    return st.session_state.get("original_df") is not None


def original() -> pd.DataFrame:
    return st.session_state["original_df"]


def working() -> pd.DataFrame:
    return st.session_state["working_df"]


def is_modified() -> bool:
    return has_data() and any(h.get("status") == "applied" for h in st.session_state["history"])


# --------------------------------------------------------------------------
# Loading / resetting
# --------------------------------------------------------------------------
def set_dataset(df: pd.DataFrame, name: str, size: int | None, source: str) -> None:
    """Replace the current dataset. Clears history, validation and caches."""
    st.session_state.update({
        "original_df": df.copy(), "working_df": df.copy(), "file_name": name, "file_size": size, "source": source,
        "load_id": st.session_state["load_id"] + 1, "data_version": 0, "history": [], "undo_stack": [],
        "validation_result": None, "validation_meta": None, "recs": None, "recs_key": None, "cache": {},
    })


def clear_dataset() -> None:
    """Remove the dataset but keep the user's settings."""
    keep = st.session_state["settings"]
    load_id = st.session_state["load_id"]
    for key in ("original_df", "working_df", "file_name", "file_size", "source", "validation_result", "validation_meta", "recs", "recs_key"):
        st.session_state[key] = None
    st.session_state.update({"history": [], "undo_stack": [], "validation_rules": [], "cache": {},
                             "data_version": 0, "load_id": load_id + 1, "settings": keep})


def reset_everything() -> None:
    """Full reset: dataset, history, rules AND settings back to defaults."""
    clear_dataset()
    st.session_state["settings"] = dict(DEFAULT_SETTINGS)
    st.session_state["upload_cache"] = {}


def _bump() -> None:
    st.session_state["data_version"] += 1
    st.session_state["recs"] = None


def _log(info: dict, missing_before: int | None, missing_after: int | None) -> None:
    history = st.session_state["history"]
    history.append({
        "step": len(history) + 1, "timestamp": now_str(), "operation": info.get("operation", "Operation"),
        "columns": info.get("columns", []), "params": info.get("params", {}),
        "rows_before": info.get("rows_before"), "rows_after": info.get("rows_after"),
        "rows_affected": info.get("rows_affected"), "cells_changed": info.get("cells_changed"),
        "missing_before": missing_before, "missing_after": missing_after,
        "status": info.get("status"), "notes": info.get("notes", []) + [f"{s['column']}: {s['reason']}" for s in info.get("skipped", [])],
        "error_count": info.get("error_count", 0),
    })


def apply_operation(func, *args, push_undo: bool = True, **kwargs) -> dict:
    """
    Run a cleaning function on the working copy and keep the result only if it
    really changed something.

    func(df, *args, **kwargs) must return (new_df, info), like every function
    in core/cleaning_engine.py. Blocked or no-op results never change the data.
    The step is added to the history (also when blocked, so nothing is hidden).
    """
    df = st.session_state["working_df"]
    new_df, info = func(df, *args, **kwargs)
    if info.get("status") == "applied":
        if push_undo and df.size <= MAX_UNDO_CELLS:
            stack = st.session_state["undo_stack"]
            stack.append(df.copy())
            del stack[:-MAX_UNDO]
        st.session_state["working_df"] = new_df
        _log(info, count_blank_cells(df), count_blank_cells(new_df))
        _bump()
    elif info.get("status") == "blocked":
        _log(info, None, None)
    return info


def can_undo() -> bool:
    return bool(st.session_state.get("undo_stack"))


def undo_last() -> bool:
    """Go back to the version before the last applied step (or batch of steps)."""
    stack = st.session_state["undo_stack"]
    if not stack:
        return False
    current = st.session_state["working_df"]
    st.session_state["working_df"] = stack.pop()
    _log({"operation": "Undo last step", "rows_before": len(current), "rows_after": len(st.session_state["working_df"]),
          "status": "applied", "notes": ["Restored the version before the previous step."]},
         count_blank_cells(current), count_blank_cells(st.session_state["working_df"]))
    _bump()
    return True


def reset_to_original() -> None:
    """Throw away all cleaning and go back to the uploaded data."""
    current = st.session_state["working_df"]
    st.session_state["working_df"] = st.session_state["original_df"].copy()
    st.session_state["undo_stack"] = []
    _log({"operation": "Reset to original data", "rows_before": len(current), "rows_after": len(st.session_state["working_df"]),
          "status": "applied", "notes": ["All cleaning steps were discarded."]},
         count_blank_cells(current), count_blank_cells(st.session_state["working_df"]))
    _bump()


# --------------------------------------------------------------------------
# Cached calculations (scores are only recalculated when data or rules change)
# --------------------------------------------------------------------------
def _rules_signature() -> str:
    return json.dumps(st.session_state["validation_rules"], sort_keys=True, default=str)


def _cached(key, compute):
    cache = st.session_state["cache"]
    if key not in cache:
        if len(cache) > 24:
            cache.clear()
        cache[key] = compute()
    return cache[key]


def get_scores() -> tuple[dict, dict]:
    """(score of the original upload, score of the current working data)."""
    cfg = settings()
    rules = st.session_state["validation_rules"] or None
    phone = (cfg["phone_min_digits"], cfg["phone_max_digits"])
    sig = (_rules_signature(), phone)
    original_score = _cached(("orig", st.session_state["load_id"]) + sig,
                             lambda: compute_quality_score(st.session_state["original_df"], rules, phone))
    current_score = _cached(("cur", st.session_state["data_version"]) + sig,
                            lambda: compute_quality_score(st.session_state["working_df"], rules, phone))
    return original_score, current_score


def validation_is_current() -> bool:
    meta = st.session_state.get("validation_meta")
    return bool(meta) and meta.get("version") == st.session_state["data_version"] and meta.get("load_id") == st.session_state["load_id"]


def store_validation(result, rules: list[dict]) -> None:
    st.session_state["validation_result"] = result
    st.session_state["validation_meta"] = {"version": st.session_state["data_version"], "load_id": st.session_state["load_id"],
                                           "rules": list(rules), "time": now_str()}
