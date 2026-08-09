# WorkCrew frontend

React + TypeScript single-page application for the local WorkCrew web UI.

## Development

Install dependencies and run the Vite development server with hot module
replacement:

```bash
pnpm install
pnpm dev
```

In a second terminal at the repository root, start the FastAPI backend with
Python hot reload:

```bash
uv run uvicorn workflow_app.server:create_app \
  --factory --reload --host 127.0.0.1 --port 8470
```

The Vite server and the FastAPI backend run independently during development.

## Production build

```bash
pnpm typecheck
pnpm lint
pnpm build
```

The production build is written to `../src/workflow_app/static/`. From the
repository root, `uv run workflow ui` serves those generated assets on
`127.0.0.1`, starting at port 8470.
