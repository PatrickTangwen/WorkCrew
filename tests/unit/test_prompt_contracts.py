from pathlib import Path

PROMPTS = Path(__file__).parents[2] / "src" / "workflow_app" / "prompts"


def prompt(name):
    return (PROMPTS / name).read_text()


def test_filler_keeps_row_folder_identity_and_propagates_conflicts():
    text = prompt("filler.md")

    assert "row-to-folder ledger" in text
    assert "source_file prefix" in text
    assert "Propagate a source conflict" in text


def test_reviewer_prioritizes_risky_cells_and_escalates_uncertainty():
    text = prompt("reviewer.md")

    assert "Risk-order the sample" in text
    assert "A conflict cannot receive PASS" in text
    assert "OCR-confusable" in text


def test_revision_requires_corroboration_before_character_level_changes():
    text = prompt("revision.md")

    assert "character-level evidence gate" in text
    assert "independent corroboration" in text
    assert "choose UNRESOLVED" in text
