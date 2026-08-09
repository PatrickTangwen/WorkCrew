# 0018 — Codex adapter invocation and review policy decisions

Status: accepted
Date: 2026-08-09
Ticket: #11 (live Codex runtime: Reviewer and targeted re-review)

## Decisions

### Invocation form

The adapter runs `codex exec --sandbox read-only --output-schema
<file> --output-last-message <file> --skip-git-repo-check --ephemeral
--ignore-user-config` with the run workspace as working directory and
the prompt on stdin. The schema and final-message files live in a
process-scoped temporary directory (both flags take file paths), so
the workspace collects no unaudited scratch files; the final message
is the structured output and lands, via the engine's `run_agent`, in
`agent_outputs/reviewer/` — the adapter records no separate envelope
because, unlike the Claude CLI, codex has no result envelope with
usage metadata beyond that same message.

`--ignore-user-config` mirrors ADR 0017's isolation decision (personal
config must not leak into engine invocations; auth still resolves
through CODEX_HOME). `--ephemeral` keeps codex from persisting session
files outside the workspace. `--skip-git-repo-check` is required
because run workspaces are not git repositories. Roles `reviewer` and
`re_review` map to this one runtime (role keys name invocation kinds,
ADR 0014).

### Contract schemas are normalized to the strict output dialect

OpenAI structured outputs reject pydantic's JSON Schema as-is: every
object must list all of its properties in `required` (optionality is
expressed only through null-type unions, which pydantic already
emits), and every schema needs a `type` — a 400 names each violation.
The adapter therefore applies `strict_schema`: `required` is set to
all properties on every object node, and the empty schema pydantic
emits for a contract `Any` (`current_value`, `recommended_value`)
becomes the concrete cell-value union `string | number | boolean |
null` — workbook cell values are scalars, dates travel as strings.
The pydantic contracts stay vendor-neutral; dialect translation is
runtime-specific invocation and belongs in the adapter (plan
section 31). Verified live: the full ReviewResult schema round-trips.

### Auth: env credentials cleared, auth.json verified, warn-not-fail

`CODEX_API_KEY` and `CODEX_ACCESS_TOKEN` outrank auth.json in the
CLI's resolution order and are cleared from the child environment, so
authentication can only come from `codex login` (plan section 10's
runtime-enforced side). Unlike Claude Code, the mode is verifiable:
the startup diagnostic reads auth.json's `auth_mode` and reports
"ChatGPT subscription (auth.json)" when it is `chatgpt`; anything else
(missing file, api-key mode, unreadable JSON) warns and proceeds.

### Review policy: optional input, defaults, fail-fast cross-check

The policy YAML (plan section 25: top-level `review:` key) is an
optional RunInputs field; when absent the default policy applies —
empty `strict_fields`, the section-18 frozen confidence bands
(0.60 / 0.85), spot-check 2 per record. The engine fails fast before
the workspace exists on malformed YAML, misordered thresholds, and
strict fields the workbook schema does not declare. The file is
copied to `input/review_policy.yaml`; LOAD_SCHEMA stores the
validated canonical form at `artifacts/review_policy.json` (a resumed
run never depends on the original path, ADR 0014); CODEX_REVIEW
embeds it in `agent_outputs/reviewer/inputs.json` together with the
workspace-relative paths of everything the Reviewer verifies (plan
section 23's input list). The runs table gained a
`review_policy_path` column so resume reconstructs the full
RunInputs (section 36: configuration).

### Read-only sandbox wins over the web-access default

Plan section 11 defaults web access ON for all roles, but section 23
pins the Reviewer invocation to `--sandbox read-only`, whose network
restrictions are part of the OS-enforced isolation. The explicit
invocation contract wins: the Reviewer verifies against the archival
sources in the workspace. Revisit if a review task genuinely needs
`external_web` evidence.

### Smoke design: only the Codex side is live

The live review runs against a draft produced by the fake Filler (no
Claude quota), with a deliberately planted error for the Reviewer to
catch; an adaptive revision fixture answers whatever the live review
returns so the run always completes. The re-review trigger is
deterministic: a fake WARN finding rebutted by a fake revision — REBUT
is only legal against WARN (ADR 0013's action table), so relying on
the live review to produce a WARN would make the test flaky. Draft
immutability is asserted by hashing the draft on both sides of each
live call (a wrapper runtime), which pins the check to the agent
invocation rather than to unrelated engine writes. As in ADR 0017,
invalid API credentials are planted in the parent environment so the
live calls prove the clearing.
