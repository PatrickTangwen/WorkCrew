# 0022 — Kleister-Charity benchmark adaptation and metric semantics

Status: accepted
Date: 2026-08-09
Ticket: #13 (benchmark evaluation)

## Context

Plan section 42 assumed a benchmark built from manually verified
historical Practicum work; that ground truth does not exist (user
confirmed). Issue #13's comment (2026-08-09) records the replacement:
the public Kleister-Charity dataset, adapted to the engine's
one-folder-one-row shape. This ADR records the adaptation decisions
and the exact metric semantics the harness implements.

## Decisions

### Documents are the dataset's OCR text layer, not the PDFs

Each benchmark folder holds `report.txt` — the dataset's `text_best`
layer. The original PDFs (12 GB via git-annex, largely scanned) are
deliberately not used: the Kleister challenge's official model input
IS this OCR text, and the engine's agents read text sources. The TSV
escaping is inverted exactly (`\n` and `\t` only; raw OCR backslashes
survive untouched).

### Deterministic stratified sample: 28 full + 8 partial, 40k cap

From dev-0 (440 documents), eligibility requires `text_best` ≤ 40,000
chars (292 qualify; keeps a full live filler pass within practical
context budgets). A fixed-seed (20260809) sample takes 28 documents
carrying all 8 dataset fields and 8 documents naturally missing at
least one — natural expected-blank labels at ~22% of rows. Folders are
named by the dataset's document stem; rows map to folders in ascending
alphabetical order starting at row 2, pinned by the pre-provided
scoping answers.

### Two derived columns exercise the WorkCrew-specific policies

- `Charity ID*` (constructed, rule in `rules/charity_id.md`):
  `CHA-<registration number>`; ground truth derived deterministically.
- `Income Size Band` (mapped controlled vocabulary, thresholds in
  `rules/income_bands.md`): Small < 250k ≤ Medium < 1M ≤ Large.

### Synthetic conflicts label expected-unresolved cells

Three sampled folders receive a second source
(`register_extract.txt`) stating a deterministically different income
(2·x + 137). Rules declare in-folder sources equally authoritative, so
the correct outcome for the income — and the band derived from it —
is "cannot be determined": labels mark both `unresolved`, expected
final cell state empty, escalation expected.

### Evidence ground truth is folder-scoped

The dataset has no span-level annotations, so `expected evidence` is
the row's folder: provenance coverage counts a filled cell as covered
only when its provenance entry cites a source file from that row's own
folder.

### Comparison normalization

Both label and workbook values normalize before exact comparison:
numbers to two decimals (the dataset's amount convention), dates to
ISO, strings stripped with spaces/colons replaced by underscores (the
dataset's value encoding), compared case-insensitively. Kleister's
leaderboard comparison is case-sensitive raw-string match; the
adaptation already changes the task shape, and for a workbook product
letter-case is presentation, not content.

### Metric definitions (acceptance criteria, made precise)

Over labeled cells only (the Notes column is unlabeled):

- **field_accuracy**: expected-status cells whose final value matches.
- **missed_data_rate**: expected-status cells left blank.
- **unsupported_fill_rate**: blank-status cells that ended up filled.
- **provenance_coverage**: filled labeled cells with folder-correct
  evidence.
- **review_true_positive_rate**: wrong draft cells (wrong value,
  unsupported fill, or a confident fill of a conflicted field) that
  received a non-PASS finding — recall over wrong cells.
- **review_false_positive_rate**: correct draft cells that received a
  non-PASS finding.
- **revision_correctness**: ACCEPT/FIX/CLEAR decisions on labeled
  cells whose cell ended label-correct (for unresolved-status cells
  only an empty end state counts as correct).
- **unresolved_count**: cells in `unresolved.json`.
- **expected_unresolved_escalated** (supplementary): known-conflict
  cells that were escalated.
- **web_evidence_percentage**: `external_web` evidence entries over
  all provenance evidence entries.

Draft values come from the filler's applied audit mutations (replays
add no rows, so they are exactly the reviewed draft). Ratios carry
numerator and denominator; an empty denominator reports `None`, never
a fake zero.

Plan §42's subagent/web on-off comparison grid is not automated in
this ticket — the harness scores one run at a time, and the grid is a
matter of running it per configuration. To make that manual grid
possible from artifacts alone, `evaluation.json` records the run's
overall duration and per-stage durations from the audit store
("runtime"); token/usage figures stay in the adapters' own log files
in the run workspace (plan §38 records usage only "when available").

### Recorded artifacts

`workflow evaluate` writes `evaluation.json` + `evaluation.md` into
the run's `artifacts/`; `--record-baseline <path>` copies the JSON to
a committed location (`benchmark/baselines/`, naming convention in its
README). The benchmark inputs under `benchmark/kleister/` are
committed (840 KB) so the baseline stays comparable even if the
upstream dataset changes; the license note lives in the benchmark
README (no explicit upstream license; public UK Charity Commission
filings; internal evaluation only). Rebuilds are byte-identical
including `template.xlsx`: the builder pins the workbook's docProps
and zip-entry timestamps (reproducible-build convention) because
openpyxl otherwise stamps both with the wall clock.
