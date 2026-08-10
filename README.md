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

### Local web UI

Build the React frontend, then launch the production-mode local server:

```bash
cd frontend
pnpm install
pnpm build
cd ..
uv run workflow ui
```

`workflow ui` binds only to `127.0.0.1`, starting at port 8470 and advancing
to the next available port when necessary. Pass `--port`, for example
`uv run workflow ui --port 9000`, to choose a different starting port. For
frontend development with HMR, run `pnpm dev` in `frontend/`. Run the FastAPI
backend with Python hot reload in a second terminal:

```bash
uv run uvicorn workflow_app.server:create_app \
  --factory --reload --host 127.0.0.1 --port 8470
```
