# ADR 0036: Per-role model and reasoning effort

Date: 2026-08-10

Extends ADR 0020 (pinned models and effort as CLI configuration) and
supersedes its decision that Claude thinking effort is not exposed.

## Context

ADR 0020 put model and effort on the CLI as four runtime-wide flags, and
recorded that Claude thinking effort stayed unexposed because the CLI had no
dependable knob for it. The CLI has since grown `--effort`
(low/medium/high/xhigh/max), so the reason no longer holds.

Two gaps remained. The web UI could not choose at all — the server always
built runtimes from the CLI's defaults — and the choice was runtime-wide, so
raising review depth also raised it for the roles that did not need it.

## Decision

Model and effort are configured **per role**, for the five roles of
`ROLE_RUNTIMES` (scoping, filler, revision on Claude; reviewer, re_review on
Codex). The role-to-runtime mapping stays an engine decision, not an operator
choice.

- `workflow_app.agent_config` is the product configuration layer: role
  runtimes, pinned default models, effort vocabularies, defaults, validation,
  and the options payload. The CLI and the server both read it, so there is
  one place where a default lives. Adapters stay free of product policy — one
  built with no arguments still runs its CLI's own default (plan section 31).
- Claude's default effort is `None` (the CLI's own). Raising it is an
  operator decision, not a silent product change. Codex keeps `high`: review
  depth is deliberate (ADR 0020).
- Model fields are free text with suggestions. Model names change faster than
  this repository; a closed list would reject valid models.
- A selection is validated when the run is requested — unknown role, unknown
  effort, blank model — so a typo fails before the run starts rather than
  when an agent process rejects it mid-run.
- The resolved config is written to `input/agents.json` with the run's other
  inputs. A resume is a fresh process, often a fresh server, and reads it
  back: without it, the second half of a run could silently execute on
  different models than the first. An explicit flag still overrides on
  resume (runtime choice is per-invocation, ADR 0019), so the CLI flags
  default to None rather than to the product default.
- The CLI keeps its runtime-wide flags (now including `--claude-effort`) and
  adds repeatable `--agent-model ROLE=MODEL` / `--agent-effort ROLE=LEVEL`
  overrides, rather than growing ten flags.
- The server serves the same options at `GET /api/agents`; the form renders
  what it is told and sends only what the operator changed.

## Consequences

Review effort can be raised without paying for it on every role, and a run
records what produced it. The cost is a second configuration surface: any new
role or runtime must be added to `agent_config` for the CLI, the server and
the UI to see it — which is the point of having one.
