"""
file_handler.py - reading uploaded files and writing downloadable files.

Reading:  CSV, Excel (.xlsx) and JSON  ->  pandas DataFrame
Writing:  DataFrame -> CSV bytes / Excel bytes

Safety notes (also explained in the README):
  * Uploaded files are only READ as data. Nothing in an uploaded file is ever
    executed, and nothing is written to disk - everything is handled in memory.
  * The file name is only used for display and to pick the reader by its
    extension. It is never used as a path.
"""

from __future__ import annotations

import io
import json
import os

import pandas as pd

MAX_FILE_MB = 50
SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".json")
_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_CSV_SEPARATORS = (",", ";", "\t", "|")


class FileReadError(Exception):
    """Raised with a clear, user-friendly message when a file cannot be read."""


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def get_extension(filename: str) -> str:
    """Lower-case extension of a file name, e.g. '.csv'. Folders are ignored."""
    base = os.path.basename(str(filename or ""))
    return os.path.splitext(base)[1].lower()


def read_uploaded_file(
    file_bytes: bytes, filename: str, max_mb: float = MAX_FILE_MB
) -> pd.DataFrame:
    """
    Read an uploaded file (given as raw bytes) into a DataFrame.

    Raises FileReadError with a readable message when the file is empty,
    too large, of an unsupported type, or corrupted.
    """
    ext = get_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise FileReadError(
            f"Unsupported file type '{ext or 'unknown'}'. "
            f"Please upload one of: {', '.join(SUPPORTED_EXTENSIONS)}."
        )
    if not file_bytes:
        raise FileReadError("The file is empty (0 bytes).")
    if len(file_bytes) > max_mb * 1024 * 1024:
        raise FileReadError(
            f"The file is larger than the {max_mb:.0f} MB limit of this app. "
            "Please upload a smaller file or a sample of your data."
        )

    if ext == ".csv":
        df = _read_csv(file_bytes)
    elif ext == ".xlsx":
        df = _read_excel(file_bytes)
    else:
        df = _read_json(file_bytes)

    return _finalise(df)


def _read_csv(data: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in _CSV_ENCODINGS:
        try:
            df = pd.read_csv(io.BytesIO(data), encoding=encoding)
            if df.shape[1] == 1:  # maybe a different separator was used
                for sep in _CSV_SEPARATORS[1:]:
                    try:
                        alt = pd.read_csv(io.BytesIO(data), encoding=encoding, sep=sep)
                    except Exception:  # noqa: BLE001 - just trying alternatives
                        continue
                    if alt.shape[1] > 1:
                        return alt
            return df
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except pd.errors.EmptyDataError:
            raise FileReadError("The CSV file contains no data.") from None
        except pd.errors.ParserError as exc:
            raise FileReadError(
                "The CSV file is damaged or irregular and could not be parsed. "
                f"Details: {_short(exc)}"
            ) from None
        except Exception as exc:  # noqa: BLE001
            raise FileReadError(f"The CSV file could not be read: {_short(exc)}") from None
    raise FileReadError(
        "The CSV text encoding could not be recognised. "
        f"Try saving the file as UTF-8. ({_short(last_error)})"
    )


def _read_excel(data: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(io.BytesIO(data), engine="openpyxl")
    except ValueError as exc:
        raise FileReadError(f"The Excel file has no readable sheet: {_short(exc)}") from None
    except Exception as exc:  # noqa: BLE001 - zip errors, corrupted xml, ...
        raise FileReadError(
            "The Excel file is corrupted or is not a real .xlsx workbook. "
            f"Details: {_short(exc)}"
        ) from None


def _read_json(data: bytes) -> pd.DataFrame:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError:
            raise FileReadError("The JSON file is not valid text (encoding problem).") from None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as first_error:
        # Maybe "JSON Lines": one JSON object per line.
        try:
            payload = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError:
            raise FileReadError(
                f"The JSON file is not valid JSON ({_short(first_error)})."
            ) from None
        if not payload:
            raise FileReadError("The JSON file contains no data.") from None

    records = _extract_records(payload)
    try:
        df = pd.json_normalize(records)
    except Exception as exc:  # noqa: BLE001
        raise FileReadError(f"The JSON structure could not be converted: {_short(exc)}") from None
    return df


def _extract_records(payload) -> list:
    """Find the list of records inside many common JSON layouts."""
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            return payload
        if payload and all(isinstance(item, (str, int, float, bool)) or item is None for item in payload):
            return [{"value": item} for item in payload]
        raise FileReadError("The JSON list must contain objects (records) like {\"name\": \"A\"}.")
    if isinstance(payload, dict):
        # {"data": [ {...}, {...} ]}  - use the first list of records we find
        for value in payload.values():
            if isinstance(value, list) and value and all(isinstance(i, dict) for i in value):
                return value
        # {"col1": [..], "col2": [..]}  - columns as lists
        if payload and all(isinstance(v, list) for v in payload.values()):
            lengths = {len(v) for v in payload.values()}
            if len(lengths) == 1:
                return pd.DataFrame(payload).to_dict(orient="records")
        # a single record {"a": 1, "b": 2}
        if payload and all(not isinstance(v, (list, dict)) for v in payload.values()):
            return [payload]
    raise FileReadError(
        "Could not find tabular data in this JSON. Expected a list of records, "
        "a dictionary of equal-length lists, or an object containing a list of records."
    )


def _finalise(df: pd.DataFrame) -> pd.DataFrame:
    """Common checks and tidy-up for every file type."""
    if df is None or df.shape[1] == 0:
        raise FileReadError("No columns were found in the file.")
    if df.shape[0] == 0:
        raise FileReadError("The file has column headings but no data rows.")
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    # Nested lists / dictionaries (from JSON) are stored as JSON text so every
    # cell is a simple value.
    for col in df.columns:
        if df[col].dtype == object:
            if df[col].map(lambda v: isinstance(v, (list, dict))).any():
                df[col] = df[col].map(
                    lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                )
    df = df.reset_index(drop=True)
    # pandas turns an integer column with blanks into floats (39 -> 39.0). If every
    # value is a whole number, keep it as a nullable integer so exports show 39.
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_float_dtype(series) and series.isna().any():
            values = series.dropna()
            if len(values) and (values % 1 == 0).all() and values.abs().max() < 2**53:
                df[col] = series.astype("Int64")
    return df


def _short(exc: Exception | None, limit: int = 160) -> str:
    text = str(exc) if exc is not None else "unknown error"
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV as UTF-8 with a BOM so Excel opens non-English text correctly."""
    return df.to_csv(index=False).encode("utf-8-sig")


def dataframes_to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """
    Several DataFrames -> one .xlsx file (one sheet each).

    openpyxl turns any text starting with '=' into a spreadsheet formula. To
    stop uploaded data from becoming formulas, every text cell is forced to
    stay plain text.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            safe_name = _sheet_name(name)
            export = _excel_ready(frame)
            export.to_excel(writer, sheet_name=safe_name, index=False)
            worksheet = writer.sheets[safe_name]
            for row in worksheet.iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
            _autosize(worksheet)
    return buffer.getvalue()


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Cleaned data") -> bytes:
    return dataframes_to_excel_bytes({sheet_name: df})


def _excel_ready(df: pd.DataFrame) -> pd.DataFrame:
    """Excel cannot store time-zone aware datetimes or nested objects."""
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    for col in out.columns:
        series = out[col]
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            out[col] = series.dt.tz_localize(None)
    return out


def _sheet_name(name: str) -> str:
    bad = '[]:*?/\\'
    cleaned = "".join("_" if ch in bad else ch for ch in str(name)).strip() or "Sheet"
    return cleaned[:31]


def _autosize(worksheet, max_width: int = 45) -> None:
    for column_cells in worksheet.columns:
        length = max((len(str(c.value)) for c in column_cells[:200] if c.value is not None), default=8)
        worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 8), max_width)
