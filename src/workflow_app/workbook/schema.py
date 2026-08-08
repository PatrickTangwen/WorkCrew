"""Workbook schema configuration (plan section 16).

V1 uses a manually authored JSON config describing sheets, writable
columns, key fields, controlled vocabularies, and references. No
automatic schema detection. The config is validated on load; a missing
or malformed config fails the run before any agent is invoked.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool = False
    type: Literal[
        "string",
        "number",
        "date",
        "id",
        "controlled_vocabulary",
        "boolean",
    ] = "string"
    writable: bool = False
    key: bool = False
    reference: str | None = None
    values: list[str] | None = None
    pattern: str | None = None
    date_format: str | None = None


class SheetSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: bool = False
    fields: dict[str, FieldSpec] = {}


class WorkbookSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheets: list[SheetSchema] = Field(min_length=1)


def load_workbook_schema(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"workbook schema config not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"workbook schema config is not valid JSON: {path}: {exc}"
        ) from exc
    try:
        return WorkbookSchema.model_validate(data)
    except ValidationError as exc:
        raise ValueError(
            f"workbook schema config failed validation: {path}\n{exc}"
        ) from exc
