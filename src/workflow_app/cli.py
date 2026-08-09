"""CLI entry (plan section 4): `workflow run` and `workflow resume`.

A thin shell over the engine — no business logic here. During fake-first
development (tickets #2-#9, plan section 32) the CLI wires in a
FakeAgentRuntime; live runtime adapters replace it in later tickets.
"""

import argparse
import sys
from pathlib import Path

from workflow_app.progress import emit
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import resume_workflow, run_workflow
from workflow_app.workspace import RunInputs

# Degenerate walking-skeleton payloads: one placeholder scoping
# question, an empty fill, and an all-clear review, so the whole graph
# short-circuits to FINALIZE. Live runtimes land in #10/#11.
FAKE_OUTPUTS = {
    "scoping": {
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
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="workflow",
        description="Local-first document-to-workbook workflow engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="start a new workflow run")
    run.add_argument("--source", required=True, help="source documents folder")
    run.add_argument("--workbook", required=True, help="target workbook file")
    run.add_argument("--rules", required=True, help="rule/reference files folder")
    run.add_argument(
        "--workbook-schema",
        required=True,
        help="hand-authored workbook schema config (JSON)",
    )
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
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    emit("Using fake agent runtimes (live runtimes arrive in later tickets).")
    fake = FakeAgentRuntime(FAKE_OUTPUTS)
    runtimes = {role: fake for role in FAKE_OUTPUTS}
    try:
        if args.command == "run":
            inputs = RunInputs(
                source=Path(args.source),
                workbook=Path(args.workbook),
                rules=Path(args.rules),
                workbook_schema=Path(args.workbook_schema),
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
