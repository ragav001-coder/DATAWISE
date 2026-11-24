"""Tests for reading CSV / Excel / JSON files and for the export functions."""

import io
import json

import pandas as pd
import pytest

from core.file_handler import (
    FileReadError,
    dataframe_to_csv_bytes,
    dataframe_to_excel_bytes,
    dataframes_to_excel_bytes,
    read_uploaded_file,
)


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


# ----------------------------------------------------------------- reading
def test_read_csv_basic():
    df = read_uploaded_file(csv_bytes("a,b\n1,x\n2,y\n"), "data.csv")
    assert df.shape == (2, 2)
    assert list(df.columns) == ["a", "b"]
    assert df["a"].tolist() == [1, 2]


def test_read_csv_semicolon_separator_is_detected():
    df = read_uploaded_file(csv_bytes("a;b;c\n1;2;3\n4;5;6\n"), "semi.csv")
    assert df.shape == (2, 3)


def test_read_csv_latin1_encoding():
    raw = "name,city\nJosé,Málaga\n".encode("cp1252")
    df = read_uploaded_file(raw, "latin.csv")
    assert df.loc[0, "name"] == "José"


def test_read_csv_with_utf8_bom_has_clean_first_column():
    raw = b"\xef\xbb\xbfid,name\n1,A\n"
    df = read_uploaded_file(raw, "bom.csv")
    assert list(df.columns) == ["id", "name"]


def test_read_excel_roundtrip():
    buffer = io.BytesIO()
    pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}).to_excel(buffer, index=False)
    df = read_uploaded_file(buffer.getvalue(), "book.xlsx")
    assert df.shape == (3, 2)
    assert df["name"].tolist() == ["a", "b", "c"]


def test_read_json_list_of_records():
    payload = json.dumps([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    df = read_uploaded_file(payload.encode(), "records.json")
    assert df.shape == (2, 2)


def test_read_json_nested_wrapper_and_nested_values():
    payload = json.dumps({"data": [{"id": 1, "tags": ["x", "y"], "owner": {"name": "A"}}]})
    df = read_uploaded_file(payload.encode(), "wrapped.json")
    assert df.shape[0] == 1
    assert df.loc[0, "tags"] == '["x", "y"]'   # lists are stored as JSON text
    assert df.loc[0, "owner.name"] == "A"


def test_read_json_lines():
    payload = '{"a": 1}\n{"a": 2}\n'
    df = read_uploaded_file(payload.encode(), "lines.json")
    assert df["a"].tolist() == [1, 2]


def test_whole_number_floats_with_blanks_become_nullable_integers():
    df = read_uploaded_file(csv_bytes("age,name\n30,a\n,b\n41,c\n"), "ages.csv")
    assert str(df["age"].dtype) == "Int64"
    assert dataframe_to_csv_bytes(df).decode("utf-8-sig").split("\n")[1] == "30,a"


# ------------------------------------------------------------------ errors
@pytest.mark.parametrize("name", ["data.txt", "data.exe", "data", "data.xls"])
def test_unsupported_extension_is_rejected(name):
    with pytest.raises(FileReadError, match="Unsupported"):
        read_uploaded_file(b"abc", name)


def test_empty_file_is_rejected():
    with pytest.raises(FileReadError, match="empty"):
        read_uploaded_file(b"", "x.csv")


def test_header_only_csv_is_rejected():
    with pytest.raises(FileReadError, match="no data rows"):
        read_uploaded_file(csv_bytes("a,b,c\n"), "x.csv")


def test_corrupted_excel_is_rejected():
    with pytest.raises(FileReadError, match="corrupted"):
        read_uploaded_file(b"this is not an excel file", "x.xlsx")


def test_invalid_json_is_rejected():
    with pytest.raises(FileReadError):
        read_uploaded_file(b"{not valid json", "x.json")


def test_json_without_tabular_data_is_rejected():
    with pytest.raises(FileReadError, match="tabular"):
        read_uploaded_file(b'{"a": {"b": {"c": 1}}}', "x.json")


def test_too_large_file_is_rejected():
    with pytest.raises(FileReadError, match="larger"):
        read_uploaded_file(b"a,b\n" + b"1,2\n" * 1000, "x.csv", max_mb=0.001)


def test_file_name_with_path_is_not_trusted():
    # only the extension matters; folders in the name are ignored
    df = read_uploaded_file(csv_bytes("a\n1\n"), "../../etc/passwd.csv")
    assert df.shape == (1, 1)


# ------------------------------------------------------------------ export
def test_csv_export_roundtrip_and_bom():
    df = pd.DataFrame({"name": ["José", "Ann"], "n": [1, 2]})
    data = dataframe_to_csv_bytes(df)
    assert data.startswith(b"\xef\xbb\xbf")
    back = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")
    assert back.equals(df)


def test_excel_export_roundtrip():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    data = dataframe_to_excel_bytes(df, "Cleaned")
    back = pd.read_excel(io.BytesIO(data), sheet_name="Cleaned")
    assert back.equals(df)


def test_excel_export_multiple_sheets_and_bad_sheet_names():
    data = dataframes_to_excel_bytes({"One": pd.DataFrame({"a": [1]}), "Bad/name:*?": pd.DataFrame({"b": [2]})})
    book = pd.ExcelFile(io.BytesIO(data))
    assert len(book.sheet_names) == 2
    assert all(len(n) <= 31 and "/" not in n for n in book.sheet_names)


def test_excel_export_does_not_create_formulas():
    df = pd.DataFrame({"x": ["=1+1", "@SUM(A1)", "normal"]})
    data = dataframe_to_excel_bytes(df)
    from openpyxl import load_workbook

    sheet = load_workbook(io.BytesIO(data)).active
    assert sheet["A2"].data_type == "s"
    assert sheet["A2"].value == "=1+1"
