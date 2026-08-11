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


def test_prompt_directory_contains_only_runtime_loaded_prompts():
    mapped = {
        prompt_name
        for prompt_name, _contract in (*CLAUDE_ROLES.values(), *CODEX_ROLES.values())
    }
    present = {path.name for path in PROMPTS.glob("*.md")}

    assert present == mapped


def test_independent_variants_preserve_core_evidence_gates():
    filler = prompt("filler_independent.md")
    reviewer = prompt("reviewer_independent.md")
    revision = prompt("revision_independent.md")

    assert "support test" in filler
    assert "target cell" in filler
    assert 'undated label such as "latest"' in filler
    assert "explicit dates or periods" in filler
    assert "conflict, not a chosen winner" in filler
    assert "verification test" in reviewer
    assert "target ownership" in reviewer
    assert 'undated label such as "latest"' in reviewer
    assert "OCR-confusable character" in reviewer
    assert "replace source evidence" in reviewer
    assert "unqualified A1 address" in reviewer
    assert "never include the sheet" in reviewer
    assert "proof test" in revision
    assert "exact value" in revision
    assert "raw OCR transcription does not prove" in revision
    assert "independent occurrence" in revision
    assert "return `UNRESOLVED`" in revision


def test_independent_reviewer_uses_supplied_rules_for_canonical_forms():
    reviewer = prompt("reviewer_independent.md")

    assert "review_targets" in reviewer
    assert "local rule" in reviewer and "canonical" in reviewer and "form" in reviewer
    assert "declared authority" in reviewer
    assert "exact" in reviewer and "replacement" in reviewer


def test_active_quality_prompts_do_not_name_the_benchmark_domain():
    active = "\n".join(
        prompt(name)
        for name in (
            "filler_independent.md",
            "reviewer_independent.md",
            "revision_independent.md",
        )
    )

    for benchmark_term in (
        "Kleister",
        "Charity Name",
        "Registration Number",
        "Annual Income GBP",
        "Income Size Band",
    ):
        assert benchmark_term not in active


def test_independent_reviewer_keeps_conflicts_open_for_human_judgment():
    reviewer = prompt("reviewer_independent.md")

    assert "conflict proposal remains unresolved" in reviewer.lower()
    assert (
        "blank" in reviewer.lower() and "workbook value is correct" in reviewer.lower()
    )


def test_revision_roles_keep_the_operator_task_and_images_in_scope():
    for name in ("revision_independent.md", "re_review.md"):
        text = prompt(name)
        assert "input/task.md" in text
        assert "attached images" in text.lower()
