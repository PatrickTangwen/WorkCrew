import pytest
from openpyxl import Workbook

from workflow_app.workbook.outline import build_outline


def write_workbook(path, rows, sheet_title="Invoices", extra_sheet=None):
    book = Workbook()
    sheet = book.active
    sheet.title = sheet_title
    for cell, value in rows.items():
        sheet[cell] = value
    if extra_sheet is not None:
        book.create_sheet(extra_sheet)
    book.save(path)
    return path


def test_outline_reports_every_sheet(tmp_path):
    path = write_workbook(
        tmp_path / "template.xlsx", {"A1": "Invoice No"}, extra_sheet="Reference"
    )

    outline = build_outline(path)

    assert [sheet.name for sheet in outline.sheets] == ["Invoices", "Reference"]


def test_cells_carry_their_real_column_letters(tmp_path):
    # Column letters come from the file, so a gap between populated
    # columns never shifts the letters that follow it.
    path = write_workbook(
        tmp_path / "template.xlsx",
        {"A1": "Invoice No", "C1": "Amount", "F1": "Notes"},
    )

    (row,) = build_outline(path).sheets[0].rows

    assert [(cell.column, cell.value) for cell in row.cells] == [
        ("A", "Invoice No"),
        ("C", "Amount"),
        ("F", "Notes"),
    ]


def test_a_title_banner_above_the_headers_stays_visible(tmp_path):
    # The outline never claims which row holds the headers; the agent
    # decides, and it can only decide if it sees the banner row too.
    path = write_workbook(
        tmp_path / "template.xlsx",
        {"A1": "Quarterly register", "A2": "Invoice No", "B2": "Vendor"},
    )

    rows = build_outline(path).sheets[0].rows

    assert [row.row for row in rows] == [1, 2]
    assert [cell.value for cell in rows[0].cells] == ["Quarterly register"]
    assert [cell.value for cell in rows[1].cells] == ["Invoice No", "Vendor"]


def test_blank_rows_are_dropped_without_renumbering_the_rest(tmp_path):
    path = write_workbook(
        tmp_path / "template.xlsx", {"A1": "Title", "A3": "Invoice No"}
    )

    rows = build_outline(path).sheets[0].rows

    assert [row.row for row in rows] == [1, 3]


def test_only_the_first_rows_are_previewed(tmp_path):
    path = write_workbook(
        tmp_path / "template.xlsx",
        {f"A{number}": f"row {number}" for number in range(1, 10)},
    )

    rows = build_outline(path, preview_rows=3).sheets[0].rows

    assert [row.row for row in rows] == [1, 2, 3]


def test_values_are_stringified(tmp_path):
    path = write_workbook(tmp_path / "template.xlsx", {"A1": 1200, "B1": "Vendor"})

    (row,) = build_outline(path).sheets[0].rows

    assert [cell.value for cell in row.cells] == ["1200", "Vendor"]


def test_a_missing_workbook_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="workbook not found"):
        build_outline(tmp_path / "absent.xlsx")
