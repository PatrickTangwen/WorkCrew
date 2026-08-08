# WorkCrew

Local-first document-to-workbook workflow engine. Claude Code fills an Excel
workbook from archival source folders, Codex independently reviews it, Claude
revises, and humans adjudicate the remainder. The application is a thin
deterministic outer harness; Claude Code and Codex are treated as full agent
runtimes.

Authoritative architecture plan: [`project_plan_v3.md`](project_plan_v3.md).
Spec and tickets: GitHub issues (#1 is the spec).

## Usage

```bash
uv run workflow run \
  --source ./source_documents \
  --workbook ./template.xlsx \
  --rules ./rules
```

Each run creates an isolated workspace under `runs/<run_id>/` containing
copied inputs, agent outputs, artifacts, the audit database, and
`run_summary.md`. Original input files are never modified.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
