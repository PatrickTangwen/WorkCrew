# 0020 — Pinned models and review effort as CLI configuration

Status: accepted
Date: 2026-08-09
Follow-up to: #12 (requested directly by the user)

## Context

The adapters originally passed no model selection, so every engine
invocation ran on whatever each CLI resolved as its default. Two
consequences surfaced after the first full live run: a CLI upgrade or
account-default change would silently shift engine behavior (the
Claude roles were running `claude-opus-4-6[1m]` purely by account
default), and ADR 0018's `--ignore-user-config` isolation had the side
effect of discarding the operator's own `~/.codex/config.toml` model
choice (`gpt-5.6-sol`), silently falling back to the CLI's built-in
default (`gpt-5.5`) with `reasoning effort: none`.

## Decisions

### Models and effort are explicit CLI configuration with pinned defaults

`--claude-model` (default `claude-opus-4-6[1m]`), `--codex-model`
(default `gpt-5.6-sol`), and `--codex-effort` (default `high`, the
full codex vocabulary none/minimal/low/medium/high/xhigh/max/ultra)
on both `run` and `resume`. The defaults live as constants in the CLI
(the product configuration layer), not in the adapters — an adapter
constructed without arguments still runs the CLI's own default, which
keeps the adapters free of product policy (plan section 31). A `[1m]`
suffix on the Claude model selects the 1M-context variant (official
CLI syntax; stripped before the provider call).

### Review effort defaults to high

Review depth is deliberate configuration, not accident (plan
section 25); `reasoning effort: none` — what the isolation flag
silently produced — is the wrong default for an adversarial verifier.
`high` matches the review roles' intelligence-sensitivity; operators
can lower it per run for cost.

### Claude thinking effort is not exposed

Claude Code has no stable CLI knob for it: the current models use
adaptive thinking (the model calibrates depth itself), and the legacy
`MAX_THINKING_TOKENS` env var targets fixed-budget models. Exposing a
flag that maps to nothing dependable would be configuration theater;
revisit if the CLI grows a real effort control.

### Codex CLI version note

`gpt-5.6-sol` requires codex-cli >= 0.147 (0.142 rejects it with a
400 naming the version); the dev machine was upgraded via
`codex update`. Verified live: model and effort overrides accepted,
all flags the adapter uses unchanged.
