"""
data_utils.py - small shared helpers used by every other core module.

Nothing in this file knows about Streamlit. It only contains plain Python /
Pandas helpers, so it can be tested without opening the web app.

What lives here:
  * constants (app name, version, regular expressions)
  * "is this value missing / blank?" helpers
  * column type helpers (is a column text? numeric? date?)
  * flexible number and date parsers that the cleaning, validation and
    scoring modules all share (so they always agree with each other)
"""

from __future__ import annotations

import re
from datetime import datetime

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
APP_NAME = "DATAWISE"
APP_TITLE = "Data Cleaning and Validation Engine"
APP_TAGLINE = "Transform Raw Data into Reliable Insights"
APP_VERSION = "1.0.0"
DEVELOPER = "Ragav K P"
COMPANY_NAME = "DefineInfoTech"

# Email: local part, one "@", domain labels, and a top-level domain of 2+ letters.
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$"
)

# A plain number such as 12, -3.5, .5, 1e3 (no commas, no currency symbols).
NUMERIC_REGEX = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

# Strings that "look like" a date. We insist on a date-like shape so that a
# plain number such as "5" is never mistaken for a date.
DATE_LIKE_REGEX = re.compile(
    r"^(?:"
    r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?"
    r"|\d{1,2}[ \-/]?(?:" + _MONTHS + r")[a-z]*[ \-/,]*\d{2,4}"
    r"|(?:" + _MONTHS + r")[a-z]*\.? +\d{1,2}(?:st|nd|rd|th)?,? +\d{2,4}"
    r")$",
    re.IGNORECASE,
)

ISO_DATE_REGEX = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}(?:[T ].*)?$")

TRUE_TOKENS = {"true", "t", "yes", "y", "1"}
FALSE_TOKENS = {"false", "f", "no", "n", "0"}


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def now_str() -> str:
    """Current time as 'YYYY-MM-DD HH:MM:SS' (server time)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_bytes(num_bytes: int | float) -> str:
    """Turn a byte count into a friendly string such as '1.4 MB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def pct(part: float, whole: float, digits: int = 1) -> float:
    """Safe percentage: returns 0.0 when whole is 0."""
    if not whole:
        return 0.0
    return round(100.0 * part / whole, digits)


# --------------------------------------------------------------------------
# Missing / blank helpers
# --------------------------------------------------------------------------
def is_missing_scalar(value) -> bool:
    """True for None, NaN, pd.NA and pd.NaT (works on any single value)."""
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, float) and value != value:  # NaN != NaN
        return True
    return False


def is_text_series(series: pd.Series) -> bool:
    """True for columns that hold text (object or string dtype)."""
    return bool(ptypes.is_object_dtype(series) or ptypes.is_string_dtype(series))


def column_kind(series: pd.Series) -> str:
    """Return one of: boolean, integer, float, datetime, text, other."""
    if ptypes.is_bool_dtype(series):
        return "boolean"
    if ptypes.is_integer_dtype(series):
        return "integer"
    if ptypes.is_float_dtype(series):
        return "float"
    if ptypes.is_datetime64_any_dtype(series):
        return "datetime"
    if is_text_series(series):
        return "text"
    return "other"


def is_numeric_column(series: pd.Series) -> bool:
    """True for real number columns (booleans are not counted as numbers)."""
    return ptypes.is_numeric_dtype(series) and not ptypes.is_bool_dtype(series)


def numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if is_numeric_column(df[c])]


def text_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if is_text_series(df[c])]


def blank_mask(series: pd.Series) -> pd.Series:
    """
    True where a cell is missing (NaN/None) OR is an empty / whitespace-only
    string. Used everywhere a "missing or blank" decision is needed.
    """
    mask = series.isna()
    if is_text_series(series):
        empty = series.map(lambda v: isinstance(v, str) and v.strip() == "")
        mask = mask | empty.astype(bool)
    return mask.astype(bool)


def count_blank_cells(df: pd.DataFrame) -> int:
    """Total number of missing-or-blank cells in the whole DataFrame."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return 0
    return int(sum(int(blank_mask(df[c]).sum()) for c in df.columns))


def count_duplicate_rows(df: pd.DataFrame, subset: list[str] | None = None) -> int:
    """Number of rows that repeat an earlier row (the first copy is kept)."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return 0
    return int(df.duplicated(subset=subset or None, keep="first").sum())


def row_numbers(df: pd.DataFrame) -> pd.Series:
    """
    1-based row numbers for reports. If the index is made of integers (the
    normal case after loading a file) the index label + 1 is used, so a row
    keeps its number even after other rows are deleted.
    """
    if ptypes.is_integer_dtype(df.index):
        return pd.Series(df.index.to_numpy() + 1, index=df.index)
    return pd.Series(np.arange(1, len(df) + 1), index=df.index)


# --------------------------------------------------------------------------
# Value -> text helpers
# --------------------------------------------------------------------------
def value_to_text(value) -> str:
    """
    Turn a cell into text the way a human would write it. Whole-number floats
    such as 9876543210.0 become '9876543210' (Excel often stores phone numbers
    that way).
    """
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if float(value).is_integer():
            return str(int(value))
        return str(float(value))
    return str(value)


_CURRENCY_STRIP = re.compile(r"(?i)rs\.?|inr|[₹$€£¥,\s]")


def _clean_number_text(value, clean_symbols: bool) -> str | None:
    if is_missing_scalar(value) or isinstance(value, (bool, np.bool_)):
        return None
    text = str(value).strip()
    if clean_symbols:
        text = _CURRENCY_STRIP.sub("", text)
    return text or None


def parse_numeric_series(series: pd.Series, clean_symbols: bool = False) -> pd.Series:
    """
    Convert a column to float. Anything that is not a clean number becomes NaN.

    clean_symbols=True first removes currency signs (Rs, INR, $, EUR, GBP),
    thousands commas and spaces, so '1,200' and '$45' can be read.
    Values that are NaN/inf are treated as invalid.
    """
    if ptypes.is_bool_dtype(series):
        return pd.Series(np.nan, index=series.index, dtype="float64")
    if ptypes.is_numeric_dtype(series):
        out = pd.to_numeric(series, errors="coerce").astype("float64")
        return out.where(np.isfinite(out))
    cleaned = series.map(lambda v: _clean_number_text(v, clean_symbols))
    valid = cleaned.map(lambda t: isinstance(t, str) and bool(NUMERIC_REGEX.match(t))).astype(bool)
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    if valid.any():
        out[valid] = cleaned[valid].astype(float).to_numpy()
    return out.where(np.isfinite(out))


def parse_dates_flexible(
    series: pd.Series,
    dayfirst: bool = False,
    date_format: str | None = None,
) -> pd.Series:
    """
    Parse a column of dates written in many styles. Unparseable cells become NaT.

    * date_format given  -> strict parsing with that format (e.g. '%d/%m/%Y')
    * otherwise          -> ISO dates (2024-03-15) are read as year-month-day;
                            everything else is parsed cell by cell, using
                            `dayfirst` to decide between 05/06/2024 = 5 June
                            (dayfirst=True) and 6 May (dayfirst=False).
    """
    if ptypes.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    text = series.map(lambda v: None if is_missing_scalar(v) else str(v).strip())
    text = text.map(lambda v: None if v in (None, "") else v).astype("string")

    if date_format:
        return pd.to_datetime(text, format=date_format, errors="coerce")

    iso = text.str.match(ISO_DATE_REGEX).fillna(False).astype(bool)
    rest = text.notna() & ~iso

    parsed_iso = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    parsed_rest = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if iso.any():
        parsed_iso = pd.to_datetime(
            text.where(iso), format="ISO8601", errors="coerce"
        ).astype("datetime64[ns]")
    if rest.any():
        parsed_rest = pd.to_datetime(
            text.where(rest), format="mixed", dayfirst=dayfirst, errors="coerce"
        ).astype("datetime64[ns]")
    return parsed_iso.fillna(parsed_rest)


def looks_like_date(value) -> bool:
    """True if a single value has a date-like shape (see DATE_LIKE_REGEX)."""
    if is_missing_scalar(value):
        return False
    if isinstance(value, (datetime, pd.Timestamp)):
        return True
    return bool(DATE_LIKE_REGEX.match(str(value).strip()))


def date_shape(value: str) -> str:
    """
    A rough "shape" of a date string, used to spot mixed date formats.
    2024-03-15 -> 'Y-d-d',  15/03/2024 -> 'd/d/Y',  5 Mar 2024 -> 'd a Y'.
    """

    def digits(match: re.Match) -> str:
        n = len(match.group(0))
        return "Y" if n == 4 else ("d" if n <= 2 else "n")

    shape = re.sub(r"\d+", digits, value.strip())
    shape = re.sub(r"[A-Za-z]+", "a", shape)
    return shape


def collapse_spaces_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


# --------------------------------------------------------------------------
# Display helper
# --------------------------------------------------------------------------
def arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Streamlit shows tables through Apache Arrow, which refuses columns that mix
    types (for example numbers and text in one column). This returns a copy in
    which such columns are shown as text. Only used for DISPLAY - never for
    changing the user's data.
    """
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    for col in out.columns:
        series = out[col]
        if ptypes.is_object_dtype(series):
            kinds = {type(v) for v in series.dropna().head(2000)}
            if len(kinds) > 1 or any(k not in (str, int, float, bool) for k in kinds):
                out[col] = series.map(lambda v: v if is_missing_scalar(v) else str(v))
    return out
