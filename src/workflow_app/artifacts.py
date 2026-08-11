"""Discover the supported public artifacts inside one run workspace."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ArtifactType = Literal["html", "md", "xlsx", "json"]
ARTIFACT_FORMATS = {
    ".html": ("html", "text/html"),
    ".md": ("md", "text/markdown"),
    ".xlsx": (
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".json": ("json", "application/json"),
}


class RunNotFoundError(FileNotFoundError):
    pass


class ArtifactNotFoundError(FileNotFoundError):
    pass


def resolve_run_workspace(runs_root, run_id):
    """The workspace one run id names, or a refusal.

    A run exists when it has an audit store; a run id that resolves
    outside the runs root names nothing, whatever it points at.
    """
    root = Path(runs_root).resolve()
    workspace = (root / run_id).resolve()
    if not workspace.is_relative_to(root) or not (
        workspace / "state" / "audit.sqlite"
    ).is_file():
        raise RunNotFoundError(run_id)
    return workspace


@dataclass(frozen=True)
class ArtifactEntry:
    path: Path
    type: ArtifactType
    media_type: str

    def summary(self):
        return {
            "name": self.path.name,
            "type": self.type,
            "size": self.path.stat().st_size,
            "path": str(self.path),
        }


def deliverable_entries(workspace):
    """The public artifacts of one run workspace, keyed by file name.

    One definition serves both the app's artifact list and the export
    into the operator's source folder, so the two can never describe
    different sets of files.
    """
    workspace = Path(workspace).resolve()
    entries = {}
    artifacts_dir = workspace / "artifacts"
    if artifacts_dir.is_dir():
        for path in artifacts_dir.iterdir():
            entry = _entry(path, workspace)
            if entry is not None:
                entries[entry.path.name] = entry

    final_entry = _entry(workspace / "output" / "final.xlsx", workspace)
    if final_entry is not None:
        entries[final_entry.path.name] = final_entry
    return entries


def _entry(path, workspace):
    artifact_format = ARTIFACT_FORMATS.get(path.suffix.lower())
    resolved = path.resolve()
    if (
        artifact_format is None
        or not resolved.is_relative_to(workspace)
        or not resolved.is_file()
    ):
        return None
    kind, media_type = artifact_format
    return ArtifactEntry(resolved, kind, media_type)


class ArtifactCatalog:
    def __init__(self, runs_root):
        self.runs_root = Path(runs_root).resolve()

    def list(self, run_id):
        workspace = self._workspace(run_id)
        artifacts = self._entries(workspace)
        return [artifacts[name].summary() for name in sorted(artifacts)]

    def get(self, run_id, name):
        workspace = self._workspace(run_id)
        try:
            return self._entries(workspace)[name]
        except KeyError as exc:
            raise ArtifactNotFoundError(name) from exc

    def _workspace(self, run_id):
        return resolve_run_workspace(self.runs_root, run_id)

    def _entries(self, workspace):
        return deliverable_entries(workspace)
