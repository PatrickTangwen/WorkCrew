from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from workflow_app.audit.db import AuditStore
from workflow_app.server import ServerOptions, create_app
from workflow_app.workspace import RunInputs, Workspace

RUN_ID = "run-artifacts"


def artifact_app(tmp_path):
    runs_root = tmp_path / "runs"
    workspace = Workspace(runs_root / RUN_ID)
    workspace.create_layout()
    inputs = RunInputs(
        source=Path("/inputs/source"),
        workbook=Path("/inputs/template.xlsx"),
        rules=Path("/inputs/rules"),
        workbook_schema=Path("/inputs/workbook-schema.json"),
    )
    audit = AuditStore(workspace.audit_db)
    audit.record_run_started(RUN_ID, inputs)
    audit.record_run_finished(RUN_ID, "completed")
    audit.close()

    (workspace.artifacts / "review_explorer.html").write_text("<h1>Review</h1>")
    (workspace.artifacts / "handoff.md").write_text("# Handoff")
    (workspace.artifacts / "evaluation.json").write_text('{"score": 1}')
    (workspace.artifacts / "debug.log").write_text("not a public artifact")
    workspace.final_xlsx.write_bytes(b"PK\x03\x04workbook")
    app = create_app(
        tmp_path / "missing-static",
        options=ServerOptions(runs_root=runs_root),
    )
    return TestClient(app), workspace


def test_artifact_list_reports_supported_run_outputs(tmp_path):
    client, workspace = artifact_app(tmp_path)

    response = client.get(f"/api/runs/{RUN_ID}/artifacts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "evaluation.json",
            "type": "json",
            "size": 12,
            "path": str((workspace.artifacts / "evaluation.json").resolve()),
        },
        {
            "name": "final.xlsx",
            "type": "xlsx",
            "size": 12,
            "path": str(workspace.final_xlsx.resolve()),
        },
        {
            "name": "handoff.md",
            "type": "md",
            "size": 9,
            "path": str((workspace.artifacts / "handoff.md").resolve()),
        },
        {
            "name": "review_explorer.html",
            "type": "html",
            "size": 15,
            "path": str((workspace.artifacts / "review_explorer.html").resolve()),
        },
    ]


@pytest.mark.parametrize(
    ("name", "content", "content_type", "downloads"),
    [
        ("review_explorer.html", b"<h1>Review</h1>", "text/html; charset=utf-8", False),
        ("handoff.md", b"# Handoff", "text/markdown; charset=utf-8", False),
        ("evaluation.json", b'{"score": 1}', "application/json", False),
        (
            "final.xlsx",
            b"PK\x03\x04workbook",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            True,
        ),
    ],
)
def test_artifact_endpoint_serves_each_supported_file_type(
    tmp_path, name, content, content_type, downloads
):
    client, _ = artifact_app(tmp_path)

    response = client.get(f"/api/runs/{RUN_ID}/artifacts/{name}")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == content_type
    disposition = response.headers.get("content-disposition")
    if downloads:
        assert disposition == f'attachment; filename="{name}"'
    else:
        assert disposition is None


def test_artifact_endpoint_rejects_unknown_names(tmp_path):
    client, _ = artifact_app(tmp_path)

    response = client.get(f"/api/runs/{RUN_ID}/artifacts/missing.md")

    assert response.status_code == 404
    assert response.json() == {"detail": "Artifact not found"}


def test_artifact_list_rejects_symlinked_directory_escape(tmp_path):
    client, workspace = artifact_app(tmp_path)
    for artifact in workspace.artifacts.iterdir():
        artifact.unlink()
    workspace.artifacts.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("not part of the run")
    workspace.artifacts.symlink_to(outside, target_is_directory=True)

    response = client.get(f"/api/runs/{RUN_ID}/artifacts")

    assert response.status_code == 200
    assert [artifact["name"] for artifact in response.json()] == ["final.xlsx"]
