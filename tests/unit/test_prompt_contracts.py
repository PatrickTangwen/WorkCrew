from pathlib import Path

PROMPTS = Path(__file__).parents[2] / "src" / "workflow_app" / "prompts"


def prompt(name):
    return (PROMPTS / name).read_text()


def test_filler_keeps_row_folder_identity_and_propagates_conflicts():
    text = prompt("filler.md")

    assert "row-to-folder ledger" in text
    assert "source_file prefix" in text
    assert "Propagate a source conflict" in text


def test_filler_requires_explicit_period_evidence_before_dismissing_conflict():
    text = prompt("filler.md")

    assert "Do not invent a temporal distinction" in text
    assert "explicit dates or reporting periods" in text
    assert "`conflict` status" in text


def test_filler_uses_categorical_confidence_and_null_for_uncertainty():
    text = prompt("filler.md")

    assert '`"low"` | `"medium"` | `"high"`' in text
    assert "confidence: null" in text
    assert "capped at `medium`" in text
    assert "0.60" not in text
    assert "0.85" not in text


def test_reviewer_prioritizes_risky_cells_and_escalates_uncertainty():
    text = prompt("reviewer.md")

    assert "Risk-order the sample" in text
    assert "A conflict cannot receive PASS" in text
    assert "OCR-confusable" in text


def test_reviewer_applies_conflict_rules_at_their_stated_file_scope():
    text = prompt("reviewer.md")

    assert "Apply each conflict rule only at its stated scope" in text
    assert "separate source files" in text
    assert "does not by itself trigger that cross-document rule" in text


def test_reviewer_routes_categories_without_numeric_thresholds():
    text = prompt("reviewer.md")

    assert "Every `low`-confidence proposal" in text
    assert "Every `medium`-confidence proposal" in text
    assert "For `high`-confidence proposals" in text
    assert "low_confidence_threshold" not in text
    assert "medium_confidence_threshold" not in text


def test_revision_requires_corroboration_before_character_level_changes():
    text = prompt("revision.md")

    assert "character-level evidence gate" in text
    assert "independent corroboration" in text
    assert "choose UNRESOLVED" in text
