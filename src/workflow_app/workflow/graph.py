"""Thin workflow graph (plan section 30).

INIT -> PREPARE_WORKSPACE -> BUILD_MANIFEST -> OUTLINE_WORKBOOK ->
CLAUDE_SCOPE -> LOAD_SCHEMA -> AWAIT_SCOPING_ANSWERS (LangGraph
interrupt; skipped when answers are pre-provided, though CLAUDE_SCOPE
always runs because it produces the schema) -> CLAUDE_FILL -> VALIDATE ->
WRITE_DRAFT -> CODEX_REVIEW, then the conditional second half: no
actionable findings finalizes directly; otherwise CLAUDE_REVISE ->
APPLY_ALLOWED_REVISIONS, one CODEX_REREVIEW round when rebuttals
exist, HUMAN_REVIEW when anything stays unresolved, then FINALIZE.
Agent invocations get two lenient retries (plan section 37); exhausted
retries fail the run for the scoping/fill stages and degrade into the
UNRESOLVED / human-review pipeline for the review-cycle stages, while
deterministic failures are never retried. Dependencies (workspace,
inputs, runtimes, audit) are closed over; LangGraph state carries file
paths and plain values only.
"""

import hashlib
import json
import shutil
from pathlib import Path

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from workflow_app.cancellation import WorkflowCancelled
from workflow_app.handoff import build_handoff, render_handoff_markdown
from workflow_app.ingestion.manifest import Manifest, build_manifest
from workflow_app.models import (
    ExtractionResult,
    ReReviewResult,
    ReviewResult,
    RevisionResult,
    ScopingQuestions,
    ScopingResult,
)
from workflow_app.provenance.explorer import render_explorer_html
from workflow_app.provenance.render import build_explorer_data
from workflow_app.provenance.store import build_provenance, resync_provenance
from workflow_app.reports import (
    action_counts,
    render_human_review_md,
    render_review_md,
    render_revision_log_md,
    render_scoping_answers_template,
    render_scoping_questions_md,
    verdict_counts,
)
from workflow_app.review_policy import (
    ReviewPolicy,
    check_strict_fields,
    load_review_policy,
)
from workflow_app.runtimes.base import AgentRequest
from workflow_app.validation.rules import check_proposal
from workflow_app.workbook import writer
from workflow_app.workbook.mutations import (
    CellMutation,
    MutationConflictError,
    apply_mutations,
)
from workflow_app.workbook.outline import WorkbookOutline, build_outline
from workflow_app.workbook.safety import Allowlist, cell_key
from workflow_app.workbook.schema import WorkbookSchema
from workflow_app.workflow import routing
from workflow_app.workflow.state import WorkflowState

# One initial attempt plus two lenient retries (plan section 37).
MAX_AGENT_ATTEMPTS = 3


class AgentStageFailure(Exception):
    """An agent invocation kept failing after the lenient retries."""

    def __init__(self, role, classification, detail):
        super().__init__(
            f"{role} failed after {MAX_AGENT_ATTEMPTS} attempts"
            f" ({classification}): {detail}"
        )
        self.role = role
        self.classification = classification


def build_graph(execution, audit, checkpointer):
    workspace = execution.workspace
    inputs = execution.inputs
    runtimes = execution.runtimes
    progress = execution.progress
    cancellation = execution.cancellation

    def stage(name, body):
        def node(state):
            audit.record_stage_started(state["run_id"], name)
            progress.phase_change(name, "active")
            try:
                if name != "INIT":
                    cancellation.raise_if_cancelled()
                update = body(state) or {}
                cancellation.raise_if_cancelled()
            except WorkflowCancelled:
                audit.record_stage_cancelled(state["run_id"], name)
                progress.phase_change(name, "failed")
                raise
            except GraphBubbleUp:
                # LangGraph control flow (the scoping interrupt), not a
                # failure: the dangling 'started' row records the pause.
                raise
            except AgentStageFailure as failure:
                audit.record_stage_failed(state["run_id"], name, failure.classification)
                progress.phase_change(name, "failed")
                raise
            except (ValueError, MutationConflictError):
                # Never blindly retried (plan section 37): contradictory
                # evidence, invalid workbook structure, rule failures.
                audit.record_stage_failed(state["run_id"], name, "deterministic")
                progress.phase_change(name, "failed")
                raise
            except Exception:
                # Environment problems (a deleted answers file, a full
                # disk) still deserve a classified stage row; kills are
                # BaseException and pass through, leaving the dangling
                # 'started' row that marks an interrupted entry.
                audit.record_stage_failed(state["run_id"], name, "unclassified")
                progress.phase_change(name, "failed")
                raise
            audit.record_stage_finished(state["run_id"], name)
            progress.phase_change(name, "completed")
            return {"phase": name, **update}

        return node

    def degrade(state, stage_name, failure):
        # Fail-soft (plan section 37): retries are exhausted, the
        # stage's output degrades, and the run continues into the
        # UNRESOLVED / human-review pipeline.
        audit.record_stage_degraded(state["run_id"], stage_name, failure.classification)
        progress.emit(
            f"{stage_name} did not complete after retries; continuing degraded."
        )

    def init(state):
        progress.emit(f"Registering run {state['run_id']} in the audit store...")
        audit.record_run_started(state["run_id"], inputs)

    def prepare_workspace(state):
        progress.emit("Copying inputs into the workspace...")
        workspace.copy_inputs(inputs)
        if inputs.scoping_answers is not None:
            return {"scoping_answers_path": str(workspace.scoping_answers_md)}

    def build_manifest_node(state):
        manifest = build_manifest(workspace.input_sources)
        workspace.manifest_json.write_text(manifest.model_dump_json(indent=2))
        progress.emit(f"Building file manifest... {len(manifest.files)} files found")
        return {"manifest_path": str(workspace.manifest_json)}

    def outline_workbook(state):
        # Sheet names, column letters, and the template's top rows are
        # facts about the file, read deterministically so the scoping
        # agent never guesses a column letter (ADR 0032).
        outline = build_outline(workspace.input_workbook / inputs.workbook.name)
        workspace.workbook_outline_json.write_text(outline.model_dump_json(indent=2))
        progress.emit(f"Outlining workbook... {len(outline.sheets)} sheets found")
        return {"workbook_outline_path": str(workspace.workbook_outline_json)}

    def claude_scope(state):
        progress.emit("Starting scoping pass...")
        result = run_agent(
            state,
            "CLAUDE_SCOPE",
            "scoping",
            workspace.filler_outputs / "scoping.json",
            ScopingResult,
        )
        questions = ScopingQuestions(questions=result.questions)
        workspace.scoping_questions_json.write_text(questions.model_dump_json(indent=2))
        workspace.scoping_questions_md.write_text(
            render_scoping_questions_md(questions)
        )
        # Pre-created template the user edits before resuming. Skipped
        # when answers were pre-provided: PREPARE_WORKSPACE already put
        # them at this path and the run will not pause, so writing the
        # template here would destroy them.
        if inputs.scoping_answers is None:
            workspace.scoping_answers_md.write_text(
                render_scoping_answers_template(questions)
            )
        progress.emit(
            f"Scoping complete: {len(result.workbook_schema.sheets)} sheets,"
            f" {len(questions.questions)} questions"
        )
        return {"scoping_questions_path": str(workspace.scoping_questions_json)}

    def load_schema(state):
        # The schema comes from the scoping pass, so the contract check
        # that gated its retry has already validated it; this node stores
        # the canonical form every later stage reads. The review policy is
        # read from the workspace copy so a resumed run never depends on
        # the original path (ADR 0014).
        progress.emit("Loading workbook schema and review policy...")
        scoping = ScopingResult.model_validate_json(
            (workspace.filler_outputs / "scoping.json").read_text()
        )
        # The schema's own validators cannot see the workbook, so a sheet
        # the agent invented would only surface as an openpyxl KeyError
        # deep inside WRITE_DRAFT. Check it against the outline instead.
        outline = WorkbookOutline.model_validate_json(
            workspace.workbook_outline_json.read_text()
        )
        present = {sheet.name for sheet in outline.sheets}
        missing = [
            sheet.name
            for sheet in scoping.workbook_schema.sheets
            if sheet.name not in present
        ]
        if missing:
            raise ValueError(
                f"workbook schema names sheets the workbook does not have: {missing};"
                f" the workbook has {sorted(present)}"
            )
        workspace.workbook_schema_json.write_text(
            scoping.workbook_schema.model_dump_json(indent=2)
        )
        policy_yaml = (
            workspace.review_policy_yaml
            if workspace.review_policy_yaml.is_file()
            else None
        )
        policy = load_review_policy(policy_yaml)
        # Moved here from the engine's pre-run gate: the schema only
        # exists now, so this is the first moment the operator's strict
        # fields can be checked against it.
        check_strict_fields(policy, scoping.workbook_schema)
        workspace.review_policy_json.write_text(policy.model_dump_json(indent=2))
        return {"schema_path": str(workspace.workbook_schema_json)}

    def await_scoping_answers(state):
        # First execution pauses here; on resume the node re-runs from
        # the top and interrupt() returns immediately, so the agent-free
        # answer intake below happens exactly once.
        interrupt({"answers_path": str(workspace.scoping_answers_md)})
        if not workspace.scoping_answers_md.is_file():
            raise FileNotFoundError(
                f"scoping answers file not found: {workspace.scoping_answers_md}"
            )
        text = workspace.scoping_answers_md.read_text()
        audit.record_event(
            state["run_id"],
            "scoping_answers_received",
            {
                "path": "artifacts/scoping_answers.md",
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            },
        )
        progress.emit("Scoping answers received.")
        return {"scoping_answers_path": str(workspace.scoping_answers_md)}

    def claude_fill(state):
        progress.emit("Starting Filler...")
        # The scoping answers are an explicit Filler input (plan
        # section 20), recorded relative to the workspace root.
        answers_path = Path(state["scoping_answers_path"])
        (workspace.filler_outputs / "inputs.json").write_text(
            json.dumps(
                {"scoping_answers_path": str(answers_path.relative_to(workspace.root))},
                indent=2,
            )
        )
        # Contract validation happens here because it gates the lenient
        # retry; rule validation stays in the VALIDATE node (guardrail
        # 49.11 as amended by ADR 0016).
        raw_path = workspace.filler_outputs / "extraction.json"
        run_agent(state, "CLAUDE_FILL", "filler", raw_path, ExtractionResult)
        progress.emit("Filler complete.")
        return {"extraction_path": str(raw_path)}

    def schema_from(state):
        return WorkbookSchema.model_validate(
            json.loads(Path(state["schema_path"]).read_text())
        )

    def load_extraction(state):
        return ExtractionResult.model_validate(
            json.loads(Path(state["extraction_path"]).read_text())
        )

    def validate(state):
        progress.emit("Validating proposals...")
        extraction = load_extraction(state)
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
        progress.emit(
            f"Validation complete: {len(extraction.proposals)} proposals,"
            f" {len(rejections)} rejected"
        )
        return {"extraction_path": str(workspace.extraction_json)}

    def write_draft(state):
        progress.emit("Writing draft workbook...")
        extraction = load_extraction(state)
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

        write_explorers(state)

        progress.emit(f"Draft written: {len(applied)} cells populated")
        return {"draft_xlsx_path": str(workspace.draft_xlsx)}

    def read_artifact_items(path, key):
        if not path.is_file():
            return []
        return json.loads(path.read_text())[key]

    def explorer_review_cycle(state):
        run = audit.get_run(state["run_id"])
        finished_stages = [
            stage["finished_at"]
            for stage in audit.list_stages(state["run_id"])
            if stage["finished_at"] is not None
        ]
        review_timestamp = max(finished_stages, default=run["started_at"])
        return {
            "review_date": review_timestamp.split("T", 1)[0],
            "findings": read_artifact_items(workspace.review_json, "findings"),
            "decisions": read_artifact_items(workspace.revision_json, "decisions"),
            "verdicts": read_artifact_items(workspace.re_review_json, "verdicts"),
            "unresolved": read_artifact_items(workspace.unresolved_json, "cells"),
            "revision_mutations": audit.list_applied_mutations(
                state["run_id"], "revision"
            ),
        }

    def write_explorers(state, version_suffix="", include_review_cycle=False):
        progress.emit(f"Rendering review explorer (EN/ZH){version_suffix and ' v2'}...")
        schema = schema_from(state)
        provenance = json.loads(workspace.provenance_json.read_text())
        handoff = json.loads(workspace.handoff_json.read_text())
        manifest = Manifest.model_validate(
            json.loads(Path(state["manifest_path"]).read_text())
        )
        data = build_explorer_data(
            workspace.draft_xlsx,
            schema,
            provenance,
            handoff,
            manifest,
            explorer_review_cycle(state) if include_review_cycle else None,
        )
        targets = {
            "": (workspace.review_explorer_html, workspace.review_explorer_zh_html),
            "_v2": (
                workspace.review_explorer_v2_html,
                workspace.review_explorer_zh_v2_html,
            ),
        }[version_suffix]
        version = version_suffix.lstrip("_")
        for path, lang in zip(targets, ("en", "zh"), strict=True):
            path.write_text(render_explorer_html(data, lang, version=version))

    def run_agent(state, stage, role, raw_output_path, model):
        # Lenient retries (plan section 37): a failed process, a raised
        # invocation, or contract-violating output re-invokes the agent
        # up to twice. Contract validation gates the retry here; rule
        # validation stays in its deterministic node and is never
        # retried. KeyboardInterrupt (a kill) passes straight through.
        failure = None
        for attempt in range(MAX_AGENT_ATTEMPTS):
            if attempt:
                audit.record_stage_retry(state["run_id"], stage)
                # The transient classification would otherwise vanish
                # once the stage eventually succeeds.
                audit.record_event(
                    state["run_id"],
                    "stage_retry",
                    {
                        "stage": stage,
                        "classification": failure[0],
                        "detail": failure[1],
                    },
                )
                progress.emit(f"Retrying {role} (attempt {attempt + 1})...")
            try:
                result = runtimes[role].run(
                    AgentRequest(
                        role=role,
                        workspace_path=str(workspace.root),
                        cancellation=cancellation,
                    )
                )
            # Any runtime exception is a temporary invocation failure
            # by plan section 37; kills are BaseException and pass.
            except Exception as exc:  # noqa: BLE001
                failure = ("invocation_failure", str(exc))
                continue
            if result.status != "ok":
                failure = ("runtime_process_failure", str(result.error))
                continue
            # The most recent attempt that returned output stays on
            # disk, whether or not it validates below.
            raw_output_path.write_text(json.dumps(result.output, indent=2))
            try:
                return model.model_validate(result.output)
            except ValidationError as exc:
                failure = ("schema_validation_failure", str(exc))
        raise AgentStageFailure(role, *failure)

    def load_review(state):
        return ReviewResult.model_validate(
            json.loads(Path(state["review_path"]).read_text())
        )

    def load_revision(state):
        # A degraded revision stage produced no decisions.
        if state.get("revision_path") is None:
            return RevisionResult(decisions=[])
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

    def revision_route(state):
        return routing.route_revision_findings(
            load_review(state).findings, load_extraction(state)
        )

    def codex_review(state):
        progress.emit("Starting Reviewer...")
        # The Reviewer's explicit inputs (plan section 23): the review
        # policy plus workspace-relative paths of everything to verify.
        policy = ReviewPolicy.model_validate_json(
            workspace.review_policy_json.read_text()
        )
        review_targets = routing.plan_review_targets(
            load_extraction(state), schema_from(state), policy
        )

        def relative(path):
            return str(path.relative_to(workspace.root))

        reviewer_inputs = {
            "review_policy": policy.model_dump(),
            "review_targets": review_targets,
            "draft_workbook": relative(workspace.draft_xlsx),
            "extraction": relative(workspace.extraction_json),
            "provenance": relative(workspace.provenance_json),
            "handoff": relative(workspace.handoff_json),
            "manifest": relative(workspace.manifest_json),
            "workbook_schema": relative(workspace.workbook_schema_json),
            "rules_dir": relative(workspace.input_rules),
            "sources_dir": relative(workspace.input_sources),
        }
        (workspace.reviewer_outputs / "inputs.json").write_text(
            json.dumps(reviewer_inputs, indent=2)
        )
        try:
            review = run_agent(
                state,
                "CODEX_REVIEW",
                "reviewer",
                workspace.reviewer_outputs / "review.json",
                ReviewResult,
            )
        except AgentStageFailure as failure:
            degrade(state, "CODEX_REVIEW", failure)
            return {"review_path": None}
        reason = routing.check_finding_cells(review.findings)
        if reason is not None:
            raise ValueError(reason)
        reason = routing.check_review_coverage(review_targets, review.findings)
        if reason is not None:
            raise ValueError(reason)
        workspace.review_json.write_text(review.model_dump_json(indent=2))
        workspace.review_md.write_text(render_review_md(review))
        counts = verdict_counts(review.findings)
        summary = ", ".join(f"{count} {verdict}" for verdict, count in counts)
        progress.emit(f"Review complete: {summary or '0 findings'}")
        return {"review_path": str(workspace.review_json)}

    def claude_revise(state):
        progress.emit("Starting Revision...")
        schema = schema_from(state)
        extraction = load_extraction(state)
        provenance = json.loads(workspace.provenance_json.read_text())

        actionable = revision_route(state)["agent_actionable"]
        flagged_cells = {writer.normalize_cell(finding.cell) for finding in actionable}
        sheet_name = schema.target_sheet().name
        flagged_keys = {cell_key(sheet_name, cell): cell for cell in flagged_cells}
        # Only the allowed context (plan section 27): non-PASS findings,
        # their proposals and provenance, the mutation allowlist, and a
        # pointer to the rules the agent reads via its workspace.
        restricted_inputs = {
            "findings": [
                {**finding.model_dump(), "cell": writer.normalize_cell(finding.cell)}
                for finding in actionable
            ],
            "proposals": {
                writer.normalize_cell(proposal.cell): proposal.model_dump()
                for proposal in extraction.proposals
                if writer.normalize_cell(proposal.cell) in flagged_cells
            },
            "provenance": {
                flagged_keys[entry["cell"]]: entry
                for entry in provenance["entries"]
                if entry["cell"] in flagged_keys
            },
            "mutation_allowlist": routing.derive_revision_allowlist(actionable, schema),
            "rules_dir": "input/rules",
        }
        (workspace.revision_outputs / "inputs.json").write_text(
            json.dumps(restricted_inputs, indent=2)
        )

        try:
            revision = run_agent(
                state,
                "CLAUDE_REVISE",
                "revision",
                workspace.revision_outputs / "decisions.json",
                RevisionResult,
            )
        except AgentStageFailure as failure:
            degrade(state, "CLAUDE_REVISE", failure)
            return {"revision_path": None}
        reason = routing.check_decisions(actionable, revision.decisions)
        if reason is not None:
            raise ValueError(reason)
        workspace.revision_json.write_text(revision.model_dump_json(indent=2))
        actions = action_counts(revision.decisions)
        progress.emit(
            "Revision complete: "
            + ", ".join(f"{count} {action}" for action, count in actions)
        )
        return {"revision_path": str(workspace.revision_json)}

    def apply_allowed_revisions(state):
        progress.emit("Applying authorized revisions...")
        revision = load_revision(state)
        schema = schema_from(state)
        sheet = schema.target_sheet()
        actionable = revision_route(state)["agent_actionable"]

        draft = writer.open_draft(workspace.draft_xlsx)

        def read_current(cell_ref):
            return writer.read_cell(draft, sheet.name, cell_ref)

        def find_prior(cell_ref, source_ref):
            return audit.find_applied_mutation(
                state["run_id"], sheet.name, cell_ref, "revision", source_ref
            )

        mutations, decision_by_ref = routing.compose_revision_mutations(
            revision.decisions, actionable, sheet, read_current, find_prior
        )

        allowlist = Allowlist(routing.derive_revision_allowlist(actionable, schema))
        outcomes = apply_mutations(
            workspace.draft_xlsx, mutations, schema, allowlist, audit, state["run_id"]
        )
        rejected = [outcome for outcome in outcomes if outcome.status == "rejected"]
        if rejected:
            reasons = "; ".join(
                f"{outcome.mutation.cell}: {outcome.reason}" for outcome in rejected
            )
            raise ValueError(f"revision mutations were rejected: {reasons}")

        resync_provenance(
            workspace.provenance_json,
            outcomes,
            decision_by_ref,
            state["run_id"],
            runtimes["revision"].name,
        )
        workspace.revision_log_md.write_text(
            render_revision_log_md(revision.decisions, outcomes)
        )
        applied = sum(1 for outcome in outcomes if outcome.status == "applied")
        progress.emit(f"Applied {applied} authorized revisions")

    def codex_rereview(state):
        revision = load_revision(state)
        rebutted = routing.rebutted_cells(revision.decisions)
        progress.emit(f"Starting targeted re-review: {len(rebutted)} rebutted cells...")
        review = load_review(state)
        findings_by_cell = {
            writer.normalize_cell(finding.cell): finding for finding in review.findings
        }
        restricted_inputs = {
            "rebutted": [
                {
                    "finding": findings_by_cell[cell].model_dump(),
                    "decision": next(
                        decision.model_dump()
                        for decision in revision.decisions
                        if writer.normalize_cell(decision.cell) == cell
                        and decision.action == "REBUT"
                    ),
                }
                for cell in rebutted
            ]
        }
        (workspace.reviewer_outputs / "re_review_inputs.json").write_text(
            json.dumps(restricted_inputs, indent=2)
        )

        try:
            result = run_agent(
                state,
                "CODEX_REREVIEW",
                "re_review",
                workspace.reviewer_outputs / "re_review.json",
                ReReviewResult,
            )
        except AgentStageFailure as failure:
            degrade(state, "CODEX_REREVIEW", failure)
            # No verdicts: every rebuttal stays unadjudicated and the
            # routing layer escalates it to human review.
            return {}
        reason = routing.check_re_review_coverage(rebutted, result.verdicts)
        if reason is not None:
            raise ValueError(reason)
        workspace.re_review_json.write_text(result.model_dump_json(indent=2))
        return {"re_review_path": str(workspace.re_review_json)}

    def human_review(state):
        progress.emit("Generating human review artifacts...")
        if state.get("review_path") is None:
            return unreviewed_human_review(state)
        review = load_review(state)
        revision = load_revision(state)
        verdicts = load_verdicts(state)
        human_only = revision_route(state)["human_only"]
        unresolved = routing.collect_unresolved(
            review.findings,
            revision.decisions,
            verdicts,
            human_only=human_only,
        )

        workspace.unresolved_json.write_text(
            json.dumps({"cells": unresolved}, indent=2)
        )

        sheet_name = schema_from(state).target_sheet().name
        draft = writer.open_draft(workspace.draft_xlsx)
        findings_by_cell = {
            writer.normalize_cell(finding.cell): finding for finding in review.findings
        }
        decisions_by_cell = {
            writer.normalize_cell(decision.cell): decision
            for decision in revision.decisions
        }
        verdicts_by_cell = {
            writer.normalize_cell(verdict.cell): verdict for verdict in verdicts
        }

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
        workspace.human_review_md.write_text(render_human_review_md(items))

    def unreviewed_human_review(state):
        # The review stage never completed: every agent-written cell and
        # every still-blank source conflict escalates with agent columns empty.
        provenance = json.loads(workspace.provenance_json.read_text())
        sheet_name = schema_from(state).target_sheet().name
        draft = writer.open_draft(workspace.draft_xlsx)
        review_failure_reason = "the review stage did not complete after retries"
        conflict_reason = "protected source conflict requires human review"

        reasons_by_cell = {}
        for entry in provenance["entries"]:
            entry_sheet, cell_ref = entry["cell"].split("!", 1)
            if entry_sheet != sheet_name:
                continue
            reasons_by_cell[cell_ref] = review_failure_reason
        for proposal in load_extraction(state).proposals:
            if proposal.sheet != sheet_name or proposal.status != "conflict":
                continue
            cell_ref = writer.normalize_cell(proposal.cell)
            if cell_ref is not None:
                reasons_by_cell[cell_ref] = conflict_reason

        items = []
        for cell_ref, reason in reasons_by_cell.items():
            items.append(
                {
                    "cell": cell_ref,
                    "current_value": writer.read_cell(draft, sheet_name, cell_ref),
                    "reviewer": None,
                    "revision": None,
                    "re_review": None,
                    "reason": reason,
                }
            )
        workspace.unresolved_json.write_text(
            json.dumps(
                {
                    "cells": [
                        {"cell": item["cell"], "reason": item["reason"]}
                        for item in items
                    ]
                },
                indent=2,
            )
        )
        workspace.human_review_json.write_text(json.dumps({"items": items}, indent=2))
        workspace.human_review_md.write_text(render_human_review_md(items))

    def finalize(state):
        progress.emit("Finalizing run...")
        write_explorers(state, version_suffix="_v2", include_review_cycle=True)
        shutil.copy2(workspace.draft_xlsx, workspace.final_xlsx)
        audit.record_run_finished(state["run_id"], "completed")
        _write_run_summary(workspace, audit, state["run_id"])

    def route_unresolved(state):
        review = load_review(state)
        revision = load_revision(state)
        human_only = revision_route(state)["human_only"]
        unresolved = routing.collect_unresolved(
            review.findings,
            revision.decisions,
            load_verdicts(state),
            human_only=human_only,
        )
        return "HUMAN_REVIEW" if unresolved else "FINALIZE"

    def route_after_review(state):
        # A degraded review must not pass for all-clear: everything the
        # run wrote goes straight to human review.
        if state.get("review_path") is None:
            return "HUMAN_REVIEW"
        routed = revision_route(state)
        if routed["agent_actionable"]:
            return "CLAUDE_REVISE"
        if routed["human_only"]:
            return "HUMAN_REVIEW"
        return "FINALIZE"

    def route_after_load_schema(state):
        # Pre-provided answers skip the pause only. The scoping pass
        # itself always runs — it is where the schema comes from
        # (ADR 0032, narrowing plan section 20).
        if inputs.scoping_answers is not None:
            return "CLAUDE_FILL"
        return "AWAIT_SCOPING_ANSWERS"

    def route_after_apply(state):
        if routing.rebutted_cells(load_revision(state).decisions):
            return "CODEX_REREVIEW"
        return route_unresolved(state)

    graph = StateGraph(WorkflowState)
    graph.add_node("INIT", stage("INIT", init))
    graph.add_node("PREPARE_WORKSPACE", stage("PREPARE_WORKSPACE", prepare_workspace))
    graph.add_node("BUILD_MANIFEST", stage("BUILD_MANIFEST", build_manifest_node))
    graph.add_node("OUTLINE_WORKBOOK", stage("OUTLINE_WORKBOOK", outline_workbook))
    graph.add_node("CLAUDE_SCOPE", stage("CLAUDE_SCOPE", claude_scope))
    graph.add_node("LOAD_SCHEMA", stage("LOAD_SCHEMA", load_schema))
    graph.add_node(
        "AWAIT_SCOPING_ANSWERS",
        stage("AWAIT_SCOPING_ANSWERS", await_scoping_answers),
    )
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
    graph.add_edge("BUILD_MANIFEST", "OUTLINE_WORKBOOK")
    graph.add_edge("OUTLINE_WORKBOOK", "CLAUDE_SCOPE")
    graph.add_edge("CLAUDE_SCOPE", "LOAD_SCHEMA")
    graph.add_conditional_edges(
        "LOAD_SCHEMA",
        route_after_load_schema,
        {
            "AWAIT_SCOPING_ANSWERS": "AWAIT_SCOPING_ANSWERS",
            "CLAUDE_FILL": "CLAUDE_FILL",
        },
    )
    graph.add_edge("AWAIT_SCOPING_ANSWERS", "CLAUDE_FILL")
    graph.add_edge("CLAUDE_FILL", "VALIDATE")
    graph.add_edge("VALIDATE", "WRITE_DRAFT")
    graph.add_edge("WRITE_DRAFT", "CODEX_REVIEW")
    graph.add_conditional_edges(
        "CODEX_REVIEW",
        route_after_review,
        {
            "CLAUDE_REVISE": "CLAUDE_REVISE",
            "HUMAN_REVIEW": "HUMAN_REVIEW",
            "FINALIZE": "FINALIZE",
        },
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

    return graph.compile(checkpointer=checkpointer)


def _write_run_summary(workspace, audit, run_id):
    run = audit.get_run(run_id)
    stage_lines = [
        f"| {entry['stage']} | {entry['status']} | {entry['started_at']} |"
        f" {entry['finished_at'] or ''} | {entry['retry_count']} |"
        f" {entry['failure'] or ''} |"
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
            f"- Task: {run['task']}",
            f"- Rules: {run['rules_path'] or 'none'}",
            "",
            "## Stages",
            "",
            "| Stage | Status | Started | Finished | Retries | Failure |",
            "| --- | --- | --- | --- | --- | --- |",
            *stage_lines,
            "",
        ]
    )
    workspace.run_summary.write_text(summary)
