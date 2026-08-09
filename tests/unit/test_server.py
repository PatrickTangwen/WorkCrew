import socket

from fastapi.testclient import TestClient

from workflow_app.server import bind_available_socket, create_app


def test_bind_available_socket_increments_past_an_occupied_port():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        starting_port = occupied.getsockname()[1]

        with bind_available_socket("127.0.0.1", starting_port) as selected:
            selected_host, selected_port = selected.getsockname()

    assert selected_host == "127.0.0.1"
    assert selected_port > starting_port


def test_create_app_serves_the_built_spa(tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        '<main id="root">WorkCrew UI is ready</main>'
    )
    (assets_dir / "app.js").write_text("console.log('ready')")

    client = TestClient(create_app(static_dir))

    page = client.get("/")
    asset = client.get("/assets/app.js")
    assert page.status_code == 200
    assert "WorkCrew UI is ready" in page.text
    assert asset.status_code == 200
    assert asset.text == "console.log('ready')"


def test_create_app_starts_without_a_production_frontend(tmp_path):
    client = TestClient(create_app(tmp_path / "missing-static"))

    response = client.get("/")

    assert response.status_code == 404
