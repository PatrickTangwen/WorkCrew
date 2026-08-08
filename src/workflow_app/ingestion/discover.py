"""Source workspace file discovery."""

from pathlib import Path


def list_files(root):
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"source workspace not found: {root}")
    return sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )
