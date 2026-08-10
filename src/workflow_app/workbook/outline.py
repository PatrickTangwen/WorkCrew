"""Deterministic workbook outline (ADR 0032).

The scoping pass derives the workbook schema, but sheet names, column
letters, and the text sitting in the top rows are facts about the file
rather than judgments. Reading them here leaves the agent one job:
deciding which row holds the headers and what each column means. The
outline never names a header row itself — a template with a title
banner above its headers would make that guess wrong, and the agent
has the rows in front of it either way.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workflow_app.workbook import writer

PREVIEW_ROWS = 5


class CellOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    value: str


class RowOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int
    cells: list[CellOutline]


class SheetOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rows: list[RowOutline]


class WorkbookOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheets: list[SheetOutline]


def build_outline(path, preview_rows=PREVIEW_ROWS):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"workbook not found: {path}")
    workbook = writer.open_template(path)
    return WorkbookOutline(
        sheets=[
            SheetOutline(name=name, rows=_rows_of(workbook, name, preview_rows))
            for name in writer.sheet_names(workbook)
        ]
    )


def _rows_of(workbook, sheet, preview_rows):
    return [
        RowOutline(
            row=number,
            cells=[CellOutline(column=column, value=value) for column, value in cells],
        )
        for number, cells in enumerate(
            writer.preview_rows(workbook, sheet, preview_rows), start=1
        )
        if cells
    ]
