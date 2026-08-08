# 0009 — Walking-skeleton structural decisions

Status: accepted
Date: 2026-08-08
Ticket: #2 (walking skeleton)

Numbers 0001–0008 are reserved for the ADRs named in plan section 47;
they will be written as their subject matter lands.

## Decisions

### Modules beyond the plan section 34 layout

- `workflow/engine.py` — `run_workflow()`, the workflow engine entry.
  This is the primary test seam agreed with the user: integration tests
  call it with fake runtimes injected and assert on artifacts only. The
  CLI stays a thin shell; the graph module stays pure graph assembly.
- `workspace.py` — per-run workspace layout and input copying
  (plan sections 12/35 describe the layout but assign it no module).
- `progress.py` — the stderr progress emitter (plan section 33).

### Contracts reject unknown fields (`extra="forbid"`)

Plan section 18 does not specify extra-key handling. The prompts demand
output "conforming exactly" to the schema, so unknown keys are treated
as contract violations. If a live agent emits benign extra keys, that
surfaces as a schema-validation failure and follows the lenient retry
path (plan section 37) rather than being silently dropped.

### Raw agent output lives under `agent_outputs/<role>/`

The Filler's unvalidated structured output is written to
`agent_outputs/filler/extraction.json`. The validated
`artifacts/extraction.json` of plan section 35 is produced by the
VALIDATE pipeline arriving with ticket #5. Raw-vs-validated separation
keeps the audit trail honest about what the agent actually returned.

### CLI `--runs-root` flag

Not in the plan's CLI sketch (section 4). Added so runs can target an
isolated directory (tests, scratch runs) instead of always `./runs`.
