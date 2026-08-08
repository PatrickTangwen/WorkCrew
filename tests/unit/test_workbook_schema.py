"""Workbook schema config tests (ticket #3, plan section 16).

The hand-authored config is validated on load; malformed or missing
configs fail with a clear error.
"""

import json

import pytest

from workflow_app.workbook.schema import load_workbook_schema

VALID_CONFIG = {
    "sheets": [
        {
            "name": "7) Practicum Courses",
            "target": True,
            "fields": {
                "Project ID*": {
                    "required": True,
                    "type": "id",
                    "reference": "6) Engagement Projects",
                    "writable": True,
                    "key": True,
                },
                "Main Issue Area(s)": {
                    "type": "controlled_vocabulary",
                    "reference": "Main Issue Area Codes.Standardized Format",
                    "values": ["Healthcare", "Education", "Environment"],
                    "writable": True,
                },
                "Notes": {"type": "string", "writable": True},
            },
        },
        {"name": "Main Issue Area Codes"},
    ]
}


def write_config(tmp_path, data):
    path = tmp_path / "workbook_schema.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def test_valid_config_loads(tmp_path):
    schema = load_workbook_schema(write_config(tmp_path, VALID_CONFIG))

    sheet = schema.sheets[0]
    assert sheet.name == "7) Practicum Courses"
    assert sheet.target is True
    project_id = sheet.fields["Project ID*"]
    assert project_id.required and project_id.writable and project_id.key
    issue_area = sheet.fields["Main Issue Area(s)"]
    assert issue_area.type == "controlled_vocabulary"
    assert "Healthcare" in issue_area.values
    # Reference sheets need no fields.
    assert schema.sheets[1].fields == {}


def test_missing_config_raises_with_path(tmp_path):
    missing = tmp_path / "absent.json"
    with pytest.raises(FileNotFoundError, match="absent.json"):
        load_workbook_schema(missing)


def test_invalid_json_raises_clear_error(tmp_path):
    path = write_config(tmp_path, "{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_workbook_schema(path)


def test_unknown_field_type_is_rejected(tmp_path):
    config = json.loads(json.dumps(VALID_CONFIG))
    config["sheets"][0]["fields"]["Project ID*"]["type"] = "telepathy"
    with pytest.raises(ValueError, match="failed validation"):
        load_workbook_schema(write_config(tmp_path, config))


def test_unexpected_keys_are_rejected(tmp_path):
    config = json.loads(json.dumps(VALID_CONFIG))
    config["sheets"][0]["surprise"] = True
    with pytest.raises(ValueError, match="failed validation"):
        load_workbook_schema(write_config(tmp_path, config))


def test_empty_sheet_list_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="failed validation"):
        load_workbook_schema(write_config(tmp_path, {"sheets": []}))
