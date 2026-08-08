"""Manifest unit tests (ticket #3, plan section 15).

Every file in the source workspace appears with hash, type, size, and a
status; unreadable-for-agents files are flagged, never silently dropped.
"""

import hashlib
import zipfile

import pypdf
import pytest

from workflow_app.ingestion.manifest import build_manifest

# OLE/CFB container magic: ECMA-376 encrypted Office files use this
# wrapper instead of plain zip.
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def entries_by_path(manifest):
    return {entry.path: entry for entry in manifest.files}


def write_minimal_zip(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", "<x/>")


def write_plain_pdf(path):
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def write_encrypted_pdf(path):
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("secret")
    with path.open("wb") as handle:
        writer.write(handle)


def test_every_file_is_listed_with_hash_type_and_size(tmp_path):
    (tmp_path / "India 2008").mkdir()
    brief = tmp_path / "India 2008" / "brief.txt"
    brief.write_text("Community healthcare delivery project.")
    (tmp_path / "notes.md").write_text("Archive notes.")

    manifest = build_manifest(tmp_path)
    entries = entries_by_path(manifest)

    assert set(entries) == {"India 2008/brief.txt", "notes.md"}
    entry = entries["India 2008/brief.txt"]
    assert entry.sha256 == hashlib.sha256(brief.read_bytes()).hexdigest()
    assert entry.size_bytes == brief.stat().st_size
    assert entry.type == "txt"
    assert entry.status == "ok"
    assert entry.normalized_path is None


def test_unsupported_extension_is_flagged_not_dropped(tmp_path):
    (tmp_path / "archive.zip").write_bytes(b"PK\x03\x04 whatever")
    (tmp_path / "readme.txt").write_text("fine")

    entries = entries_by_path(build_manifest(tmp_path))

    assert entries["archive.zip"].status == "UNSUPPORTED"
    assert entries["readme.txt"].status == "ok"


def test_office_files_zip_ole_and_garbage(tmp_path):
    write_minimal_zip(tmp_path / "plain.xlsx")
    (tmp_path / "locked.xlsx").write_bytes(OLE_MAGIC + b"\x00" * 64)
    (tmp_path / "broken.docx").write_bytes(b"not a container at all")

    entries = entries_by_path(build_manifest(tmp_path))

    assert entries["plain.xlsx"].status == "ok"
    assert entries["locked.xlsx"].status == "ENCRYPTED"
    assert entries["broken.docx"].status == "CORRUPT"


def test_pdf_plain_encrypted_and_garbage(tmp_path):
    write_plain_pdf(tmp_path / "plain.pdf")
    write_encrypted_pdf(tmp_path / "locked.pdf")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.7 then chaos")

    entries = entries_by_path(build_manifest(tmp_path))

    assert entries["plain.pdf"].status == "ok"
    assert entries["locked.pdf"].status == "ENCRYPTED"
    assert entries["broken.pdf"].status == "CORRUPT"


def test_nothing_is_silently_omitted(tmp_path):
    names = ["a.txt", "b.zip", "c.pdf", "d.xlsx", "e.png"]
    for name in names:
        (tmp_path / name).write_bytes(b"x")

    manifest = build_manifest(tmp_path)

    assert sorted(entry.path for entry in manifest.files) == sorted(names)


def test_manifest_is_deterministically_ordered(tmp_path):
    for name in ["z.txt", "a.txt", "m/inner.txt"]:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(name)

    first = [entry.path for entry in build_manifest(tmp_path).files]
    second = [entry.path for entry in build_manifest(tmp_path).files]

    assert first == second == sorted(first)


def test_missing_source_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_manifest(tmp_path / "absent")
