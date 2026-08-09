"""Thin workflow graph (plan section 30).

INIT -> PREPARE_WORKSPACE -> BUILD_MANIFEST -> LOAD_SCHEMA ->
CLAUDE_FILL -> VALIDATE -> WRITE_DRAFT -> CODEX_REVIEW, then the
conditional second half: no actionable findings finalizes directly;
otherwise CLAUDE_REVISE -> APPLY_ALLOWED_REVISIONS, one CODEX_REREVIEW
round when rebuttals exist, HUMAN_REVIEW when anything stays
unresolved, then FINALIZE. The scoping pause (#7) is still missing.
Dependencies (workspace, inputs, runtimes, audit) are closed over;
LangGraph state carries file paths and plain values only.
"""

import json
import shutil
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from workflow_app.handoff import build_handoff, render_handoff_markdown
from workflow_app.ingestion.manifest import Manifest, build_manifest
from workflow_app.models import (
    ExtractionResult,
    ReReviewResult,
    ReviewResult,
    RevisionResult,
)
from workflow_app.progress import emit
from workflow_app.provenance.store import (
    ProvenanceEntry,
    ProvenanceLog,
    build_provenance,
)
from workflow_app.runtimes.base import AgentRequest
from workflow_app.validation.rules import check_proposal
from workflow_app.workbook import writer
from workflow_app.workbook.mutations import CellMutation, apply_mutations
from workflow_app.workbook.safety import Allowlist, cell_key
from workflow_app.workbook.schema import WorkbookSchema, load_workbook_schema
from workflow_app.workflow import routing
from workflow_app.workflow.state import WorkflowState


def build_graph(workspace, inputs, runtimes, audit):
    def stage(name, body):
        def node(state):
            audit.record_stage_started(state["run_id"], name)
            update = body(state) or {}
            audit.record_stage_finished(state["run_id"], name)
            return {"phase": name, **update}

        return node

    def init(state):
        emit(f"Registering run {state['run_id']} in the audit store...")
        audit.record_run_started(state["run_id"], inputs)

    def prepare_workspace(state):
        emit("Copying inputs into the workspace...")
        workspace.copy_inputs(inputs)

    def build_manifest_node(state):
        manifest = build_manifest(workspace.input_sources)
        workspace.manifest_json.write_text(manifest.model_dump_json(indent=2))
        emit(f"Building file manifest... {len(manifest.files)} files found")
        return {"manifest_path": str(workspace.manifest_json)}

    def load_schema(state):
        # The engine already validated the config as a fail-fast gate;
        # this node loads it again and stores the canonical form.
        emit("Loading workbook schema...")
        schema = load_workbook_schema(inputs.workbook_schema)
        workspace.workbook_schema_json.write_text(schema.model_dump_json(indent=2))
        return {"schema_path": str(workspace.workbook_schema_json)}

    def claude_fill(state):
        emit("Starting Filler...")
        # Raw agent output only; contract + rule validation happens in the
        # VALIDATE node (guardrail 49.11).
        run_agent("filler", workspace.filler_outputs / "extraction.json")
        emit("Filler complete.")
        return {"extraction_path": str(workspace.filler_outputs / "extraction.json")}

    def schema_from(state):
        return WorkbookSchema.model_validate(
            json.loads(Path(state["schema_path"]).read_text())
        )

    def validate(state):
        emit("Validating proposals...")
        raw = json.loads(Path(state["extraction_path"]).read_text())
        extraction = ExtractionResult.model_validate(raw)
        schema = schema_from(state)

        rejections = []
        for index, proposal in enumerate(extraction.proposals):
            reason = check_proposal(proposal, schema)
            if reason is not None:
                rejections.append(
                    {
                        "index": index,
                        "cell": cell_key(proposal.sheet, proposal.cell),
                        "reason": reason,
                    }
                )

        workspace.extraction_json.write_text(extraction.model_dump_json(indent=2))
        workspace.validation_json.write_text(
            json.dumps({"rejections": rejections}, indent=2)
        )
        emit(
            f"Validation complete: {len(extraction.proposals)} proposals,"
            f" {len(rejections)} rejected"
        )
        return {"extraction_path": str(workspace.extraction_json)}

    def write_draft(state):
        emit("Writing draft workbook...")
        extraction = ExtractionResult.model_validate(
            json.loads(Path(state["extraction_path"]).read_text())
        )
        rejections = json.loads(workspace.validation_json.read_text())["rejections"]
        rejected_indexes = {rejection["index"] for rejection in rejections}
        schema = schema_from(state)

        shutil.copy2(
            workspace.input_workbook / inputs.workbook.name, workspace.draft_xlsx
        )

        writable = [
            (index, proposal)
            for index, proposal in enumerate(extraction.proposals)
            if proposal.status == "proposed" and index not in rejected_indexes
        ]
        allowlist = Allowlist(
            cell_key(proposal.sheet, proposal.cell) for _, proposal in writable
        )
        mutations = [
            CellMutation(
                sheet=proposal.sheet,
                cell=proposal.cell,
                value=proposal.value,
                actor_role="filler",
                source_ref=f"proposals[{index}]",
            )
            for index, proposal in writable
        ]
        outcomes = apply_mutations(
            workspace.draft_xlsx, mutations, schema, allowlist, audit, state["run_id"]
        )

        proposals_by_ref = {
            f"proposals[{index}]": proposal for index, proposal in writable
        }
        applied = [
            (proposals_by_ref[outcome.mutation.source_ref], outcome.cell_ref)
            for outcome in outcomes
            if outcome.status == "applied"
        ]
        provenance = build_provenance(
            applied, state["run_id"], "filler", runtimes["filler"].name
        )
        workspace.provenance_json.write_text(provenance.model_dump_json(indent=2))

        manifest = Manifest.model_validate(
            json.loads(Path(state["manifest_path"]).read_text())
        )
        handoff = build_handoff(manifest, extraction, rejections, outcomes, schema)
        workspace.handoff_json.write_text(json.dumps(handoff, indent=2))
        workspace.handoff_md.write_text(render_handoff_markdown(handoff))

        emit(f"Draft written: {len(applied)} cells populated")
        return {"draft_xlsx_path": str(workspace.draft_xlsx)}

    def run_agent(role, raw_output_path):
        result = runtimes[role].run(
            AgentRequest(role=role, workspace_path=str(workspace.root))
        )
        if result.status != "ok":
            raise RuntimeError(f"{role} runtime failed: {result.error}")
        raw_output_path.write_text(json.dumps(result.output, indent=2))
        return result.output

    def load_review(state):
        return ReviewResult.model_validate(
            json.loads(Path(state["review_path"]).read_text())
        )

    def load_revision(state):
        return RevisionResult.model_validate(
            json.loads(Path(state["revision_path"]).read_text())
        )

    def load_verdicts(state):
        if state.get("re_review_path") is None:
            return []
        result = ReReviewResult.model_validate(
            json.loads(Path(state["re_review_path"]).read_text())
        )
        return result.verdicts

    def codex_review(state):
        emit("Starting Reviewer...")
        raw = run_agent("reviewer", workspace.reviewer_outputs / "review.json")
        review = ReviewResult.model_validate(raw)
        reason = routing.check_finding_cells(review.findings)
        if reason is not None:
            raise ValueError(reason)
        workspace.review_json.write_text(review.model_dump_json(indent=2))
        workspace.review_md.write_text(_render_review_md(review))
        counts = _verdict_counts(review.findings)
        emit(
            "Review complete: "
            + ", ".join(f"{count} {verdict}" for verdict, count in counts)
        )
        return {"review_path": str(workspace.review_json)}

    def claude_revise(state):
        emit("Starting Revision...")
        review = load_review(state)
        schema = schema_from(state)
        extraction = ExtractionResult.model_validate(
            json.loads(Path(state["extraction_path"]).read_text())
        )
        provenance = ProvenanceLog.model_validate(
            json.loads(workspace.provenance_json.read_text())
        )

        actionable = routing.non_pass_findings(review.findings)
        flagged_cells = {finding.cell for finding in actionable}
        sheet_name = schema.target_sheet().name
        # Only the allowed context (plan section 27): non-PASS findings,
        # their proposals and provenance, and the mutation allowlist.
        restricted_inputs = {
            "findings": [finding.model_dump() for finding in actionable],
            "proposals": {
                proposal.cell: proposal.model_dump()
                for proposal in extraction.proposals
                if proposal.cell in flagged_cells
            },
            "provenance": {
                cell: entry.model_dump()
                for entry in provenance.entries
                for cell in flagged_cells
                if entry.cell == cell_key(sheet_name, cell)
            },
            "mutation_allowlist": routing.derive_revision_allowlist(
                review.findings, schema
            ),
        }
        (workspace.revision_outputs / "inputs.json").write_text(
            json.dumps(restricted_inputs, indent=2)
        )

        raw = run_agent("revision", workspace.revision_outputs / "decisions.json")
        revision = RevisionResult.model_validate(raw)
        reason = routing.check_decisions(review.findings, revision.decisions)
        if reason is not None:
            raise ValueError(reason)
        workspace.revision_json.write_text(revision.model_dump_json(indent=2))
        actions = _action_counts(revision.decisions)
        emit(
            "Revision complete: "
            + ", ".join(f"{count} {action}" for action, count in actions)
        )
        return {"revision_path": str(workspace.revision_json)}

    def apply_allowed_revisions(state):
        emit("Applying authorized revisions...")
        review = load_review(state)
        revision = load_revision(state)
        schema = schema_from(state)
        sheet = schema.target_sheet()
        findings_by_cell = {finding.cell: finding for finding in review.findings}

        draft = writer.open_draft(workspace.draft_xlsx)
        mutations, decision_by_ref = [], {}
        for index, decision in enumerate(revision.decisions):
            source_ref = f"decisions[{index}]"
            decision_by_ref[source_ref] = decision
            if decision.action in ("ACCEPT", "FIX", "CLEAR"):
                value = {
                    "ACCEPT": findings_by_cell[decision.cell].recommended_value,
                    "FIX": decision.proposed_value,
                    "CLEAR": None,
                }[decision.action]
                mutations.append(
                    CellMutation(
                        sheet=sheet.name,
                        cell=decision.cell,
                        value=value,
                        actor_role="revision",
                        source_ref=source_ref,
                    )
                )
            if decision.note_append is not None:
                cell_ref = writer.normalize_cell(decision.cell)
                notes_ref = routing.notes_cell_for(sheet, cell_ref)
                if notes_ref is None:
                    raise ValueError(
                        f"decision on {decision.cell!r} carries note_append but"
                        " the target sheet declares no notes_field"
                    )
                current = writer.read_cell(draft, sheet.name, notes_ref)
                text = (
                    f"{current}\n{decision.note_append}"
                    if current
                    else decision.note_append
                )
                mutations.append(
                    CellMutation(
                        sheet=sheet.name,
                        cell=notes_ref,
                        value=text,
                        actor_role="revision",
                        source_ref=source_ref,
                    )
                )

        allowlist = Allowlist(
            routing.derive_revision_allowlist(review.findings, schema)
        )
        outcomes = apply_mutations(
            workspace.draft_xlsx, mutations, schema, allowlist, audit, state["run_id"]
        )
        rejected = [outcome for outcome in outcomes if outcome.status == "rejected"]
        if rejected:
            reasons = "; ".join(
                f"{outcome.mutation.cell}: {outcome.reason}" for outcome in rejected
            )
            raise ValueError(f"revision mutations were rejected: {reasons}")

        _resync_provenance(
            workspace, outcomes, decision_by_ref, state["run_id"], runtimes
        )
        workspace.revision_log_md.write_text(
            _render_revision_log(revision.decisions, outcomes)
        )
        applied = sum(1 for outcome in outcomes if outcome.status == "applied")
        emit(f"Applied {applied} authorized revisions")

    def codex_rereview(state):
        revision = load_revision(state)
        rebutted = routing.rebutted_cells(revision.decisions)
        emit(f"Starting targeted re-review: {len(rebutted)} rebutted cells...")
        review = load_review(state)
        findings_by_cell = {finding.cell: finding for finding in review.findings}
        restricted_inputs = {
            "rebutted": [
                {
                    "finding": findings_by_cell[cell].model_dump(),
                    "decision": next(
                        decision.model_dump()
                        for decision in revision.decisions
                        if decision.cell == cell and decision.action == "REBUT"
                    ),
                }
                for cell in rebutted
            ]
        }
        (workspace.reviewer_outputs / "re_review_inputs.json").write_text(
            json.dumps(restricted_inputs, indent=2)
        )

        raw = run_agent("re_review", workspace.reviewer_outputs / "re_review.json")
        result = ReReviewResult.model_validate(raw)
        reason = routing.check_re_review_coverage(rebutted, result.verdicts)
        if reason is not None:
            raise ValueError(reason)
        workspace.re_review_json.write_text(result.model_dump_json(indent=2))
        return {"re_review_path": str(workspace.re_review_json)}

    def human_review(state):
        emit("Generating human review artifacts...")
        review = load_review(state)
        revision = load_revision(state)
        verdicts = load_verdicts(state)
        unresolved = routing.collect_unresolved(
            review.findings, revision.decisions, verdicts
        )

        workspace.unresolved_json.write_text(
            json.dumps({"cells": unresolved}, indent=2)
        )

        sheet_name = schema_from(state).target_sheet().name
        draft = writer.open_draft(workspace.draft_xlsx)
        findings_by_cell = {finding.cell: finding for finding in review.findings}
        decisions_by_cell = {decision.cell: decision for decision in revision.decisions}
        verdicts_by_cell = {verdict.cell: verdict for verdict in verdicts}

        items = []
        for entry in unresolved:
            cell = entry["cell"]
            finding = findings_by_cell[cell]
            decision = decisions_by_cell.get(cell)
            verdict = verdicts_by_cell.get(cell)
            items.append(
                {
                    "cell": cell,
                    "current_value": writer.read_cell(draft, sheet_name, cell),
                    "reviewer": {
                        "verdict": finding.verdict,
                        "recommended_value": finding.recommended_value,
                        "comment": finding.reviewer_comment,
                        "evidence": [e.model_dump() for e in finding.evidence],
                    },
                    "revision": None
                    if decision is None
                    else {
                        "action": decision.action,
                        "proposed_value": decision.proposed_value,
                        "justification": decision.justification,
                        "evidence": [e.model_dump() for e in decision.evidence],
                    },
                    "re_review": None
                    if verdict is None
                    else {
                        "verdict": verdict.verdict,
                        "comment": verdict.reviewer_comment,
                    },
                    "reason": entry["reason"],
                }
            )
        workspace.human_review_json.write_text(json.dumps({"items": items}, indent=2))
        workspace.human_review_md.write_text(_render_human_review_md(items))

    def finalize(state):
        emit("Finalizing run...")
        shutil.copy2(workspace.draft_xlsx, workspace.final_xlsx)
        audit.record_run_finished(state["run_id"], "completed")
        _write_run_summary(workspace, audit, state["run_id"])

    def route_unresolved(state):
        review = load_review(state)
        revision = load_revision(state)
        unresolved = routing.collect_unresolved(
            review.findings, revision.decisions, load_verdicts(state)
        )
        return "HUMAN_REVIEW" if unresolved else "FINALIZE"

    def route_after_review(state):
        if routing.has_actionable_findings(load_review(state).findings):
            return "CLAUDE_REVISE"
        return "FINALIZE"

    def route_after_apply(state):
        if routing.rebutted_cells(load_revision(state).decisions):
            return "CODEX_REREVIEW"
        return route_unresolved(state)

    graph = StateGraph(WorkflowState)
    graph.add_node("INIT", stage("INIT", init))
    graph.add_node("PREPARE_WORKSPACE", stage("PREPARE_WORKSPACE", prepare_workspace))
    graph.add_node("BUILD_MANIFEST", stage("BUILD_MANIFEST", build_manifest_node))
    graph.add_node("LOAD_SCHEMA", stage("LOAD_SCHEMA", load_schema))
    graph.add_node("CLAUDE_FILL", stage("CLAUDE_FILL", claude_fill))
    graph.add_node("VALIDATE", stage("VALIDATE", validate))
    graph.add_node("WRITE_DRAFT", stage("WRITE_DRAFT", write_draft))
    graph.add_node("CODEX_REVIEW", stage("CODEX_REVIEW", codex_review))
    graph.add_node("CLAUDE_REVISE", stage("CLAUDE_REVISE", claude_revise))
    graph.add_node(
        "APPLY_ALLOWED_REVISIONS",
        stage("APPLY_ALLOWED_REVISIONS", apply_allowed_revisions),
    )
    graph.add_node("CODEX_REREVIEW", stage("CODEX_REREVIEW", codex_rereview))
    graph.add_node("HUMAN_REVIEW", stage("HUMAN_REVIEW", human_review))
    graph.add_node("FINALIZE", stage("FINALIZE", finalize))

    graph.add_edge(START, "INIT")
    graph.add_edge("INIT", "PREPARE_WORKSPACE")
    graph.add_edge("PREPARE_WORKSPACE", "BUILD_MANIFEST")
    graph.add_edge("BUILD_MANIFEST", "LOAD_SCHEMA")
    graph.add_edge("LOAD_SCHEMA", "CLAUDE_FILL")
    graph.add_edge("CLAUDE_FILL", "VALIDATE")
    graph.add_edge("VALIDATE", "WRITE_DRAFT")
    graph.add_edge("WRITE_DRAFT", "CODEX_REVIEW")
    graph.add_conditional_edges(
        "CODEX_REVIEW",
        route_after_review,
        {"CLAUDE_REVISE": "CLAUDE_REVISE", "FINALIZE": "FINALIZE"},
    )
    graph.add_edge("CLAUDE_REVISE", "APPLY_ALLOWED_REVISIONS")
    graph.add_conditional_edges(
        "APPLY_ALLOWED_REVISIONS",
        route_after_apply,
        {
            "CODEX_REREVIEW": "CODEX_REREVIEW",
            "HUMAN_REVIEW": "HUMAN_REVIEW",
            "FINALIZE": "FINALIZE",
        },
    )
    graph.add_conditional_edges(
        "CODEX_REREVIEW",
        route_unresolved,
        {"HUMAN_REVIEW": "HUMAN_REVIEW", "FINALIZE": "FINALIZE"},
    )
    graph.add_edge("HUMAN_REVIEW", "FINALIZE")
    graph.add_edge("FINALIZE", END)

    return graph.compile()


def _verdict_counts(findings):
    order = ("FAIL", "WARN", "PASS", "UNRESOLVED")
    counts = {verdict: 0 for verdict in order}
    for finding in findings:
        counts[finding.verdict] += 1
    return [(verdict, counts[verdict]) for verdict in order if counts[verdict]]


def _action_counts(decisions):
    counts = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
    return sorted(counts.items())


def _resync_provenance(workspace, outcomes, decision_by_ref, run_id, runtimes):
    # Provenance must match post-revision cell contents exactly: every
    # applied revision replaces (or adds) its cell's entry.
    log = ProvenanceLog.model_validate(
        json.loads(workspace.provenance_json.read_text())
    )
    entries = {entry.cell: entry for entry in log.entries}
    order = list(entries)
    for outcome in outcomes:
        if outcome.status != "applied":
            continue
        decision = decision_by_ref[outcome.mutation.source_ref]
        cell = cell_key(outcome.mutation.sheet, outcome.cell_ref)
        entries[cell] = ProvenanceEntry(
            cell=cell,
            value=outcome.mutation.value,
            agent_role="revision",
            agent_runtime=runtimes["revision"].name,
            evidence=decision.evidence,
            rules_applied=[],
            confidence=None,
            run_id=run_id,
        )
        if cell not in order:
            order.append(cell)
    updated = ProvenanceLog(entries=[entries[cell] for cell in order])
    workspace.provenance_json.write_text(updated.model_dump_json(indent=2))


def _render_review_md(review):
    lines = ["# Review", ""]
    for verdict, count in _verdict_counts(review.findings):
        lines.append(f"- {verdict}: {count}")
    lines.append("")
    for finding in review.findings:
        lines += [f"## {finding.cell} — {finding.verdict}", ""]
        if finding.recommended_value is not None:
            lines.append(f"- Recommended: {finding.recommended_value}")
        lines += [f"- {finding.reviewer_comment}", ""]
    return "\n".join(lines)


def _render_revision_log(decisions, outcomes):
    applied_refs = {
        outcome.mutation.source_ref
        for outcome in outcomes
        if outcome.status == "applied"
    }
    lines = ["# Revision log", ""]
    for index, decision in enumerate(decisions):
        marker = "applied" if f"decisions[{index}]" in applied_refs else "no write"
        lines.append(f"- {decision.cell} — {decision.action} ({marker})")
        lines.append(f"  - {decision.justification}")
        if decision.note_append is not None:
            lines.append(f"  - Note appended: {decision.note_append}")
    lines.append("")
    return "\n".join(lines)


def _render_human_review_md(items):
    lines = ["# Human review", ""]
    if not items:
        lines.append("Nothing unresolved.")
    for item in items:
        reviewer = item["reviewer"]
        revision = item["revision"]
        lines += [
            f"## {item['cell']}",
            "",
            f"- Current value: {item['current_value']!r}",
            f"- Why automation stopped: {item['reason']}",
            (
                f"- Reviewer ({reviewer['verdict']}):"
                f" recommended {reviewer['recommended_value']!r}"
                f" — {reviewer['comment']}"
            ),
        ]
        if revision is not None:
            lines.append(
                f"- Revision ({revision['action']}):"
                f" proposed {revision['proposed_value']!r}"
                f" — {revision['justification']}"
            )
        if item["re_review"] is not None:
            lines.append(
                f"- Re-review: {item['re_review']['verdict']}"
                f" — {item['re_review']['comment']}"
            )
        lines.append("")
    return "\n".join(lines)


def _write_run_summary(workspace, audit, run_id):
    run = audit.get_run(run_id)
    stage_lines = [
        f"| {entry['stage']} | {entry['status']} | {entry['started_at']} |"
        f" {entry['finished_at'] or ''} |"
        for entry in audit.list_stages(run_id)
    ]
    summary = "\n".join(
        [
            "# Run summary",
            "",
            f"- Run: {run['run_id']}",
            f"- Status: {run['status']}",
            f"- Started: {run['started_at']}",
            f"- Finished: {run['finished_at']}",
            "",
            "## Inputs",
            "",
            f"- Source: {run['source_path']}",
            f"- Workbook: {run['workbook_path']}",
            f"- Rules: {run['rules_path']}",
            f"- Workbook schema: {run['workbook_schema_path']}",
            "",
            "## Stages",
            "",
            "| Stage | Status | Started | Finished |",
            "| --- | --- | --- | --- |",
            *stage_lines,
            "",
        ]
    )
    workspace.run_summary.write_text(summary)
