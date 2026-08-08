# 0010 — Manifest status checks and the schema config input

Status: accepted
Date: 2026-08-08
Ticket: #3 (source manifest and workbook schema loading)

## Decisions

### `--workbook-schema` is a fourth explicit run input

The plan's CLI sketch (section 4) lists source/workbook/rules only, and
section 16 mandates a hand-authored schema config without saying where
it comes from. It is a core input authored by the user, so it is passed
explicitly rather than discovered by convention inside `rules/`. The
engine validates it before the workspace is created — a malformed or
missing config fails the run before any agent could be invoked.

### Validated schema is stored under `artifacts/`, not copied to `input/`

`artifacts/workbook_schema.json` (plan section 35) is the canonical,
validated form the agents and later stages read. The original config
file is referenced by path in the audit runs table; `input/` keeps the
plan-section-35 shape (sources/rules/workbook only).

### Manifest status checks are container-format checks

UNSUPPORTED comes from the extension allowlist (plan section 3 types).
ENCRYPTED/CORRUPT are determined by deterministic file-format facts,
not content heuristics: open-XML Office files must be zip containers
(ECMA-376 encrypted documents are OLE/CFB wrappers instead — magic
bytes checked directly), and PDFs are parsed with pypdf (new runtime
dependency), whose `is_encrypted` reflects the PDF trailer. Text/CSV/
image files are recorded `ok`; deeper readability is the agents' domain.

### Manifest describes the workspace copy

`build_manifest` runs over `input/sources/` (the copied snapshot), so
hashes describe exactly what agents can read during the run.
