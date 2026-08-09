# 0014 — Scoping pause, checkpointing, and resume semantics

Status: accepted
Date: 2026-08-08
Ticket: #7 (pre-extraction scoping pause and resume)

## Decisions

### Checkpoint database is state/checkpoints.sqlite

Plan section 30 mandates SqliteSaver; section 35 lists state/ contents
without naming the checkpoint file. It lives at `state/checkpoints.sqlite`
beside audit.sqlite, one database per run, thread id = run id. The
engine resolves the workspace root at both entries so checkpointed
state never encodes the launch working directory — a run started with a
relative `--runs-root` resumes correctly from anywhere.

### "scoping" is a runtime role key; raw output stays under filler/

Section 20 defines scoping as the Filler's first invocation, so there
is no `agent_outputs/scoping/` directory (section 35) — the raw output
lands in `agent_outputs/filler/scoping_questions.json`. The runtime
adapter still receives a distinct role key `"scoping"`, because the two
invocations need different prompts/fixtures; role keys name invocation
kinds, directories name actors (both Claude roles map to one runtime in
the live adapters, mirroring the Codex pair in #11).

### ScopingQuestions contract is minimal

Section 18 defines no scoping contract. `ScopingQuestion` carries only
`id` and `question` (extra="forbid", like every contract): ids give the
markdown rendering and the answers template stable anchors. Question
topics (row granularity, mapping, completeness, conventions) are prompt
content for #10, not structure. Answers stay free-form markdown edited
by the user — no answer contract exists; the extraction pass consumes
the file itself.

### The interrupt node re-runs on resume; scope and await are split

LangGraph re-executes the interrupted node from the top on resume, so
CLAUDE_SCOPE (agent call, artifacts) and AWAIT_SCOPING_ANSWERS (bare
interrupt + answer intake) are separate nodes: the scoping agent runs
exactly once. On resume the await node verifies the answers file
exists, records a `scoping_answers_received` audit event (workspace-
relative path + sha256 — the file is the artifact; the audit trail
anchors it, per section 36's structured-data-only rule), and publishes
`scoping_answers_path` into state.

### Interrupted stage entries stay as dangling 'started' rows

The stage wrapper records `started` before the node body, so the pause
leaves an unfinished AWAIT_SCOPING_ANSWERS row and the resumed entry
adds a second one. `record_stage_finished` now completes only the
newest unfinished row, leaving earlier dangling rows in place as the
faithful record of interrupted entries (previously it would have
back-filled every unfinished row). #9's crash-resume produces the same
pattern.

### Run status: paused → running → terminal

Pausing sets the runs row to `paused` (status only — no finished_at);
resumption flips it back to `running` before the graph is re-entered,
because the pause is consumed at that point and a mid-resume failure
must not leave a false "waiting for answers" fact. FINALIZE still
records the terminal status. The runs table gained a
`scoping_answers_path` column so a resumed process reconstructs the
full RunInputs (section 36: configuration).

### Resume does not re-validate original input paths

From CLAUDE_FILL onward the run consumes only the copies inside the
workspace; the original source/rules/workbook paths recorded in the
audit store are reconstructed for their names, not re-checked for
existence. Resume preconditions are instead the workspace directory,
the audit run row, and the checkpoint database — each missing one
raises a distinct FileNotFoundError before any graph work starts.

### An empty scoping question list still pauses

Section 20 pauses unconditionally after the scoping pass; no
skip-on-empty branch was added. The only way to skip the pause is the
documented one: pre-provided answers at run start, which route
LOAD_SCHEMA → CLAUDE_FILL directly (neither scoping node appears in
the stage history).
