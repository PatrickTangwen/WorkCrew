# Kleister-Charity benchmark inputs

Benchmark inputs for the WorkCrew engine (ticket #13, plan section
42), adapted from the public Kleister-Charity dataset
(https://github.com/applicaai/kleister-charity, dev-0 split).

## Layout

- `source/<doc>/report.txt` - the dataset's best OCR text layer
  (`text_best`) for one charity annual report; one folder per
  document, one workbook row per folder.
- `source/<doc>/register_extract.txt` - synthetic conflicting income
  copy injected into a few folders to exercise the
  conflict -> UNRESOLVED -> human-fallback path with known truth.
- `labels.json` - expected value, evidence folder, and
  expected / blank / unresolved status per field per row.
- `workbook_schema.json`, `template.xlsx`, `rules/`,
  `scoping_answers.md` - the run inputs.

The original PDFs (12 GB, git-annex) are deliberately not used: the
dataset's official challenge input is the OCR text, and the engine's
agents read text sources.

## License note

The Kleister-Charity repository declares no explicit license; the
underlying documents are public filings from the UK Charity
Commission register. These inputs are used for internal evaluation
only - do not redistribute the document texts.

## Rebuilding

`workflow build-benchmark --split-dir <dev-0 dir> --output <this dir>`
regenerates everything above deterministically (fixed seed, sorted
inputs). The dev-0 split (`in.tsv.xz`, `expected.tsv`) is downloaded
from the dataset repository.
