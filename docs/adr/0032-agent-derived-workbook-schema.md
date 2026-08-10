# ADR 0032: The scoping pass derives the workbook schema

Date: 2026-08-10

Supersedes the schema-input decisions in ADR 0010.

## Context

ADR 0010 made `--workbook-schema` a fourth explicit run input: a hand-authored
JSON config describing sheets, writable columns, key fields, controlled
vocabularies, and references. Authoring it was the operator's hardest task and
the least supported: no documentation section, no generator, no validation
command. The only feedback loop was starting a run and reading the failure.

Every writable column, its letter, and its vocabulary had to be transcribed by
hand from the workbook. That transcription is mechanical where it is not a
judgment call, and the run already invokes an agent that reads the workbook.

## Decision

### The schema is part of the scoping pass's structured output

`ScopingResult` is `{workbook_schema, questions}` and replaces
`ScopingQuestions` as the scoping role's contract. Emitting the schema through
the same contract makes a malformed schema a **retryable agent failure**,
handled by the existing lenient-retry policy, rather than a crash three stages
later.

### Run inputs are the source folder, the workbook, and a task description

`RunInputs` drops `rules: Path` and `workbook_schema: Path`, and gains
`task: str`. The task is the operator's own statement of what the run should
produce, written in prose; the scoping pass derives the schema to serve it.

### Rules are optional, and are prose or one text file

Rules stop being a required directory. `rules_text` and `rules_file` are
mutually exclusive and both optional; whichever is given lands at
`input/rules/rules.md`, so no later stage learns which form was used. A run
with no rules leaves `input/rules/` empty, which is a normal state, not an
error.

### Stage order inverts, and the pre-run schema gate is gone

`BUILD_MANIFEST -> OUTLINE_WORKBOOK -> CLAUDE_SCOPE -> LOAD_SCHEMA`.
`LOAD_SCHEMA` now canonicalizes what the agent produced instead of reading a
user file, and `check_strict_fields` moved into it from the engine's pre-run
gate — the schema it checks against only exists after scoping has run.

ADR 0010's guarantee that a malformed schema "fails the run before any agent
could be invoked" **no longer holds, and cannot**: the schema is agent output.
What survives is that no *cell is written* before the schema validates, since
WRITE_DRAFT is downstream of LOAD_SCHEMA.

### Pre-provided scoping answers skip the pause, not the pass

Plan section 20 had pre-provided answers skip `CLAUDE_SCOPE` and
`AWAIT_SCOPING_ANSWERS` alike. The scoping pass now produces the schema, so it
always runs; only the interrupt is skipped. `CLAUDE_SCOPE` correspondingly does
not write the answers template when answers were pre-provided — that write
would destroy them.

### Whether to pause is the scoping agent's call

A pass that returns no questions does not stop the run: the operator would
otherwise face an empty form to submit. `CLAUDE_SCOPE` writes a short
no-questions note in place of the answers template and sets
`scoping_answers_path` itself, which is what routes the run past the interrupt.
`CLAUDE_FILL` reads the answers document unconditionally, so skipping the pause
must never mean skipping the document.

The router therefore branches on `state["scoping_answers_path"]` rather than on
`inputs.scoping_answers`: both ways of already having answers converge on one
condition.

### Column letters are read deterministically, not inferred

`workbook/outline.py` (through the `writer.py` openpyxl isolation layer) emits
`artifacts/workbook_outline.json`: every sheet, and every non-empty cell of its
first rows tagged with its real Excel column letter. The agent maps headers to
types and vocabularies; it never counts columns.

The outline deliberately does **not** name a header row. A template with a
title banner above its headers would make that call wrong, and the agent has
the rows in front of it either way.

### The schema's sheet names are checked against the workbook

`WorkbookSchema`'s own validators cannot see the workbook. `LOAD_SCHEMA` now
rejects a schema naming sheets the workbook does not have — otherwise an
invented sheet name surfaces as an `openpyxl` `KeyError` inside the explorer
renderer, three stages downstream.

### The agent defines its own write allowlist

`writable` and `column` are the source of the mutation allowlist. With the
schema agent-derived, the agent decides which cells any later stage may write.
This was raised with the operator, who chose auto-acceptance over surfacing the
derived schema for confirmation at the existing scoping pause. Recorded here as
a deliberate accepted risk, not an oversight; the pause remains the obvious
place to add confirmation if that judgment changes.

### Contract fields an agent writes must be self-describing

The first live run derived an otherwise good schema but wrote
`"date_format": "YYYY-MM-DD"`. That field is handed straight to
`datetime.strptime`, where every non-`%` character is a literal, so the rule
rejected `2011-07-01`. A human author never hit it because the default is
already `%Y-%m-%d`.

`FieldSpec` now rejects a `date_format` that renders unchanged (no directives)
or fails to round-trip, and the scoping prompt names it a strptime pattern.
The general lesson: a field that used to carry a human's tacit knowledge needs
that knowledge written into the contract once an agent fills it in.

### The first writable row is not in the schema

The same run wrote its first record into row 2 — the header row — because the
mock workbook opens with a banner. Nothing in `SheetSchema` records where data
starts, and the extraction pass takes the row from the **scoping answers**, in
prose.

The chosen fix is prompt-side: the scoping prompt now makes establishing the
row mapping mandatory and tells the pass to state the first writable row and
have the operator confirm it, and the filler prompt forbids proposing a cell
above it. This leaves the failure mode dependent on the agent obeying its
prompt; a `first_data_row` field on `SheetSchema` would make it structural and
checkable, and was deliberately not taken.

## Consequences

- The audit `runs` table replaces `rules_path`/`workbook_schema_path` with
  `task` and a nullable `rules_path`. `_migrate` adds `task` to databases from
  earlier runs so their history stays listable; those runs are **not
  resumable**, since their schema came from a file the new graph never reads.
- **Benchmark reproducibility regresses for live runs.** `build_benchmark`
  still emits `workbook_schema.json`, but it is no longer a run input — it is
  the schema a live scoping pass is *expected* to derive, and the labels'
  column mapping assumes it. The fake-runtime evaluation tests feed it to the
  scoping fixture, so they stay deterministic; a live benchmark run may derive
  a different mapping and score against labels that no longer line up. Closing
  this needs a way to pin a schema for benchmark runs, which is deliberately
  not solved here.
- `--runtimes fake` derives its degenerate schema's target sheet from the
  operator's actual workbook, because that schema is now checked against it.
