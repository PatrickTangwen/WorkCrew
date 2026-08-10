# ADR 0031: Archive inactive prompts outside the runtime package

Date: 2026-08-10

## Context

The prompt package contained both the active independent variants and older
prompt variants that were no longer referenced by either runtime adapter.
Keeping inactive files beside live prompts made filesystem presence look like
runtime activation and allowed tests to continue enforcing obsolete prompt
contracts.

ADR 0017 and ADR 0019 accurately recorded the prompt mappings used when they
were written. Subsequent independent-review work changed the live Filler,
Reviewer, and Revision mappings, and handoff generation became deterministic
Python code.

## Decision

`src/workflow_app/prompts/` contains only prompt files referenced by the
current Claude or Codex runtime role tables:

- `scoping.md`
- `filler_independent.md`
- `reviewer_independent.md`
- `revision_independent.md`
- `re_review.md`

The superseded `filler.md`, `reviewer.md`, `revision.md`, and
`handoff_independent.md` files move to `archive/legacy-runtime-prompts/`.
They remain available as historical records but are not part of the runtime
prompt package.

Prompt contract tests assert that the active prompt directory exactly matches
the union of the two runtime role mappings. Tests no longer enforce content in
archived prompts.

## Consequences

The active prompt directory becomes an unambiguous runtime inventory. Adding a
new prompt file requires mapping it to a runtime role, while removing a role
mapping requires archiving or deleting its prompt deliberately. Historical ADR
statements remain unchanged and are superseded by this decision for the current
runtime mapping.
