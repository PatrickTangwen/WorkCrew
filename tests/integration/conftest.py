import json

import pytest

WORKBOOK_SCHEMA_CONFIG = {
    "sheets": [
        {
            "name": "7) Practicum Courses",
            "target": True,
            "fields": {
                "Project ID*": {"required": True, "type": "id", "writable": True},
                "Main Issue Area(s)": {
                    "type": "controlled_vocabulary",
                    "values": ["Healthcare", "Education"],
                    "writable": True,
                },
            },
        }
    ]
}


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source_documents"
    (source / "India 2008").mkdir(parents=True)
    (source / "India 2008" / "Project_Brief.txt").write_text(
        "Community healthcare delivery project."
    )
    (source / "archive_notes.md").write_text("Top-level archive notes.")

    workbook = tmp_path / "template.xlsx"
    workbook.write_bytes(b"placeholder workbook bytes")

    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "naming.md").write_text("Naming conventions.")

    workbook_schema = tmp_path / "workbook_schema.json"
    workbook_schema.write_text(json.dumps(WORKBOOK_SCHEMA_CONFIG))

    return {
        "source": source,
        "workbook": workbook,
        "rules": rules,
        "workbook_schema": workbook_schema,
        "runs_root": tmp_path / "runs",
    }
