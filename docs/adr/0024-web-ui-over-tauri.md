# 0024 — Web UI instead of Tauri desktop application

Status: accepted (amends plan §4/§7/Milestone 9: replaces Tauri +
React + TypeScript with a FastAPI + React + TypeScript local web
application)
Date: 2026-08-09
Ticket: #15

## Context

Plan sections 4, 7, and Milestone 9 specify a Tauri + React +
TypeScript desktop application as the V2 frontend. During the V2
spec design session, the user evaluated the trade-offs between a
native desktop application and a local web UI:

- **Development cost.** Tauri adds a Rust layer (IPC bridge,
  permission model, sidecar configuration) and a packaging/
  distribution problem (bundling Python + two agent CLIs without
  credentials). The web UI eliminates both.
- **User profile.** Target users already have Python, Claude Code,
  and Codex installed. Launching a browser from a CLI command is
  zero friction for this audience.
- **Time to ship.** Estimated 2–3 weeks for the web UI vs 4–6 weeks
  for Tauri, primarily due to the Rust layer and packaging.

## Decisions

### Local web application replaces Tauri

The V2 frontend is a FastAPI backend serving a React + TypeScript
SPA. The CLI gains a `workflow ui` subcommand that starts the server
and opens the browser. No Rust, no native installer, no sidecar
protocol.

### Development / production split

Development: Vite dev server (with HMR) + FastAPI run independently.
Production: Vite builds static assets into `src/workflow_app/static/`;
FastAPI mounts them via `StaticFiles`; `workflow ui` is the single
entry point.

### Engine contract unchanged

The web server calls the same `run_workflow` / `resume_workflow`
entry points as the CLI. No engine API changes are required for the
delivery-format decision itself. (Scoping-question schema extension
and progress callback injection are separate, UI-driven changes
recorded in the spec issue.)

## Implementation note — 2026-08-09 (#17)

The run-creation API must return its run ID before the engine thread
finishes, while the original engine entry point generated that ID
internally. `run_workflow` therefore accepts an optional, keyword-only
`run_id`; callers that omit it retain the original behavior. This
supersedes only the no-signature-change part of the decision above.
The server still calls the same engine entry point, and workflow state
and execution semantics remain unchanged.
