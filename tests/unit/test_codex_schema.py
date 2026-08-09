"""strict_schema normalizes contract schemas to the OpenAI structured-
output dialect (ADR 0018): every object lists all properties as
required, and unconstrained (Any) schemas become the scalar cell-value
union."""

from workflow_app.models.review import ReReviewResult, ReviewResult
from workflow_app.runtimes.codex import strict_schema


def walk_objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield node
        for value in node.values():
            yield from walk_objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_objects(value)


def walk_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_dicts(value)


def test_every_object_requires_all_its_properties():
    for contract in (ReviewResult, ReReviewResult):
        schema = strict_schema(contract.model_json_schema())
        objects = list(walk_objects(schema))
        assert objects
        for node in objects:
            assert node["required"] == sorted(node["properties"])


def test_any_valued_fields_become_the_scalar_cell_union():
    schema = strict_schema(ReviewResult.model_json_schema())
    finding = schema["$defs"]["ReviewFinding"]["properties"]
    for field in ("current_value", "recommended_value"):
        branches = finding[field]["anyOf"]
        assert {"type": ["string", "number", "boolean", "null"]} in branches
    # No unconstrained schema survives anywhere.
    assert all(node != {} for node in walk_dicts(schema))


def test_contract_constraints_are_preserved():
    schema = strict_schema(ReviewResult.model_json_schema())
    finding = schema["$defs"]["ReviewFinding"]
    assert finding["additionalProperties"] is False
    assert set(finding["properties"]["verdict"]["enum"]) == {
        "PASS",
        "WARN",
        "FAIL",
        "UNRESOLVED",
    }
    evidence = schema["$defs"]["Evidence"]
    assert "external_web" in evidence["properties"]["evidence_type"]["enum"]
