import pytest


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

    return {
        "source": source,
        "workbook": workbook,
        "rules": rules,
        "runs_root": tmp_path / "runs",
    }
