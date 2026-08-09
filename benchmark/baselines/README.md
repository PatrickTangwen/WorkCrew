# Recorded baselines

Baseline evaluation results land here via
`workflow evaluate ... --record-baseline benchmark/baselines/<name>.json`.

Naming convention: `<benchmark>-<date>-<configuration>.json`, e.g.
`kleister-dev0-2026-08-09-default.json` for the pinned default models
(ADR 0020). Each file is the full `evaluation.json` of one scored run:
metrics with numerators/denominators, per-cell detail, and the run's
stage timings — enough to compare a future run configuration against
it without re-running the original.
