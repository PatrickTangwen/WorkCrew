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
    def artifacts(self):
        return self.root / "artifacts"

    @property
    def audit_db(self):
        return self.root / "state" / "audit.sqlite"

    @property
    def manifest_json(self):
        return self.artifacts / "manifest.json"

    @property
    def workbook_schema_json(self):
        return self.artifacts / "workbook_schema.json"

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
