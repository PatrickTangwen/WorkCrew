"""Benchmark evaluation through the engine seam (ticket #13).

A mini Kleister-like split is built into benchmark inputs, a full fake
engine run executes over them with deliberate imperfections (a wrong
draft value, an unsupported fill, a confident fill of a conflicted
field, one reviewer false positive), and the harness scores the
completed run. Assertions pin every metric's exact counts.
"""

import json
from pathlib import Path

from openpyxl import load_workbook

from workflow_app.benchmark.kleister import build_benchmark
from workflow_app.cli import main
from workflow_app.evaluation.evaluate import evaluate_run
from workflow_app.evaluation.labels import load_labels
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import RunInputs

KEYS = (
    "address__post_town address__postcode address__street_line charity_name"
    " charity_number income_annually_in_british_pounds report_date"
    " spending_annually_in_british_pounds"
)

DOCS = {
    "aaa1": {
        "address__post_town": "BRISTOL",
        "address__postcode": "BS1_4DJ",
        "address__street_line": "12_HARBOUR_ROAD",
        "charity_name": "Harbour_Trust",
        "charity_number": "1234567",
        "income_annually_in_british_pounds": "500000.00",
        "report_date": "2018-03-31",
        "spending_annually_in_british_pounds": "450000.00",
    },
    "bbb2": {
        "address__post_town": "LEEDS",
        "address__postcode": "LS1_1UR",
        "address__street_line": "8_CITY_SQUARE",
        "charity_name": "Leeds_Aid",
        "charity_number": "7654321",
        "income_annually_in_british_pounds": "1200000.00",
        "report_date": "2019-12-31",
        "spending_annually_in_british_pounds": "1100000.00",
    },
    # Partial document: street/income/spending genuinely absent.
    "ccc3": {
        "address__post_town": "YORK",
        "address__postcode": "YO1_7HH",
        "charity_name": "Minster_Fund",
        "charity_number": "1111111",
        "report_date": "2020-06-30",
    },
}

BANDS = {"aaa1": "Medium", "bbb2": "Large"}

NUMBER_FIELDS = ("Annual Income GBP", "Annual Spending GBP")


def write_split(tmp_path):
    split = tmp_path / "dev-0"
    split.mkdir()
    in_lines, expected_lines = [], []
    for stem, labels in DOCS.items():
        text = f"Annual report of {labels['charity_name']}.\\nFull details inside."
        in_lines.append("\t".join([f"{stem}.pdf", KEYS, "d", "t", "x", text]))
        expected_lines.append(
            " ".join(f"{key}={value}" for key, value in sorted(labels.items()))
        )
    (split / "in.tsv").write_text("\n".join(in_lines) + "\n")
    (split / "expected.tsv").write_text("\n".join(expected_lines) + "\n")
    return split


def evidence(folder, evidence_type="direct"):
    return {
        "source_file": f"{folder}/report.txt",
        "source_location": "page 1",
        "evidence_text": "Stated in the report.",
        "evidence_type": evidence_type,
    }


def build_outputs(labels):
    proposals, findings, decisions, verdicts = [], [], [], []
    for row in labels.rows:
        folder = row.folder
        for field_name, label in row.fields.items():
            # Default arguments bind the loop variables per iteration.
            def proposal(
                value,
                extra_evidence=None,
                row=row,
                field_name=field_name,
                label=label,
                folder=folder,
            ):
                proposals.append(
                    {
                        "sheet": labels.sheet,
                        "row": row.row,
                        "column_name": field_name,
                        "cell": label.cell,
                        "value": value,
                        "evidence": [evidence(folder)] + (extra_evidence or []),
                        "rules_applied": [],
                        "confidence": "medium",
                        "status": "proposed",
                    }
                )

            if label.status == "expected":
                value = label.expected_value
                if field_name in NUMBER_FIELDS:
                    value = float(value)
                if field_name == "Charity Name" and folder == "ccc3":
                    # Deliberately wrong draft; review flags, revision fixes.
                    proposal("Totally Wrong Charity")
                    findings.append(
                        {
                            "cell": label.cell,
                            "verdict": "FAIL",
                            "recommended_value": label.expected_value,
                            "evidence": [evidence(folder)],
                            "reviewer_comment": "Name does not match the report.",
                        }
                    )
                    decisions.append(
                        {
                            "cell": label.cell,
                            "action": "FIX",
                            "proposed_value": label.expected_value,
                            "note_append": None,
                            "evidence": [evidence(folder)],
                            "justification": "Report states the registered name.",
                        }
                    )
                elif field_name == "Post Town" and folder == "aaa1":
                    # Correct draft the reviewer wrongly disputes; the
                    # rebuttal is withdrawn on re-review.
                    proposal(
                        label.expected_value,
                        extra_evidence=[evidence(folder, "external_web")],
                    )
                    findings.append(
                        {
                            "cell": label.cell,
                            "verdict": "WARN",
                            "recommended_value": "FAKETOWN",
                            "evidence": [evidence(folder)],
                            "reviewer_comment": "Looks like a different town.",
                        }
                    )
                    decisions.append(
                        {
                            "cell": label.cell,
                            "action": "REBUT",
                            "proposed_value": None,
                            "note_append": None,
                            "evidence": [evidence(folder)],
                            "justification": "The report front page states it.",
                        }
                    )
                    verdicts.append(
                        {
                            "cell": label.cell,
                            "verdict": "WITHDRAWN",
                            "reviewer_comment": "Convinced by the front page.",
                        }
                    )
                else:
                    proposal(value)
            elif label.status == "unresolved":
                # Confident fill of a genuinely conflicted field.
                source = DOCS[folder]
                if field_name == "Annual Income GBP":
                    value = float(source["income_annually_in_british_pounds"])
                else:
                    value = BANDS[folder]
                proposal(value)
                findings.append(
                    {
                        "cell": label.cell,
                        "verdict": "UNRESOLVED",
                        "recommended_value": None,
                        "evidence": [evidence(folder)],
                        "reviewer_comment": "The register extract disagrees.",
                    }
                )
                decisions.append(
                    {
                        "cell": label.cell,
                        "action": "UNRESOLVED",
                        "proposed_value": None,
                        "note_append": None,
                        "evidence": [evidence(folder)],
                        "justification": "Sources conflict; cannot adjudicate.",
                    }
                )
            elif field_name == "Annual Spending GBP" and folder == "ccc3":
                # Unsupported fill of an expected-blank cell; review
                # flags it and revision clears it.
                proposal(999.0)
                findings.append(
                    {
                        "cell": label.cell,
                        "verdict": "FAIL",
                        "recommended_value": None,
                        "evidence": [evidence(folder)],
                        "reviewer_comment": "No spending figure in the report.",
                    }
                )
                decisions.append(
                    {
                        "cell": label.cell,
                        "action": "CLEAR",
                        "proposed_value": None,
                        "note_append": None,
                        "evidence": [evidence(folder)],
                        "justification": "Nothing in the sources supports it.",
                    }
                )
    reviewed_cells = {finding["cell"] for finding in findings}
    findings.extend(
        {
            "cell": proposal["cell"],
            "verdict": "PASS",
            "evidence": proposal["evidence"][:1],
            "reviewer_comment": "Verified against the source.",
        }
        for proposal in proposals
        if proposal["cell"] not in reviewed_cells
    )
    return {
        "filler": {"proposals": proposals},
        "reviewer": {"findings": findings},
        "revision": {"decisions": decisions},
        "re_review": {"verdicts": verdicts},
    }


def run_benchmark(tmp_path):
    split = write_split(tmp_path)
    bench = tmp_path / "bench"
    build_benchmark(
        split,
        bench,
        sample_full=2,
        sample_partial=1,
        text_cap=4000,
        conflicts=1,
        seed=7,
    )
    labels = load_labels(bench / "labels.json")
    outputs = build_outputs(labels)
    runtimes = {role: FakeAgentRuntime(outputs) for role in outputs}
    state = run_workflow(
        inputs=RunInputs(
            source=bench / "source",
            workbook=bench / "template.xlsx",
            rules=bench / "rules",
            workbook_schema=bench / "workbook_schema.json",
            scoping_answers=bench / "scoping_answers.md",
        ),
        runs_root=tmp_path / "runs",
        runtimes=runtimes,
    )
    return bench, labels, state


def test_metrics_over_a_full_fake_engine_run(tmp_path):
    _bench, labels, state = run_benchmark(tmp_path)

    evaluation = evaluate_run(Path(state["workspace_path"]), labels)
    metrics = evaluation["metrics"]

    def ratio(name):
        metric = metrics[name]
        return metric["numerator"], metric["denominator"]

    assert ratio("field_accuracy") == (24, 24)
    assert ratio("missed_data_rate") == (0, 24)
    assert ratio("unsupported_fill_rate") == (0, 4)
    assert ratio("provenance_coverage") == (26, 26)
    assert ratio("review_true_positive_rate") == (4, 4)
    assert ratio("review_false_positive_rate") == (1, 26)
    assert ratio("revision_correctness") == (2, 2)
    assert metrics["unresolved_count"] == 2
    assert ratio("expected_unresolved_escalated") == (2, 2)
    assert metrics["web_evidence_percentage"]["numerator"] == 1
    assert evaluation["run_id"] == state["run_id"]

    # Runtime context for cross-configuration comparison (plan §42).
    run = evaluation["run"]
    assert run["status"] == "completed"
    assert run["duration_seconds"] >= 0
    stage_names = [stage["stage"] for stage in run["stages"]]
    assert "CLAUDE_FILL" in stage_names and "CODEX_REVIEW" in stage_names

    # The conflicted income cell is a recorded miss: confidently
    # filled, flagged, escalated, never resolved to a value.
    conflict_row = next(row for row in labels.rows if row.conflict is not None)
    income_cell = conflict_row.fields["Annual Income GBP"].cell
    detail = next(item for item in evaluation["cells"] if item["cell"] == income_cell)
    assert detail["status"] == "unresolved"
    assert detail["final_correct"] is False
    assert detail["flagged"] is True and detail["escalated"] is True


def test_cli_evaluate_writes_artifacts_and_baseline(tmp_path):
    bench, _labels, state = run_benchmark(tmp_path)
    workspace = Path(state["workspace_path"])
    baseline = tmp_path / "baselines" / "dev0.json"

    exit_code = main(
        [
            "evaluate",
            "--run-id",
            state["run_id"],
            "--runs-root",
            str(tmp_path / "runs"),
            "--labels",
            str(bench / "labels.json"),
            "--record-baseline",
            str(baseline),
        ]
    )

    assert exit_code == 0
    evaluation = json.loads((workspace / "artifacts/evaluation.json").read_text())
    assert evaluation["metrics"]["field_accuracy"]["numerator"] == 24
    assert (
        baseline.read_bytes() == (workspace / "artifacts/evaluation.json").read_bytes()
    )

    text = (workspace / "artifacts/evaluation.md").read_text()
    assert "field_accuracy" in text and "## Misses" in text


def test_cli_build_benchmark_smoke(tmp_path):
    split = write_split(tmp_path)
    output = tmp_path / "bench-cli"

    # The CLI builds with product defaults, which need more documents
    # than the mini split offers — expect the sampling refusal to
    # surface as a clean CLI error, not a traceback.
    exit_code = main(
        ["build-benchmark", "--split-dir", str(split), "--output", str(output)]
    )
    assert exit_code == 2


def test_final_workbook_matches_labels_for_a_correct_row(tmp_path):
    _bench, labels, state = run_benchmark(tmp_path)

    row = next(item for item in labels.rows if item.folder == "ccc3")
    sheet = load_workbook(Path(state["workspace_path"]) / "output/final.xlsx")[
        labels.sheet
    ]
    assert sheet[row.fields["Charity Name"].cell].value == "Minster_Fund"
    assert sheet[row.fields["Charity ID*"].cell].value == "CHA-1111111"
    assert sheet[row.fields["Annual Spending GBP"].cell].value is None
