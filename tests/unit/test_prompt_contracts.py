from pathlib import Path

from workflow_app.runtimes.claude_code import ROLES as CLAUDE_ROLES
from workflow_app.runtimes.codex import ROLES as CODEX_ROLES

PROMPTS = Path(__file__).parents[2] / "src" / "workflow_app" / "prompts"


def prompt(name):
    return (PROMPTS / name).read_text()


def test_live_quality_roles_use_independent_prompt_variants():
    assert CLAUDE_ROLES["filler"][0] == "filler_independent.md"
    assert CODEX_ROLES["reviewer"][0] == "reviewer_independent.md"
    assert CLAUDE_ROLES["revision"][0] == "revision_independent.md"


def test_independent_variants_preserve_core_evidence_gates():
    filler = prompt("filler_independent.md")
    reviewer = prompt("reviewer_independent.md")
    revision = prompt("revision_independent.md")

    assert "support test" in filler
    assert "target cell" in filler
    assert "conflict, not a chosen winner" in filler
    assert "verification test" in reviewer
    assert "target ownership" in reviewer
    assert "replace source evidence" in reviewer
    assert "unqualified A1 address" in reviewer
    assert "never include the sheet" in reviewer
    assert "proof test" in revision
    assert "exact value" in revision
    assert "return `UNRESOLVED`" in revision


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
