"""CLI entry (plan section 4): `workflow run`, `resume`, `evaluate`,
and `build-benchmark`.

A thin shell over the engine — no business logic here. Runs use the
live agent runtimes by default (Claude Code for scoping/fill/revision,
Codex for review/re-review); `--runtimes fake` replays the degenerate
walking-skeleton fixtures instead, for wiring checks and tests that
must not spend agent quota (plan section 32). `build-benchmark` and
`evaluate` are the plan-section-42 benchmark pipeline: build inputs
from a Kleister-Charity split, score a completed run against the
labels, and optionally record the result as a baseline.
"""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

from workflow_app.agent_config import (
    CLAUDE,
    CODEX,
    DEFAULT_EFFORTS,
    DEFAULT_MODELS,
    EFFORT_CHOICES,
    ROLE_RUNTIMES,
    build_agent_config,
    default_agent_config,
    read_agent_config,
)
from workflow_app.benchmark.kleister import build_benchmark
from workflow_app.evaluation.evaluate import evaluate_run
from workflow_app.evaluation.labels import load_labels
from workflow_app.evaluation.report import format_metric, render_evaluation_md
from workflow_app.progress import emit
from workflow_app.runtimes.claude_code import ClaudeCodeRuntime
from workflow_app.runtimes.codex import CodexRuntime
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import DEFAULT_UI_PORT, run_ui
from workflow_app.workbook.outline import build_outline
from workflow_app.workflow.engine import resume_workflow, run_workflow
from workflow_app.workspace import (
    IMAGE_FILE_SUFFIXES,
    RunInputs,
    TaskImage,
    Workspace,
)

# Degenerate walking-skeleton payloads: one placeholder scoping
# question, an empty fill, and an all-clear review, so a pure fake run
# short-circuits to FINALIZE. The revision/re-review fixtures cover a
# live run resumed with --runtimes fake (runtime choice is
# per-invocation, ADR 0019): zero decisions and zero verdicts degrade
# every open finding into the UNRESOLVED / human-review pipeline.
FAKE_OUTPUTS = {
    # Two rounds: one question, then nothing left to ask. A single step
    # would repeat its question every round and stall the run at the
    # pause until the round cap. workbook_schema is filled in per
    # invocation by fake_scoping_schema() — the target sheet must name a
    # sheet the operator's workbook actually has, and the fake fill
    # proposes nothing, so no column ever needs declaring.
    "scoping": [
        {
            "questions": [
                {
                    "id": "Q1",
                    "question": (
                        "Confirm the source folders are the complete set to process."
                    ),
                }
            ]
        },
        {"questions": []},
    ],
    "filler": {"proposals": []},
    "reviewer": {"findings": []},
    "revision": {"decisions": []},
    "re_review": {"verdicts": []},
}


# Models and effort are product configuration (ADR 0020), now per role
# and shared with the server (ADR 0036); workflow_app.agent_config owns
# the defaults and vocabularies these flags resolve against.
DEFAULT_CLAUDE_MODEL = DEFAULT_MODELS[CLAUDE]
DEFAULT_CODEX_MODEL = DEFAULT_MODELS[CODEX]
DEFAULT_CODEX_EFFORT = DEFAULT_EFFORTS[CODEX]
CLAUDE_EFFORT_CHOICES = EFFORT_CHOICES[CLAUDE]
SUPPORTED_IMAGE_SUFFIXES = IMAGE_FILE_SUFFIXES
CODEX_EFFORT_CHOICES = EFFORT_CHOICES[CODEX]


def role_setting(value):
    """Parse a `role=value` per-role override."""
    role, separator, setting = value.partition("=")
    if not separator or not role or not setting:
        raise argparse.ArgumentTypeError(
            f"expected role=value, got {value!r}; roles are {sorted(ROLE_RUNTIMES)}"
        )
    if role not in ROLE_RUNTIMES:
        raise argparse.ArgumentTypeError(
            f"unknown role {role!r}; roles are {sorted(ROLE_RUNTIMES)}"
        )
    return role, setting


def agent_config_from_args(args, base=None):
    """Runtime-wide flags first, then per-role overrides on top.

    Unset flags leave `base` alone — the product defaults for a new run,
    the run's recorded config for a resume.
    """
    selections = {
        role: {
            "model": args.claude_model if runtime == CLAUDE else args.codex_model,
            "effort": args.claude_effort if runtime == CLAUDE else args.codex_effort,
        }
        for role, runtime in ROLE_RUNTIMES.items()
    }
    for role, model in getattr(args, "agent_model", None) or []:
        selections[role]["model"] = model
    for role, effort in getattr(args, "agent_effort", None) or []:
        selections[role]["effort"] = effort
    return build_agent_config(selections, base=base)


def read_task_images(paths):
    """Task images given as files, in the order the operator listed them."""
    images = []
    for raw in paths or []:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(
                f"unsupported task image {path};"
                f" supported suffixes are {sorted(SUPPORTED_IMAGE_SUFFIXES)}"
            )
        if not path.is_file():
            raise FileNotFoundError(f"task image not found: {path}")
        images.append(TaskImage(suffix=suffix, data=path.read_bytes()))
    return tuple(images)


def recorded_agent_config(args):
    """The agent config a run was started with, for `resume`."""
    if args.command != "resume":
        return None
    return read_agent_config(Workspace(Path(args.runs_root) / args.run_id).agents_json)


def ui_port(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "port must be an integer from 1 to 65535"
        ) from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535")
    return port


def fake_scoping_schema(workbook):
    # A degenerate schema is still checked against the real workbook
    # (the target sheet must exist), so read the first sheet's name.
    outline = build_outline(workbook)
    return {"sheets": [{"name": outline.sheets[0].name, "target": True}]}


def fake_workbook_for(args):
    # The fake scoping fixture needs the workbook to name a real sheet.
    # `run` is given it directly; `resume` finds the workspace copy.
    if getattr(args, "workbook", None) is not None:
        return Path(args.workbook)
    run_id = getattr(args, "run_id", None)
    if run_id is None:
        return None
    copies = sorted((Path(args.runs_root) / run_id / "input" / "workbook").glob("*"))
    return copies[0] if copies else None


def build_runtimes(choice, agents=None, workbook=None, resuming=False):
    """Agent runtimes per role, built from the run's agent config."""
    if choice == "fake":
        emit("Using fake agent runtimes (walking-skeleton fixtures).")
        outputs = deepcopy(FAKE_OUTPUTS)
        if resuming:
            # A resume is a fresh process, so the sequence would restart
            # and ask the same question forever. The pause already
            # happened in the run that created this workspace.
            outputs["scoping"] = outputs["scoping"][1:]
        if workbook is not None:
            schema = fake_scoping_schema(workbook)
            for step in outputs["scoping"]:
                step["workbook_schema"] = schema
        fake = FakeAgentRuntime(outputs)
        return {role: fake for role in outputs}

    config = agents or default_agent_config()
    # Roles sharing a runtime, model and effort share one adapter, so an
    # unchanged config still constructs (and announces) two adapters.
    built, runtimes = {}, {}
    for role, choice_for_role in config.items():
        emit(
            f"{role}: {choice_for_role.runtime} {choice_for_role.model}"
            f" (reasoning effort: {choice_for_role.effort or 'CLI default'})"
        )
        key = (choice_for_role.runtime, choice_for_role.model, choice_for_role.effort)
        if key not in built:
            built[key] = _live_runtime(choice_for_role)
        runtimes[role] = built[key]
    return runtimes


def _live_runtime(choice):
    if choice.runtime == CLAUDE:
        return ClaudeCodeRuntime(model=choice.model, effort=choice.effort)
    return CodexRuntime(model=choice.model, effort=choice.effort)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="workflow",
        description="Local-first document-to-workbook workflow engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ui = subparsers.add_parser("ui", help="start the local WorkCrew web UI")
    ui.add_argument(
        "--port",
        type=ui_port,
        default=DEFAULT_UI_PORT,
        help=f"starting TCP port (default: {DEFAULT_UI_PORT})",
    )

    run = subparsers.add_parser("run", help="start a new workflow run")
    run.add_argument("--source", required=True, help="source documents folder")
    run.add_argument("--workbook", required=True, help="target workbook file")
    run.add_argument(
        "--task",
        required=True,
        help="what the run should accomplish, in your own words;"
        " the scoping pass derives the workbook schema from it",
    )
    run.add_argument(
        "--name",
        help="name this run; it leads the run id (default: the source folder name)",
    )
    run.add_argument(
        "--task-image",
        action="append",
        metavar="PATH",
        help="image belonging to the task description (png/jpeg/gif/webp);"
        " repeatable, order preserved",
    )
    rules = run.add_mutually_exclusive_group()
    rules.add_argument("--rules-text", help="extraction rules as prose")
    rules.add_argument("--rules-file", help="extraction rules as one text file")
    run.add_argument(
        "--scoping-answers",
        help="pre-provided scoping answers file (skips the scoping pause)",
    )
    run.add_argument(
        "--review-policy",
        help="review policy YAML (default: built-in policy)",
    )
    run.add_argument(
        "--runs-root",
        default="runs",
        help="directory holding per-run workspaces (default: ./runs)",
    )

    resume = subparsers.add_parser("resume", help="resume a paused workflow run")
    resume.add_argument(
        "--run-id", required=True, help="run id printed when the run paused"
    )
    resume.add_argument(
        "--runs-root",
        default="runs",
        help="directory holding per-run workspaces (default: ./runs)",
    )
    evaluate = subparsers.add_parser(
        "evaluate", help="score a completed run against benchmark labels"
    )
    evaluate.add_argument(
        "--run-id", required=True, help="id of the completed run to score"
    )
    evaluate.add_argument(
        "--runs-root",
        default="runs",
        help="directory holding per-run workspaces (default: ./runs)",
    )
    evaluate.add_argument("--labels", required=True, help="benchmark labels.json file")
    evaluate.add_argument(
        "--record-baseline",
        help="also copy evaluation.json to this path as the recorded baseline",
    )

    build = subparsers.add_parser(
        "build-benchmark",
        help="build the Kleister-Charity benchmark inputs from a dataset split",
    )
    build.add_argument(
        "--split-dir",
        required=True,
        help="dataset split directory holding in.tsv(.xz) and expected.tsv",
    )
    build.add_argument(
        "--output", required=True, help="directory to write the benchmark inputs to"
    )

    for subparser in (run, resume):
        subparser.add_argument(
            "--runtimes",
            choices=("live", "fake"),
            default="live",
            help=(
                "agent runtimes: live CLIs (default) or the fake"
                " walking-skeleton fixtures"
            ),
        )
        # These default to None, not to the product default: an
        # unflagged resume continues on the models the run recorded,
        # while an explicit flag overrides them (runtime choice is
        # per-invocation, ADR 0019).
        subparser.add_argument(
            "--claude-model",
            help=(
                "model for the Claude roles (scoping/fill/revision);"
                f" a [1m] suffix selects 1M context (default: {DEFAULT_CLAUDE_MODEL})"
            ),
        )
        subparser.add_argument(
            "--codex-model",
            help=(
                "model for the Codex roles (review/re-review)"
                f" (default: {DEFAULT_CODEX_MODEL})"
            ),
        )
        subparser.add_argument(
            "--claude-effort",
            choices=CLAUDE_EFFORT_CHOICES,
            help="Claude reasoning effort for the Claude roles"
            " (default: the CLI's own)",
        )
        subparser.add_argument(
            "--codex-effort",
            choices=CODEX_EFFORT_CHOICES,
            help=(
                "Codex reasoning effort for the review roles"
                f" (default: {DEFAULT_CODEX_EFFORT})"
            ),
        )
        subparser.add_argument(
            "--agent-model",
            action="append",
            type=role_setting,
            metavar="ROLE=MODEL",
            help="model for one role, overriding the runtime-wide flag; repeatable",
        )
        subparser.add_argument(
            "--agent-effort",
            action="append",
            type=role_setting,
            metavar="ROLE=LEVEL",
            help="reasoning effort for one role, overriding the runtime-wide"
            " flag; repeatable",
        )
    return parser


def run_evaluation(args):
    labels = load_labels(Path(args.labels))
    workspace = Path(args.runs_root) / args.run_id
    evaluation = evaluate_run(workspace, labels)

    artifacts = workspace / "artifacts"
    # Workbook values may be dates; default=str keeps the record readable.
    evaluation_json = json.dumps(evaluation, indent=2, default=str) + "\n"
    (artifacts / "evaluation.json").write_text(evaluation_json)
    (artifacts / "evaluation.md").write_text(render_evaluation_md(evaluation))

    for name, metric in evaluation["metrics"].items():
        value, detail = format_metric(metric)
        emit(f"{name}: {value}" + (f" ({detail})" if detail else ""))
    emit(f"Evaluation written: {artifacts / 'evaluation.md'}")

    if args.record_baseline:
        baseline = Path(args.record_baseline)
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(evaluation_json)
        emit(f"Baseline recorded: {baseline}")


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        if args.command == "ui":
            try:
                run_ui(args.port)
            except KeyboardInterrupt:
                emit("WorkCrew UI stopped.")
                return 130
            return 0
        if args.command == "evaluate":
            run_evaluation(args)
            return 0
        if args.command == "build-benchmark":
            summary = build_benchmark(Path(args.split_dir), Path(args.output))
            emit(
                f"Benchmark built: {summary['documents']} documents"
                f" ({summary['conflicts']} with injected conflicts)"
                f" -> {summary['output']}"
            )
            return 0

        agents = agent_config_from_args(args, base=recorded_agent_config(args))
        runtimes = build_runtimes(
            args.runtimes,
            agents=agents,
            workbook=fake_workbook_for(args),
            resuming=args.command == "resume",
        )
        if args.command == "run":
            inputs = RunInputs(
                source=Path(args.source),
                workbook=Path(args.workbook),
                task=args.task,
                name=args.name,
                task_images=read_task_images(args.task_image),
                rules_text=args.rules_text,
                rules_file=None if args.rules_file is None else Path(args.rules_file),
                scoping_answers=None
                if args.scoping_answers is None
                else Path(args.scoping_answers),
                review_policy=None
                if args.review_policy is None
                else Path(args.review_policy),
            )
            run_workflow(
                inputs=inputs,
                runs_root=args.runs_root,
                runtimes=runtimes,
                agents=agents,
            )
        else:
            resume_workflow(
                run_id=args.run_id, runs_root=args.runs_root, runtimes=runtimes
            )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[workflow] Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
