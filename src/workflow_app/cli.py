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
from pathlib import Path

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
from workflow_app.workspace import RunInputs

# Degenerate walking-skeleton payloads: one placeholder scoping
# question, an empty fill, and an all-clear review, so a pure fake run
# short-circuits to FINALIZE. The revision/re-review fixtures cover a
# live run resumed with --runtimes fake (runtime choice is
# per-invocation, ADR 0019): zero decisions and zero verdicts degrade
# every open finding into the UNRESOLVED / human-review pipeline.
FAKE_OUTPUTS = {
    "scoping": {
        # workbook_schema is filled in per invocation by
        # fake_scoping_schema(): the target sheet must name a sheet the
        # operator's workbook actually has, and the fake fill proposes
        # nothing, so no column ever needs declaring.
        "questions": [
            {
                "id": "Q1",
                "question": (
                    "Confirm the source folders are the complete set to process."
                ),
            }
        ]
    },
    "filler": {"proposals": []},
    "reviewer": {"findings": []},
    "revision": {"decisions": []},
    "re_review": {"verdicts": []},
}


# Product default models and review effort (ADR 0020). Pinned so a CLI
# upgrade or account-default change never silently shifts engine
# behavior; overridable per run via the CLI flags below.
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6[1m]"
DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_CODEX_EFFORT = "high"

CODEX_EFFORT_CHOICES = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)


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


def build_runtimes(
    choice,
    claude_model=DEFAULT_CLAUDE_MODEL,
    codex_model=DEFAULT_CODEX_MODEL,
    codex_effort=DEFAULT_CODEX_EFFORT,
    workbook=None,
):
    if choice == "fake":
        emit("Using fake agent runtimes (walking-skeleton fixtures).")
        outputs = {role: dict(output) for role, output in FAKE_OUTPUTS.items()}
        if workbook is not None:
            outputs["scoping"]["workbook_schema"] = fake_scoping_schema(workbook)
        fake = FakeAgentRuntime(outputs)
        return {role: fake for role in outputs}
    emit(f"Claude model: {claude_model}")
    emit(f"Codex model: {codex_model} (reasoning effort: {codex_effort})")
    claude = ClaudeCodeRuntime(model=claude_model)
    codex = CodexRuntime(model=codex_model, effort=codex_effort)
    return {
        "scoping": claude,
        "filler": claude,
        "revision": claude,
        "reviewer": codex,
        "re_review": codex,
    }


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
        subparser.add_argument(
            "--claude-model",
            default=DEFAULT_CLAUDE_MODEL,
            help=(
                "model for the Claude roles (scoping/fill/revision);"
                f" a [1m] suffix selects 1M context (default: {DEFAULT_CLAUDE_MODEL})"
            ),
        )
        subparser.add_argument(
            "--codex-model",
            default=DEFAULT_CODEX_MODEL,
            help=(
                "model for the Codex roles (review/re-review)"
                f" (default: {DEFAULT_CODEX_MODEL})"
            ),
        )
        subparser.add_argument(
            "--codex-effort",
            choices=CODEX_EFFORT_CHOICES,
            default=DEFAULT_CODEX_EFFORT,
            help=(
                "Codex reasoning effort for the review roles"
                f" (default: {DEFAULT_CODEX_EFFORT})"
            ),
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

        runtimes = build_runtimes(
            args.runtimes,
            claude_model=args.claude_model,
            codex_model=args.codex_model,
            codex_effort=args.codex_effort,
            workbook=getattr(args, "workbook", None),
        )
        if args.command == "run":
            inputs = RunInputs(
                source=Path(args.source),
                workbook=Path(args.workbook),
                task=args.task,
                rules_text=args.rules_text,
                rules_file=None if args.rules_file is None else Path(args.rules_file),
                scoping_answers=None
                if args.scoping_answers is None
                else Path(args.scoping_answers),
                review_policy=None
                if args.review_policy is None
                else Path(args.review_policy),
            )
            run_workflow(inputs=inputs, runs_root=args.runs_root, runtimes=runtimes)
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
