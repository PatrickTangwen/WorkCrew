"""Thin workflow graph.

INIT -> PREPARE_WORKSPACE -> BUILD_MANIFEST -> LOAD_SCHEMA ->
CLAUDE_FILL -> VALIDATE -> WRITE_DRAFT -> FINALIZE, a subset of the
full graph in plan section 30. Later tickets insert the remaining nodes
between these. Dependencies (workspace, inputs, runtimes, audit) are
closed over; LangGraph state carries file paths and plain values only.
"""

import json
import shutil
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from workflow_app.handoff import build_handoff, render_handoff_markdown
from workflow_app.ingestion.manifest import Manifest, build_manifest
from workflow_app.models import ExtractionResult
from workflow_app.progress import emit
from workflow_app.provenance.store import build_provenance
from workflow_app.runtimes.base import AgentRequest
from workflow_app.validation.rules import check_proposal
from workflow_app.workbook.mutations import CellMutation, apply_mutations
from workflow_app.workbook.safety import Allowlist
from workflow_app.workbook.schema import WorkbookSchema, load_workbook_schema
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
        request = AgentRequest(role="filler", workspace_path=str(workspace.root))
        result = runtimes["filler"].run(request)
        if result.status != "ok":
            raise RuntimeError(f"Filler runtime failed: {result.error}")
        # Raw agent output only; contract + rule validation happens in the
        # VALIDATE node (guardrail 49.11), which lands with ticket #5.
        extraction_path = workspace.filler_outputs / "extraction.json"
        extraction_path.write_text(json.dumps(result.output, indent=2))
        emit("Filler complete.")
        return {"extraction_path": str(extraction_path)}

    def validate(state):
        emit("Validating proposals...")
        raw = json.loads(Path(state["extraction_path"]).read_text())
        extraction = ExtractionResult.model_validate(raw)
        schema = WorkbookSchema.model_validate(
            json.loads(Path(state["schema_path"]).read_text())
        )

        rejections = []
        for index, proposal in enumerate(extraction.proposals):
            reason = check_proposal(proposal, schema)
            if reason is not None:
                rejections.append(
                    {
                        "index": index,
                        "cell": f"{proposal.sheet}!{proposal.cell}",
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
        schema = WorkbookSchema.model_validate(
            json.loads(Path(state["schema_path"]).read_text())
        )

        shutil.copy2(
            workspace.input_workbook / inputs.workbook.name, workspace.draft_xlsx
        )

        writable = [
            (index, proposal)
            for index, proposal in enumerate(extraction.proposals)
            if proposal.status == "proposed" and index not in rejected_indexes
        ]
        allowlist = Allowlist(
            f"{proposal.sheet}!{proposal.cell}" for _, proposal in writable
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

    def finalize(state):
        emit("Finalizing run...")
        audit.record_run_finished(state["run_id"], "completed")
        _write_run_summary(workspace, audit, state["run_id"])

    graph = StateGraph(WorkflowState)
    graph.add_node("INIT", stage("INIT", init))
    graph.add_node("PREPARE_WORKSPACE", stage("PREPARE_WORKSPACE", prepare_workspace))
    graph.add_node("BUILD_MANIFEST", stage("BUILD_MANIFEST", build_manifest_node))
    graph.add_node("LOAD_SCHEMA", stage("LOAD_SCHEMA", load_schema))
    graph.add_node("CLAUDE_FILL", stage("CLAUDE_FILL", claude_fill))
    graph.add_node("VALIDATE", stage("VALIDATE", validate))
    graph.add_node("WRITE_DRAFT", stage("WRITE_DRAFT", write_draft))
    graph.add_node("FINALIZE", stage("FINALIZE", finalize))

    graph.add_edge(START, "INIT")
    graph.add_edge("INIT", "PREPARE_WORKSPACE")
    graph.add_edge("PREPARE_WORKSPACE", "BUILD_MANIFEST")
    graph.add_edge("BUILD_MANIFEST", "LOAD_SCHEMA")
    graph.add_edge("LOAD_SCHEMA", "CLAUDE_FILL")
    graph.add_edge("CLAUDE_FILL", "VALIDATE")
    graph.add_edge("VALIDATE", "WRITE_DRAFT")
    graph.add_edge("WRITE_DRAFT", "FINALIZE")
    graph.add_edge("FINALIZE", END)

    return graph.compile()


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
