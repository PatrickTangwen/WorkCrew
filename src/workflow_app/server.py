"""Local web server for the WorkCrew browser UI."""

import errno
import socket
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from workflow_app.progress import emit

UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8470
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


def bind_available_socket(host=UI_HOST, starting_port=DEFAULT_UI_PORT):
    """Reserve the first available TCP port at or above ``starting_port``."""
    for port in range(starting_port, 65536):
        selected = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        selected.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            selected.bind((host, port))
        except OSError as exc:
            selected.close()
            if exc.errno == errno.EADDRINUSE:
                continue
            raise
        selected.listen()
        return selected

    raise RuntimeError(f"No available port at or above {starting_port}")


def create_app(static_dir=DEFAULT_STATIC_DIR, require_frontend=False):
    """Create the FastAPI app, mounting the production frontend when present."""
    static_dir = Path(static_dir)
    index = static_dir / "index.html"
    if require_frontend and not index.is_file():
        raise FileNotFoundError(
            f"Frontend build not found at {index}. Run `pnpm build` in frontend/."
        )

    app = FastAPI(title="WorkCrew")
    if index.is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


def run_ui():
    """Serve the built UI on loopback and open it in the default browser."""
    app = create_app(require_frontend=True)
    with bind_available_socket() as selected:
        host, port = selected.getsockname()
        url = f"http://{host}:{port}"
        emit(f"WorkCrew UI available at {url}")
        webbrowser.open_new_tab(url)

        config = uvicorn.Config(app, host=host, port=port)
        uvicorn.Server(config).run(sockets=[selected])
