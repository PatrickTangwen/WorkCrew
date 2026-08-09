"""Per-run workspace layout (plan sections 12, 35).

Every run gets an isolated directory under the runs root. Inputs are
copied in untouched; original files are never modified.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunInputs:
    source: Path
    workbook: Path
    rules: Path
    workbook_schema: Path
    # Optional pre-provided scoping answers (plan section 20): when set,
    # the scoping pass and its pause are skipped.
    scoping_answers: Path | None = None

    def validate(self):
        if not self.source.is_dir():
            raise FileNotFoundError(f"source folder not found: {self.source}")
        if not self.workbook.is_file():
            raise FileNotFoundError(f"workbook not found: {self.workbook}")
        if not self.rules.is_dir():
            raise FileNotFoundError(f"rules folder not found: {self.rules}")
        if not self.workbook_schema.is_file():
            raise FileNotFoundError(
                f"workbook schema config not found: {self.workbook_schema}"
            )
        if self.scoping_answers is not None and not self.scoping_answers.is_file():
            raise FileNotFoundError(
                f"scoping answers file not found: {self.scoping_answers}"
            )


SUBDIRS = (
    "input/sources",
    "input/rules",
    "input/workbook",
    "working",
    "agent_outputs/filler",
    "agent_outputs/reviewer",
    "agent_outputs/revision",
    "artifacts",
    "output",
    "state",
    "logs",
)


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def input_sources(self):
        return self.root / "input" / "sources"

    @property
    def input_rules(self):
        return self.root / "input" / "rules"

    @property
    def input_workbook(self):
        return self.root / "input" / "workbook"

    @property
    def filler_outputs(self):
        return self.root / "agent_outputs" / "filler"

    @property
    def reviewer_outputs(self):
        return self.root / "agent_outputs" / "reviewer"

    @property
    def revision_outputs(self):
        return self.root / "agent_outputs" / "revision"

    @property
    def artifacts(self):
        return self.root / "artifacts"

    @property
    def audit_db(self):
        return self.root / "state" / "audit.sqlite"

    @property
    def checkpoint_db(self):
        return self.root / "state" / "checkpoints.sqlite"

    @property
    def manifest_json(self):
        return self.artifacts / "manifest.json"

    @property
    def scoping_questions_json(self):
        return self.artifacts / "scoping_questions.json"

    @property
    def scoping_questions_md(self):
        return self.artifacts / "scoping_questions.md"

    @property
    def scoping_answers_md(self):
        return self.artifacts / "scoping_answers.md"

    @property
    def workbook_schema_json(self):
        return self.artifacts / "workbook_schema.json"

    @property
    def extraction_json(self):
        return self.artifacts / "extraction.json"

    @property
    def validation_json(self):
        return self.artifacts / "validation.json"

    @property
    def provenance_json(self):
        return self.artifacts / "provenance.json"

    @property
    def handoff_json(self):
        return self.artifacts / "handoff.json"

    @property
    def handoff_md(self):
        return self.artifacts / "handoff.md"

    @property
    def review_explorer_html(self):
        return self.artifacts / "review_explorer.html"

    @property
    def review_explorer_zh_html(self):
        return self.artifacts / "review_explorer_zh.html"

    @property
    def review_explorer_v2_html(self):
        return self.artifacts / "review_explorer_v2.html"

    @property
    def review_explorer_zh_v2_html(self):
        return self.artifacts / "review_explorer_zh_v2.html"

    @property
    def review_json(self):
        return self.artifacts / "review.json"

    @property
    def review_md(self):
        return self.artifacts / "review.md"

    @property
    def revision_json(self):
        return self.artifacts / "revision.json"

    @property
    def revision_log_md(self):
        return self.artifacts / "revision_log.md"

    @property
    def re_review_json(self):
        return self.artifacts / "re_review.json"

    @property
    def unresolved_json(self):
        return self.artifacts / "unresolved.json"

    @property
    def human_review_json(self):
        return self.artifacts / "human_review.json"

    @property
    def human_review_md(self):
        return self.artifacts / "human_review.md"

    @property
    def draft_xlsx(self):
        return self.root / "working" / "draft.xlsx"

    @property
    def final_xlsx(self):
        return self.root / "output" / "final.xlsx"

    @property
    def run_summary(self):
        return self.artifacts / "run_summary.md"

    def create_layout(self):
        for subdir in SUBDIRS:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)

    def copy_inputs(self, inputs):
        shutil.copytree(inputs.source, self.input_sources, dirs_exist_ok=True)
        shutil.copytree(inputs.rules, self.input_rules, dirs_exist_ok=True)
        shutil.copy2(inputs.workbook, self.input_workbook / inputs.workbook.name)
        if inputs.scoping_answers is not None:
            shutil.copy2(inputs.scoping_answers, self.scoping_answers_md)
