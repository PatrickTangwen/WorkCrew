"""Benchmark labels contract (ticket #13, plan section 42).

One labeled field per workbook cell: the expected value, and whether
the correct outcome is a value ("expected"), an empty cell ("blank"),
or an escalation because the sources genuinely conflict
("unresolved"). Evidence expectations are folder-scoped — the dataset
carries no span-level ground truth, so evidence must cite a file from
the row's own source folder.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class FieldLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell: str
    expected_value: Any = None
    status: Literal["expected", "blank", "unresolved"]


class ConflictNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    file: str
    value: str


class RowLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int
    folder: str
    document: str
    conflict: ConflictNote | None = None
    fields: dict[str, FieldLabel]


class BenchmarkLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark: str
    sheet: str
    seed: int
    rows: list[RowLabels]


def load_labels(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"labels file not found: {path}")
    return BenchmarkLabels.model_validate(json.loads(path.read_text()))
