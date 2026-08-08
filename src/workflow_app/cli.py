"""CLI entry (plan section 4): `workflow run`.

A thin shell over the engine — no business logic here. During fake-first
development (tickets #2-#9, plan section 32) the CLI wires in a
FakeAgentRuntime; live runtime adapters replace it in later tickets.
"""

import argparse
import sys

from workflow_app.progress import emit
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow

# Degenerate walking-skeleton payload. Ticket #5 wires realistic fixture
# flows through the fake pipeline; live runtimes land in #10.
FAKE_OUTPUTS = {"filler": {"proposals": []}}


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
        "--runs-root",
        default="runs",
        help="directory holding per-run workspaces (default: ./runs)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    emit("Using fake agent runtimes (live runtimes arrive in later tickets).")
    try:
        run_workflow(
            source=args.source,
            workbook=args.workbook,
            rules=args.rules,
            workbook_schema=args.workbook_schema,
            runs_root=args.runs_root,
            runtimes={"filler": FakeAgentRuntime(FAKE_OUTPUTS)},
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[workflow] Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
