# ADR 0038: Claude Code uses auto permission mode

Status: accepted
Date: 2026-08-11

Supersedes the permission-mode decision in ADR 0017. The rest of ADR 0017
remains in force.

## Context

ADR 0017 chose `bypassPermissions` because a headless `claude --print` run
cannot answer permission prompts. That mode also disables the CLI's own
guardrails, which is broader than WorkCrew needs. Claude Code now provides an
`auto` permission mode that grants the access required by a headless run
without stopping for a prompt and without bypassing those guardrails.

## Decision

The Claude Code adapter passes `--permission-mode auto`. It still does not use
an `--allowedTools` allowlist: role READ/WRITE boundaries remain prompt-defined,
and the process still starts inside the isolated run workspace. The adapter's
invocation test pins this policy because no other WorkCrew layer controls the
CLI argument.

## Consequences

Headless runs remain non-blocking while retaining the CLI's own permission
guardrails. WorkCrew must continue to verify the locally supported Claude Code
permission modes when it raises the minimum CLI version.
