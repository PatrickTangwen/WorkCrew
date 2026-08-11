"""Unit tests for run id generation.

A run id is a directory name, a URL segment, and a SQLite key at once,
so these pin both halves of the contract: it reads as something, and it
stays safe and unique.
"""

from workflow_app.workflow.engine import SLUG_MAX, new_run_id, slugify


def test_the_operator_name_leads_the_id():
    run_id = new_run_id(name="Charity 2015 review", source="/data/inbox")

    assert run_id.startswith("charity-2015-review-")


def test_the_source_folder_names_an_unnamed_run():
    assert new_run_id(source="/data/Charity Reports").startswith("charity-reports-")


def test_a_name_with_nothing_to_slugify_falls_back():
    # Non-Latin script slugifies to nothing; the source folder, then a
    # generic stem, keep the id readable rather than empty.
    assert new_run_id(name="审查", source="/data/inbox").startswith("inbox-")
    assert new_run_id(name="审查", source="/数据").startswith("run-")


def test_ids_stay_filesystem_and_url_safe():
    run_id = new_run_id(name="../../etc/passwd -- 'DROP TABLE'", source="/data/inbox")

    assert set(run_id) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")
    assert ".." not in run_id
    assert "/" not in run_id


def test_long_names_are_capped():
    assert len(slugify("word " * 40)) <= SLUG_MAX


def test_a_taken_id_gets_the_next_free_suffix(tmp_path):
    first = new_run_id(name="daily", source="/data/inbox", runs_root=tmp_path)
    (tmp_path / first).mkdir()
    second = new_run_id(name="daily", source="/data/inbox", runs_root=tmp_path)
    (tmp_path / second).mkdir()
    third = new_run_id(name="daily", source="/data/inbox", runs_root=tmp_path)

    assert second == f"{first}-2"
    assert third == f"{first}-3"


def test_an_unnamed_run_never_reads_as_none():
    # str(None) slugifies to "none", which would name every unnamed run.
    assert slugify(None) == ""
    assert not new_run_id(source="/data/inbox").startswith("none-")
