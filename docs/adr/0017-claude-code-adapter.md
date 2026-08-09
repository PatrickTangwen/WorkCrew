# 0017 — Claude Code adapter invocation decisions

Status: accepted
Date: 2026-08-08
Ticket: #10 (live Claude Code runtime: scoping pass and Filler)

## Decisions

### Invocation form and permission mode

The adapter runs `claude --print --output-format json --json-schema
<contract schema>` with the run workspace as the working directory and
the prompt on stdin (avoids argv length limits). The JSON result
envelope's `structured_output` field carries the schema-validated
output; `--json-schema` requires claude CLI >= 2.1.205 (an invalid
schema is a hard CLI error there, silent degradation before).

Headless runs cannot answer permission prompts, so the adapter passes
`--permission-mode bypassPermissions`. This is the plan's section 13
policy expressed in print mode: tool access is deliberately not
restricted (`--allowedTools` unused), READ/WRITE boundaries are
prompt-instructed, and the workspace scoping comes from launching the
process inside the isolated run workspace.

### Personal configuration is excluded from the invocation

The child environment sets `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`. Plan
section 39 makes version-controlled prompt files the agent's
instruction source; without this flag the operator's personal
`~/.claude/CLAUDE.md` (and any project memory) would silently leak
rules — response language, tool habits — into every engine invocation
and into the structured outputs.

### API-billing env vars cleared: ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN

Plan section 10 names `ANTHROPIC_API_KEY`; `ANTHROPIC_AUTH_TOKEN` is
the second env credential the CLI resolves before OAuth and is cleared
for the same reason (never silently fall back to API billing). The
startup diagnostic reports which of the two were present, and always
warns that subscription auth cannot be verified at the CLI level —
warn-not-fail is the plan's stated policy for this known limitation.

### Section 39's prompt checklist is tailored to each invocation's contract

Plan section 39 lists evidence, confidence, and uncertainty policies as
elements of "every prompt". The scoping prompt omits them: its output
contract (`ScopingQuestions`) carries no evidence, confidence, or
status fields, so those policies have nothing to govern in that
invocation. `filler.md` defines the full list; `scoping.md` defines the
elements its contract can express (role, goal, workspace, permissions,
artifacts, output schema, subagent permission).

### Role mapping and failure surface live in the adapter, policy in the engine

The `ROLES` table (role key -> prompt file + output contract) maps
`scoping` and `filler` to this one runtime instance (role keys name
invocation kinds, ADR 0014; `revision` joins in #12). Failure mapping
follows plan section 31 and ADR 0016: a process that ran and failed —
non-zero exit, non-JSON stdout, `is_error` envelope, missing
`structured_output` — returns an error AgentResult
(`runtime_process_failure`); an impossible invocation — unknown role,
missing CLI binary — raises (`invocation_failure`). Contract
validation of the structured output stays in the engine's `run_agent`,
which owns the retry loop. The adapter sets no timeout: a wedged
process is interrupted by the operator and resumed via the existing
kill/resume path (ADR 0016); any fixed limit would be a heuristic that
kills legitimately long fills.

### Result envelope recorded under logs/

Each successful parse writes the full CLI result envelope (usage,
cost, duration, session id — no chain-of-thought) to
`logs/claude_<role>_result.json`, satisfying section 38's "record
high-level runtime usage metadata when available". Last attempt per
role wins, matching the engine's raw-output retention rule.

### Live smoke tests are marker-excluded, and auth clearing is proven live

`pytest -m smoke` runs the live tests; the default run excludes them
via `addopts = "-m 'not smoke'"` (plan section 41: normal CI must not
spend agent quota). Runtime adapters have no unit seam (spec test
decision), so env clearing is verified in the smoke tests themselves:
they plant an intentionally invalid `ANTHROPIC_API_KEY` in the parent
environment, and the live call can only succeed if the adapter removed
it and the CLI's subscription auth took over.
