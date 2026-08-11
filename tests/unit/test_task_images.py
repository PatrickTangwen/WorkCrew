"""Unit tests for task images (ADR 0037).

A pasted image only helps if it reaches the workspace, gets named in
task.md, and is actually put in front of the agents.
"""

import json
import subprocess

import pytest

from workflow_app.models.review import ReviewResult
from workflow_app.runtimes import codex
from workflow_app.runtimes.base import AgentRequest
from workflow_app.workspace import RunInputs, TaskImage, Workspace, render_task_md

PNG = TaskImage(suffix=".png", data=b"\x89PNG fake")
JPG = TaskImage(suffix=".jpg", data=b"\xff\xd8 fake")


@pytest.fixture
def prepared(tmp_path):
    """A workspace with inputs copied in, including two task images."""
    source = tmp_path / "inbox"
    source.mkdir()
    (source / "brief.txt").write_text("A brief.")
    workbook = tmp_path / "template.xlsx"
    workbook.write_bytes(b"not really a workbook")

    workspace = Workspace(tmp_path / "run")
    workspace.create_layout()
    workspace.copy_inputs(
        RunInputs(
            source=source,
            workbook=workbook,
            task="Fill one row per folder.",
            task_images=(PNG, JPG),
        )
    )
    return workspace


def test_images_land_in_the_workspace_in_paste_order(prepared):
    paths = prepared.task_image_paths()

    assert [path.name for path in paths] == ["task-image-1.png", "task-image-2.jpg"]
    assert paths[0].read_bytes() == PNG.data
    assert paths[1].read_bytes() == JPG.data


def test_more_than_nine_images_keep_their_numeric_paste_order(tmp_path):
    source = tmp_path / "inbox"
    source.mkdir()
    workbook = tmp_path / "template.xlsx"
    workbook.write_bytes(b"x")
    images = tuple(
        TaskImage(suffix=".png", data=f"image-{index}".encode())
        for index in range(1, 12)
    )
    workspace = Workspace(tmp_path / "run")
    workspace.create_layout()
    workspace.copy_inputs(
        RunInputs(
            source=source,
            workbook=workbook,
            task="Read every pasted image in order.",
            task_images=images,
        )
    )

    assert [path.name for path in workspace.task_image_paths()] == [
        f"task-image-{index}.png" for index in range(1, 12)
    ]


def test_task_md_names_the_images_it_was_written_with(prepared):
    task = prepared.task_md.read_text()

    assert "Fill one row per folder." in task
    assert "input/task_images/task-image-1.png" in task
    assert "input/task_images/task-image-2.jpg" in task


def test_a_task_without_images_reads_exactly_as_written():
    # No heading, no pointer to an empty directory.
    assert render_task_md("Fill one row per folder.", []) == "Fill one row per folder."


def test_a_run_with_no_images_leaves_the_directory_empty(tmp_path):
    source = tmp_path / "inbox"
    source.mkdir()
    workbook = tmp_path / "template.xlsx"
    workbook.write_bytes(b"x")
    workspace = Workspace(tmp_path / "run")
    workspace.create_layout()
    workspace.copy_inputs(RunInputs(source=source, workbook=workbook, task="Fill it."))

    assert workspace.task_images_dir.is_dir()
    assert workspace.task_image_paths() == []


def test_codex_attaches_every_task_image_to_the_prompt(prepared, monkeypatch):
    # Codex reads images only when they are attached; the read-only
    # sandbox lets it open the file but not see the picture.
    calls = []

    def fake_run_process(argv, **kwargs):
        calls.append(argv)
        message_file = argv[argv.index("--output-last-message") + 1]
        with open(message_file, "w") as handle:
            json.dump(ReviewResult(findings=[]).model_dump(), handle)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(codex, "run_process", fake_run_process)
    monkeypatch.setattr(codex, "print_auth_diagnostic", lambda: None)

    codex.CodexRuntime().run(
        AgentRequest(role="reviewer", workspace_path=str(prepared.root))
    )

    argv = calls[0]
    attached = [argv[i + 1] for i, item in enumerate(argv) if item == "--image"]
    assert [path.rsplit("/", 1)[-1] for path in attached] == [
        "task-image-1.png",
        "task-image-2.jpg",
    ]


def test_codex_attaches_nothing_when_there_are_no_images(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "run")
    workspace.create_layout()
    calls = []

    def fake_run_process(argv, **kwargs):
        calls.append(argv)
        message_file = argv[argv.index("--output-last-message") + 1]
        with open(message_file, "w") as handle:
            json.dump(ReviewResult(findings=[]).model_dump(), handle)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(codex, "run_process", fake_run_process)
    monkeypatch.setattr(codex, "print_auth_diagnostic", lambda: None)

    codex.CodexRuntime().run(
        AgentRequest(role="reviewer", workspace_path=str(workspace.root))
    )

    assert "--image" not in calls[0]
