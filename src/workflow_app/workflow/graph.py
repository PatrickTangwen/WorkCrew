"""Thin workflow graph.

INIT -> PREPARE_WORKSPACE -> BUILD_MANIFEST -> LOAD_SCHEMA ->
CLAUDE_FILL -> FINALIZE, a subset of the full graph in plan section 30.
Later tickets insert the remaining nodes between these. Dependencies
(workspace, inputs, schema, runtimes, audit) are closed over; LangGraph
state carries file paths and plain values only.
"""

import json

from langgraph.graph import END, START, StateGraph

from workflow_app.ingestion.manifest import build_manifest
from workflow_app.progress import emit
from workflow_app.runtimes.base import AgentRequest
from workflow_app.workflow.state import WorkflowState


def build_graph(workspace, inputs, schema, runtimes, audit):
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
        # The engine validated the hand-authored config before the run
        # started; this node stores the canonical form as an artifact.
        emit("Loading workbook schema...")
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
    graph.add_node("FINALIZE", stage("FINALIZE", finalize))

    graph.add_edge(START, "INIT")
    graph.add_edge("INIT", "PREPARE_WORKSPACE")
    graph.add_edge("PREPARE_WORKSPACE", "BUILD_MANIFEST")
    graph.add_edge("BUILD_MANIFEST", "LOAD_SCHEMA")
    graph.add_edge("LOAD_SCHEMA", "CLAUDE_FILL")
    graph.add_edge("CLAUDE_FILL", "FINALIZE")
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
