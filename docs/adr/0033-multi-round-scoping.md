# ADR 0033: Scoping asks in rounds, and answers carry notes

Date: 2026-08-10

Extends ADR 0032.

## Context

The scoping pass asked once. An operator who needed to qualify an answer had
nowhere to put the qualification, and the pass had no way to follow up on it.

The first live run showed both halves of the gap. The pass offered an option
reading "A different mapping applies — I will specify in a follow-up"; the
operator chose it; there was no follow-up, and no field in which to specify.
The mapping stayed unknown, and the extraction correctly marked those cells
ambiguous — a right answer to a question that should never have been left open.

## Decisions

### Every answer may carry a free-text note

`ScopingAnswer` is `{value, note}` and replaces the bare value in
`ResumeRunRequest.answers`. The note is prose with no contract of its own; the
transcript renders it under its answer and the next round reads it as part of
that answer.

The UI offers the note box on choice questions only. A `text` question's
control is already free prose, and a second box beside it would only make the
operator wonder which one counts.

This also changes what the pass should offer: escape-hatch options like
"other" or "I will specify later" are now wrong, because the note is that
escape hatch and the next round is where the follow-up happens.

### AWAIT_SCOPING_ANSWERS routes back to CLAUDE_SCOPE

The pass re-runs per round, reads the transcript of everything answered so
far, and decides for itself whether anything is still open. It returns the
**whole schema** each round, not a patch, so an answer that changes a
vocabulary or a column's writability is reflected in what the run then uses.
Freezing the schema after round one would make later rounds pure Q&A and
strip the loop of its point.

`CLAUDE_SCOPE` sets `scoping_pending` when it wants the operator; the router
reads only that flag, so pre-provided answers, nothing-to-ask, and
rounds-exhausted all converge on one condition.

### Three rounds reach the operator, then the run continues

`MAX_SCOPING_ROUNDS = 3`. An agent that keeps asking must not hold an operator
— or a live-agent budget — indefinitely. Continuing beats failing: unanswered
questions become ambiguous proposals that the review cycle already surfaces,
whereas failing discards everything the run has already paid for. The cap
firing is recorded as a `scoping_rounds_exhausted` audit event naming the
questions that went unanswered.

### The answers file is a cumulative transcript

`artifacts/scoping_answers.md` gains a `## Round N` section per round instead
of being overwritten. Both intake paths converge on it: the pass appends a
placeholder section, the CLI operator edits it in place, and the UI's
structured answers replace that last section. Earlier rounds are never
touched, because they are the pass's own memory of what it already knows.

## Consequences

- The resume API is a breaking change: `answers` values are objects, not bare
  values.
- `FakeAgentRuntime` accepts a list of outputs per role, replayed one per call
  with the last repeating. A single fixture would repeat its questions every
  round and stall a run at the pause until the cap. The sequence lives in the
  runtime object, so it restarts in a new process: the CLI's fake selects its
  step by command (`run` asks, `resume` does not), and tests that resume in a
  fresh runtime pass an explicit nothing-left-to-ask fixture. Live runtimes are
  unaffected — a real pass reads the transcript.
- The UI store no longer short-circuits a "ready" question load. Every pause is
  a new round, and skipping the fetch left the form showing the previous
  round's questions.

## Follow-up amendment: round identity is structured state

`artifacts/scoping_questions.json` records the current `round` and an opaque
`placeholder_token` alongside its questions. The resume API uses the token's
machine-only marker to replace the open transcript section instead of parsing
headings in the editable Markdown file. `scoping_answers.md` remains the
cumulative human/agent transcript, but it is not the source of workflow round
identity or placeholder location.
