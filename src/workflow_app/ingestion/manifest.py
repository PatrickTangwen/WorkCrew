"""Source manifest (plan section 15).

Records every file in the source workspace with hash, type, size, and a
status. Files agents may not be able to inspect are flagged with
UNSUPPORTED / ENCRYPTED / CORRUPT — never silently omitted. Status
checks are deterministic container-format checks, not content heuristics:
Office open-XML files must be zip containers (their ECMA-376 encrypted
form is an OLE/CFB wrapper instead), and PDFs are parsed with pypdf.
"""

import hashlib
import zipfile
from pathlib import Path
from typing import Literal

import pypdf
from pydantic import BaseModel, ConfigDict

from workflow_app.ingestion.discover import list_files

SUPPORTED_TYPES = {
    "txt",
    "md",
    "docx",
    "pptx",
    "xlsx",
    "csv",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
}

OFFICE_ZIP_TYPES = {"docx", "pptx", "xlsx"}

# OLE/CFB container magic (ECMA-376 encrypted Office documents).
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str
    type: str
    size_bytes: int
    status: Literal["ok", "UNSUPPORTED", "ENCRYPTED", "CORRUPT"]
    # Reserved for a future Docling normalization layer (plan section 15).
    normalized_path: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[ManifestEntry]


def build_manifest(root):
    root = Path(root)
    entries = [_build_entry(root, relative) for relative in list_files(root)]
    return Manifest(files=entries)


def _build_entry(root, relative):
    path = root / relative
    file_type = path.suffix.removeprefix(".").lower()
    return ManifestEntry(
        path=relative,
        sha256=_sha256(path),
        type=file_type,
        size_bytes=path.stat().st_size,
        status=_status(path, file_type),
    )


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _status(path, file_type):
    if file_type not in SUPPORTED_TYPES:
        return "UNSUPPORTED"
    if file_type in OFFICE_ZIP_TYPES:
        return _office_status(path)
    if file_type == "pdf":
        return _pdf_status(path)
    return "ok"


def _office_status(path):
    if zipfile.is_zipfile(path):
        return "ok"
    with path.open("rb") as handle:
        if handle.read(len(OLE_MAGIC)) == OLE_MAGIC:
            return "ENCRYPTED"
    return "CORRUPT"


def _pdf_status(path):
    try:
        reader = pypdf.PdfReader(path)
        encrypted = reader.is_encrypted
    except Exception:  # noqa: BLE001 — any parse failure of a malformed PDF
        # is exactly what CORRUPT means; pypdf's exception surface for
        # hostile input is not a stable contract.
        return "CORRUPT"
    return "ENCRYPTED" if encrypted else "ok"
