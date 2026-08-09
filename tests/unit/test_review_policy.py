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
    assert policy.strict_fields == []
    assert policy.low_confidence_threshold == 0.60
    assert policy.medium_confidence_threshold == 0.85
    assert policy.high_confidence_sampling_per_record == 2


def test_loads_the_plan_example_shape(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        "review:\n"
        "  strict_fields:\n"
        "    - Project ID*\n"
        "  low_confidence_threshold: 0.5\n"
        "  medium_confidence_threshold: 0.9\n"
        "  high_confidence_sampling_per_record: 3\n"
    )
    policy = load_review_policy(path)
    assert policy.strict_fields == ["Project ID*"]
    assert policy.low_confidence_threshold == 0.5
    assert policy.medium_confidence_threshold == 0.9
    assert policy.high_confidence_sampling_per_record == 3


def test_partial_policy_keeps_defaults(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("review:\n  strict_fields: [Notes]\n")
    policy = load_review_policy(path)
    assert policy.strict_fields == ["Notes"]
    assert policy.medium_confidence_threshold == 0.85


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
    "low,medium",
    [(0.9, 0.6), (0.6, 0.6), (-0.1, 0.85), (0.6, 1.5)],
)
def test_rejects_misordered_thresholds(tmp_path, low, medium):
    path = tmp_path / "policy.yaml"
    path.write_text(
        "review:\n"
        f"  low_confidence_threshold: {low}\n"
        f"  medium_confidence_threshold: {medium}\n"
    )
    with pytest.raises(ValueError, match="thresholds"):
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
