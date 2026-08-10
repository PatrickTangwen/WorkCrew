"""openpyxl isolation layer (plan section 14, bottom of the boundary).

The only module that imports openpyxl. Loading keeps formulas as
formulas (data_only=False default), so untouched cells survive
save/reopen exactly.
"""

import re

from openpyxl import load_workbook

# A1-style single-cell reference: 1-3 column letters + positive row.
_CELL_REF = re.compile(r"^([A-Za-z]{1,3})([1-9]\d*)$")

MAX_ROW = 1_048_576
MAX_COLUMN = "XFD"


def normalize_cell(cell):
    match = _CELL_REF.fullmatch(cell or "")
    if match is None:
        return None
    column, row = match.group(1).upper(), int(match.group(2))
    if row > MAX_ROW:
        return None
    if len(column) == len(MAX_COLUMN) and column > MAX_COLUMN:
        return None
    return f"{column}{row}"


def column_of(cell_ref):
    return _CELL_REF.fullmatch(cell_ref).group(1).upper()


def row_of(cell_ref):
    return int(_CELL_REF.fullmatch(cell_ref).group(2))


def open_draft(path):
    return load_workbook(path)


def save_draft(workbook, path):
    workbook.save(path)


def open_template(path):
    # Read side of open_draft: the template is never saved back.
    return load_workbook(path)


def has_sheet(workbook, name):
    return name in workbook.sheetnames


def sheet_names(workbook):
    return list(workbook.sheetnames)


def preview_rows(workbook, sheet, limit):
    """Column letter and text of every non-empty cell in the first rows."""
    return [
        [
            (cell.column_letter, str(cell.value).strip())
            for cell in cells
            if cell.value is not None and str(cell.value).strip()
        ]
        for cells in workbook[sheet].iter_rows(min_row=1, max_row=limit)
    ]


def read_cell(workbook, sheet, cell_ref):
    return workbook[sheet][cell_ref].value


def max_row(workbook, sheet):
    return workbook[sheet].max_row


def write_cell(workbook, sheet, cell_ref, value):
    workbook[sheet][cell_ref] = value
