"""Workbook schema configuration (plan section 16).

V1 uses a manually authored JSON config describing sheets, writable
columns, key fields, controlled vocabularies, and references. No
automatic schema detection. The config is validated on load; a missing
or malformed config fails the run before any agent is invoked.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


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
    # Excel column letter; hand-authored (no auto-detection in V1).
    column: str | None = Field(default=None, pattern=r"^[A-Z]+$")
    # Constructed = assembled by naming format; mapped = chosen from a
    # controlled vocabulary or judgment scale. Both cap confidence at
    # medium (ADR 0024). controlled_vocabulary fields are mapped
    # by nature and need no explicit marking.
    value_kind: Literal["constructed", "mapped"] | None = None
    writable: bool = False
    key: bool = False
    reference: str | None = None
    values: list[str] | None = None
    pattern: str | None = None
    date_format: str | None = None
    # Chinese gloss shown under the field name in the ZH review
    # explorer (plan section 22); display-only.
    gloss_zh: str | None = None

    @model_validator(mode="after")
    def _fail_fast_on_unusable_specs(self):
        if self.type == "controlled_vocabulary" and not self.values:
            raise ValueError("controlled_vocabulary field must declare values")
        if self.writable and self.column is None:
            raise ValueError("writable field must declare its column letter")
        return self


class SheetSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: bool = False
    # Field name of this sheet's Notes column; enables note_append
    # companion edits (plan section 28).
    notes_field: str | None = None
    # Display annotations for the review explorer (plan section 22):
    # the field whose value titles a row in navigation and detail
    # pages, and the fields shown as master-table columns.
    title_field: str | None = None
    overview_fields: list[str] = []
    fields: dict[str, FieldSpec] = {}

    @model_validator(mode="after")
    def _named_fields_must_exist(self):
        for label in ("notes_field", "title_field"):
            name = getattr(self, label)
            if name is not None and name not in self.fields:
                raise ValueError(f"{label} {name!r} is not a declared field")
        for name in self.overview_fields:
            if name not in self.fields:
                raise ValueError(
                    f"overview_fields entry {name!r} is not a declared field"
                )
        return self

    @model_validator(mode="after")
    def _columns_must_be_unique(self):
        seen = {}
        for header, field in self.fields.items():
            if field.column is None:
                continue
            if field.column in seen:
                raise ValueError(
                    f"column {field.column!r} is declared by both"
                    f" {seen[field.column]!r} and {header!r}"
                )
            seen[field.column] = header
        return self

    def field_for_column(self, column):
        for header, field in self.fields.items():
            if field.column == column:
                return header, field
        return None, None


class WorkbookSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheets: list[SheetSchema] = Field(min_length=1)

    def sheet_named(self, name):
        for sheet in self.sheets:
            if sheet.name == name:
                return sheet
        return None

    def target_sheet(self):
        (sheet,) = [sheet for sheet in self.sheets if sheet.target]
        return sheet

    @model_validator(mode="after")
    def _exactly_one_target_sheet(self):
        targets = [sheet.name for sheet in self.sheets if sheet.target]
        if len(targets) != 1:
            raise ValueError(
                f"exactly one target sheet is required in V1, found {targets}"
            )
        return self


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
