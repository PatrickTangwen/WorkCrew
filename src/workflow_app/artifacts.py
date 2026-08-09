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
        workspace = (self.runs_root / run_id).resolve()
        audit_db = workspace / "state" / "audit.sqlite"
        if not workspace.is_relative_to(self.runs_root) or not audit_db.is_file():
            raise RunNotFoundError(run_id)
        return workspace

    def _entries(self, workspace):
        entries = {}
        artifacts_dir = workspace / "artifacts"
        if artifacts_dir.is_dir():
            for path in artifacts_dir.iterdir():
                entry = self._entry(path, workspace)
                if entry is not None:
                    entries[entry.path.name] = entry

        final_xlsx = workspace / "output" / "final.xlsx"
        final_entry = self._entry(final_xlsx, workspace)
        if final_entry is not None:
            entries[final_entry.path.name] = final_entry
        return entries

    def _entry(self, path, workspace):
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
