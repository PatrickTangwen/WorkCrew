"""Deterministic value validators (ticket #4, plan section 17).

check_value(spec, value) returns None when the value passes and a
rejection reason string when it violates the field's deterministic
rules. These run before any workbook write.
"""

import pytest
from pydantic import ValidationError

from workflow_app.rules.deterministic import check_value
from workflow_app.workbook.schema import FieldSpec


def spec(**kwargs):
    return FieldSpec(writable=True, column="A", **kwargs)


# --- type checks ---------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (spec(type="string"), "Healthcare"),
        (spec(type="number"), 42),
        (spec(type="number"), 3.14),
        (spec(type="boolean"), True),
        (spec(type="id"), "PRJ-0001"),
    ],
)
def test_matching_types_pass(field, value):
    assert check_value(field, value) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (spec(type="string"), 42),
        (spec(type="string"), True),
        (spec(type="number"), "42"),
        (spec(type="number"), True),  # bool must not pass as number
        (spec(type="number"), False),
        (spec(type="boolean"), "true"),
        (spec(type="boolean"), 1),
        (spec(type="id"), 7),
    ],
)
def test_type_violations_are_rejected(field, value):
    assert check_value(field, value) is not None


# --- controlled vocabulary ----------------------------------------------


def test_vocabulary_member_passes():
    field = spec(type="controlled_vocabulary", values=["Healthcare", "Education"])
    assert check_value(field, "Healthcare") is None


def test_vocabulary_non_member_is_rejected():
    field = spec(type="controlled_vocabulary", values=["Healthcare", "Education"])
    reason = check_value(field, "Sorcery")
    assert reason is not None and "vocabulary" in reason


def test_vocabulary_without_values_cannot_even_be_declared():
    # Fail-closed at load time: the schema layer rejects the spec itself.
    with pytest.raises(ValidationError):
        spec(type="controlled_vocabulary")


def test_vocabulary_non_string_is_rejected():
    field = spec(type="controlled_vocabulary", values=["1"])
    assert check_value(field, 1) is not None


# --- id pattern ----------------------------------------------------------


def test_id_matching_pattern_passes():
    field = spec(type="id", pattern=r"^PRJ-\d{4}$")
    assert check_value(field, "PRJ-2026") is None


def test_id_pattern_violation_is_rejected():
    field = spec(type="id", pattern=r"^PRJ-\d{4}$")
    reason = check_value(field, "PRJ-26")
    assert reason is not None and "pattern" in reason


def test_id_without_pattern_accepts_any_string():
    assert check_value(spec(type="id"), "anything goes") is None


def test_id_pattern_must_match_whole_not_just_prefix():
    field = spec(type="id", pattern=r"PRJ-\d{4}")
    assert check_value(field, "PRJ-2026-extra") is not None


# --- date format ---------------------------------------------------------


def test_date_matching_default_iso_format_passes():
    assert check_value(spec(type="date"), "2026-08-08") is None


def test_date_with_custom_format_passes():
    field = spec(type="date", date_format="%d/%m/%Y")
    assert check_value(field, "08/08/2026") is None


@pytest.mark.parametrize("value", ["2026-13-45", "08/08/2026", "yesterday", 20260808])
def test_date_violations_are_rejected(value):
    assert check_value(spec(type="date"), value) is not None


# --- clearing ------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        spec(type="string"),
        spec(type="number"),
        spec(type="date"),
        spec(type="id", pattern=r"^X$"),
        spec(type="controlled_vocabulary", values=["A"]),
    ],
)
def test_none_clears_any_field_type(field):
    # Clearing a cell is always type-safe; CLEAR semantics arrive with #6.
    assert check_value(field, None) is None
