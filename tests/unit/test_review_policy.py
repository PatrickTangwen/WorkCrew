import json

import pytest

from workflow_app.review_policy import (
    ReviewPolicy,
    check_strict_fields,
    load_review_policy,
)
from workflow_app.workbook.schema import load_workbook_schema

SCHEMA_CONFIG = {
    "sheets": [
        {
            "name": "Sheet",
            "target": True,
            "fields": {
                "Project ID*": {"type": "id", "column": "A", "writable": True},
                "Notes": {"type": "string", "column": "B", "writable": True},
            },
        }
    ]
}


def write_schema(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(SCHEMA_CONFIG))
    return load_workbook_schema(path)


def test_no_path_yields_default_policy():
    policy = load_review_policy(None)
    assert policy.coverage == "sampled"
    assert policy.strict_fields == []
    assert policy.high_confidence_sampling_per_record == 2


def test_full_coverage_is_an_explicit_categorical_mode(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("review:\n  coverage: full\n")

    policy = load_review_policy(path)

    assert policy.coverage == "full"


def test_loads_the_categorical_policy_shape(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        "review:\n"
        "  strict_fields:\n"
        "    - Project ID*\n"
        "  high_confidence_sampling_per_record: 3\n"
    )
    policy = load_review_policy(path)
    assert policy.strict_fields == ["Project ID*"]
    assert policy.high_confidence_sampling_per_record == 3


def test_partial_policy_keeps_defaults(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("review:\n  strict_fields: [Notes]\n")
    policy = load_review_policy(path)
    assert policy.strict_fields == ["Notes"]
    assert policy.high_confidence_sampling_per_record == 2


@pytest.mark.parametrize(
    "text",
    [
        "strict_fields: []\n",  # missing the review: envelope
        "review: {}\nextra: {}\n",  # a second top-level key
        "- just\n- a\n- list\n",
        "",
    ],
)
def test_rejects_wrong_top_level_shape(tmp_path, text):
    path = tmp_path / "policy.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match="top-level"):
        load_review_policy(path)


def test_rejects_invalid_yaml(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("review: [unclosed\n")
    with pytest.raises(ValueError, match="not valid YAML"):
        load_review_policy(path)


def test_rejects_unknown_keys(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("review:\n  spot_checks: 2\n")
    with pytest.raises(ValueError):
        load_review_policy(path)


@pytest.mark.parametrize(
    "legacy_key", ["low_confidence_threshold", "medium_confidence_threshold"]
)
def test_rejects_legacy_numeric_thresholds(tmp_path, legacy_key):
    path = tmp_path / "policy.yaml"
    path.write_text(f"review:\n  {legacy_key}: 0.5\n")
    with pytest.raises(ValueError):
        load_review_policy(path)


def test_rejects_negative_sampling(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("review:\n  high_confidence_sampling_per_record: -1\n")
    with pytest.raises(ValueError, match="negative"):
        load_review_policy(path)


def test_strict_fields_must_exist_in_schema(tmp_path):
    schema = write_schema(tmp_path)
    good = ReviewPolicy(strict_fields=["Project ID*"])
    assert check_strict_fields(good, schema) is None

    bad = ReviewPolicy(strict_fields=["Project ID*", "Parent Program*"])
    with pytest.raises(ValueError, match="Parent Program"):
        check_strict_fields(bad, schema)
