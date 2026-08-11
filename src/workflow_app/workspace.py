"""Per-run workspace layout (plan sections 12, 35).

Every run gets an isolated directory under the runs root. Inputs are
copied in untouched; original files are never modified. The finished
run's deliverables are additionally exported into the operator's source
folder, under OUTPUT_DIR_NAME (ADR 0035).
"""

import filecmp
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

# Deliverables are exported to <source>/<OUTPUT_DIR_NAME>/<run_id>/, so
# the operator finds the results beside the documents they came from.
OUTPUT_DIR_NAME = "workcrew-output"
EXPORT_RESERVATION_DIR_NAME = ".reservations"


def validate_task_and_rules(task, rules_text, rules_file):
    if not task.strip():
        raise ValueError("task description must not be empty")
    if rules_text is not None and rules_file is not None:
        raise ValueError("rules may be given as text or as a file, not both")


# Clipboard images arrive as content, not as files on the operator's
# disk, so they are materialized once — into the run workspace.
@dataclass(frozen=True)
class TaskImage:
    suffix: str
    data: bytes


IMAGE_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
IMAGE_FILE_SUFFIXES = frozenset((*IMAGE_SUFFIXES.values(), ".jpeg"))


@dataclass(frozen=True)
class RunInputs:
    source: Path
    workbook: Path
    # The operator's natural-language description of the job. The scoping
    # pass derives the workbook schema from it (ADR 0032), so it is a
    # required input rather than an optional hint.
    task: str
    # Optional operator-chosen name for the run. It names the run id and
    # nothing else; unset, the source folder names the run.
    name: str | None = None
    # Screenshots and diagrams that belong to the task description —
    # what the operator pasted beside their own words (ADR 0037).
    task_images: tuple = ()
    # Optional extraction rules, given either as prose or as one text
    # file. At most one of the two is set; both unset means the run has
    # no rules beyond the task itself.
    rules_text: str | None = None
    rules_file: Path | None = None
    # Optional pre-provided scoping answers (plan section 20): when set,
    # the scoping pause is skipped. The scoping pass itself always runs —
    # it produces the schema.
    scoping_answers: Path | None = None
    # Optional review policy YAML (plan section 25): when unset, the
    # default policy applies.
    review_policy: Path | None = None

    def validate(self):
        if not self.source.is_dir():
            raise FileNotFoundError(f"source folder not found: {self.source}")
        if not self.workbook.is_file():
            raise FileNotFoundError(f"workbook not found: {self.workbook}")
        validate_task_and_rules(self.task, self.rules_text, self.rules_file)
        if self.rules_file is not None and not self.rules_file.is_file():
            raise FileNotFoundError(f"rules file not found: {self.rules_file}")
        if self.scoping_answers is not None and not self.scoping_answers.is_file():
            raise FileNotFoundError(
                f"scoping answers file not found: {self.scoping_answers}"
            )
        if self.review_policy is not None and not self.review_policy.is_file():
            raise FileNotFoundError(
                f"review policy file not found: {self.review_policy}"
            )

    def resolved(self):
        """Pin filesystem inputs so checkpoints survive a changed cwd."""
        return replace(
            self,
            source=self.source.resolve(),
            workbook=self.workbook.resolve(),
            rules_file=None if self.rules_file is None else self.rules_file.resolve(),
            scoping_answers=None
            if self.scoping_answers is None
            else self.scoping_answers.resolve(),
            review_policy=None
            if self.review_policy is None
            else self.review_policy.resolve(),
        )


SUBDIRS = (
    "input/sources",
    "input/rules",
    "input/workbook",
    "input/task_images",
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
    def task_md(self):
        return self.root / "input" / "task.md"

    @property
    def task_images_dir(self):
        return self.root / "input" / "task_images"

    def task_image_paths(self):
        """The task's images, in the order the operator pasted them."""
        return sorted(
            (
                path
                for path in self.task_images_dir.glob("task-image-*")
                if path.is_file()
            ),
            key=lambda path: int(path.stem.removeprefix("task-image-")),
        )

    @property
    def agents_json(self):
        # The model and effort each role ran with. A resume is a fresh
        # process, so the run has to carry its own configuration.
        return self.root / "input" / "agents.json"

    @property
    def rules_md(self):
        return self.input_rules / "rules.md"

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
    def events_jsonl(self):
        # The run's progress stream, one JSON event per line, in the order
        # the engine emitted them. The websocket only reaches whoever is
        # watching at the time; this is what a run can be reopened on.
        return self.root / "state" / "events.jsonl"

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
    def review_policy_yaml(self):
        return self.root / "input" / "review_policy.yaml"

    @property
    def review_policy_json(self):
        return self.artifacts / "review_policy.json"

    @property
    def workbook_outline_json(self):
        return self.artifacts / "workbook_outline.json"

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
        shutil.copytree(
            inputs.source,
            self.input_sources,
            dirs_exist_ok=True,
            ignore=_ignore_exported_output(inputs.source),
        )
        shutil.copy2(inputs.workbook, self.input_workbook / inputs.workbook.name)
        # Numbered by paste order, named by the workspace rather than by
        # the clipboard: a pasted image carries no trustworthy file name.
        images = []
        for index, image in enumerate(inputs.task_images, start=1):
            path = self.task_images_dir / f"task-image-{index}{image.suffix}"
            path.write_bytes(image.data)
            images.append(path.relative_to(self.root))
        self.task_md.write_text(render_task_md(inputs.task, images))
        # Prose and file rules land in the same place, so every later
        # stage reads rules from one path and never learns which form
        # the operator chose. No rules at all leaves input/rules/ empty.
        if inputs.rules_text is not None:
            self.rules_md.write_text(inputs.rules_text)
        elif inputs.rules_file is not None:
            shutil.copy2(inputs.rules_file, self.rules_md)
        if inputs.scoping_answers is not None:
            shutil.copy2(inputs.scoping_answers, self.scoping_answers_md)
        if inputs.review_policy is not None:
            shutil.copy2(inputs.review_policy, self.review_policy_yaml)

    @staticmethod
    def _export_root(source):
        source = Path(source).resolve(strict=True)
        if not source.is_dir():
            raise NotADirectoryError(
                f"source folder is no longer a directory: {source}"
            )
        output_root = source / OUTPUT_DIR_NAME
        if output_root.is_symlink():
            raise ValueError(
                f"deliverable export root must not be a symlink: {output_root}"
            )
        output_root.mkdir(exist_ok=True)
        return output_root

    def reserve_export(self, source, run_id, *, allow_existing=False):
        """Atomically reserve a source-side run id for this workspace."""
        output_root = self._export_root(source)
        reservations = output_root / EXPORT_RESERVATION_DIR_NAME
        if reservations.is_symlink():
            raise ValueError(
                f"deliverable reservation root must not be a symlink: {reservations}"
            )
        reservations.mkdir(exist_ok=True)
        marker = reservations / run_id
        owner = str(self.root.resolve())
        created = False
        try:
            with marker.open(
                "x", encoding="utf-8", errors="strict", newline="\n"
            ) as file:
                file.write(owner)
        except FileExistsError:
            if not allow_existing or marker.read_text() != owner:
                raise FileExistsError(
                    f"deliverable export id is already reserved: {run_id}"
                ) from None
        else:
            created = True

        destination = output_root / run_id
        if (destination.exists() or destination.is_symlink()) and (
            not allow_existing or created or destination.is_symlink()
        ):
            if created:
                marker.unlink()
            raise FileExistsError(f"deliverable export already exists: {destination}")
        return marker

    def export_deliverables(self, source, run_id, artifacts):
        """Copy this run's public artifacts into the source folder.

        The reservation proves that an existing partial directory belongs
        to this workspace. Files are assembled beside the reservation and
        renamed into place, so a copy failure never exposes a half-built
        final directory. A retry also recognizes the crash window after
        the rename but before the reservation marker was removed.
        """
        marker = self.reserve_export(source, run_id, allow_existing=True)
        output_root = self._export_root(source)
        destination = output_root / run_id
        artifacts = list(artifacts)

        if destination.exists():
            if not destination.is_dir() or destination.is_symlink():
                raise FileExistsError(
                    f"deliverable export already exists: {destination}"
                )
            existing = {path.name: path for path in destination.iterdir()}
            expected = {artifact.name: artifact for artifact in artifacts}
            complete = existing.keys() == expected.keys() and all(
                path.is_file()
                and not path.is_symlink()
                and filecmp.cmp(path, expected[name], shallow=False)
                for name, path in existing.items()
            )
            if complete:
                marker.unlink()
                return destination
            shutil.rmtree(destination)

        staging = marker.parent / f"{run_id}.partial"
        if staging.is_symlink():
            raise ValueError(
                f"deliverable export staging must not be a symlink: {staging}"
            )
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
            for artifact in artifacts:
                shutil.copy2(artifact, staging / artifact.name)
            staging.rename(destination)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        marker.unlink()
        return destination


def render_task_md(task, images):
    """The operator's words, plus a pointer to what they pasted with them.

    Agents read `input/task.md` as the statement of intent, so the images
    have to be named there — an image nobody is told to open is an image
    nobody reads.
    """
    if not images:
        return task
    listed = "\n".join(f"- `{image}`" for image in images)
    return (
        f"{task.rstrip()}\n\n## Attached images\n\n"
        "The operator pasted these with the task description; read them as"
        f" part of it.\n\n{listed}\n"
    )


def _ignore_exported_output(source):
    # A second run on the same source folder must not ingest the first
    # run's deliverables as source documents. Only the export directory
    # at the source root is skipped; a directory of the same name deeper
    # in the tree is the operator's own and is copied.
    root = Path(source).resolve()

    def ignore(directory, names):
        if Path(directory).resolve() != root:
            return set()
        return {name for name in names if name == OUTPUT_DIR_NAME}

    return ignore
