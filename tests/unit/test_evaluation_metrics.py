"""Evaluation metric core (ticket #13, plan section 42).

Pure computation over labels + extracted run facts; no workspace IO.
The synthetic scenario covers every metric's numerator and denominator
paths, including the None-when-undefined rule for empty denominators.
"""

from workflow_app.evaluation.labels import BenchmarkLabels
from workflow_app.evaluation.metrics import compute_metrics, normalize_value

# --- value normalization -------------------------------------------------


def test_normalize_blank_values():
    assert normalize_value(None) is None
    assert normalize_value("") is None
    assert normalize_value("   ") is None


def test_normalize_numbers_to_two_decimals():
    assert normalize_value(500000.0) == "500000.00"
    assert normalize_value("500000") == "500000.00"
    assert normalize_value("10348000.00") == "10348000.00"
    assert normalize_value(42) == "42.00"


def test_normalize_strings_dataset_style():
    # The dataset writes values with underscores for spaces/colons;
    # comparison is case-insensitive on both sides.
    assert normalize_value("Havens Christian Hospice") == "havens_christian_hospice"
    assert normalize_value("Havens_Christian_Hospice") == "havens_christian_hospice"
    assert normalize_value("SS0 8HX") == normalize_value("SS0_8HX")
    assert normalize_value("CHA-1022119") == "cha-1022119"


def test_normalize_dates():
    import datetime

    assert normalize_value("2018-07-31") == "2018-07-31"
    assert normalize_value(datetime.date(2018, 7, 31)) == "2018-07-31"
    assert (
        normalize_value(datetime.datetime(2018, 7, 31, tzinfo=datetime.UTC))
        == "2018-07-31"
    )


# --- the metric scenario -------------------------------------------------


def field(cell, expected=None, status="expected"):
    return {"cell": cell, "expected_value": expected, "status": status}


LABELS = BenchmarkLabels.model_validate(
    {
        "benchmark": "kleister-charity",
        "sheet": "Charity Reports",
        "seed": 7,
        "rows": [
            {
                "row": 2,
                "folder": "aaa1",
                "document": "aaa1/report.txt",
                "conflict": None,
                "fields": {
                    "Charity Name": field("B2", "Harbour_Trust"),
                    "Registration Number": field("C2", "1234567"),
                    "Annual Income GBP": field("H2", "500000.00"),
                    "Income Size Band": field("J2", "Medium"),
                },
            },
            {
                "row": 3,
                "folder": "bbb2",
                "document": "bbb2/report.txt",
                "conflict": None,
                "fields": {
                    "Charity Name": field("B3", "Leeds_Aid"),
                    "Annual Income GBP": field("H3", status="blank"),
                    "Income Size Band": field("J3", status="blank"),
                },
            },
            {
                "row": 4,
                "folder": "ccc3",
                "document": "ccc3/report.txt",
                "conflict": {
                    "field": "Annual Income GBP",
                    "file": "register_extract.txt",
                    "value": "1000137.00",
                },
                "fields": {
                    "Charity Name": field("B4", "Zeta_Fund"),
                    "Annual Income GBP": field("H4", status="unresolved"),
                    "Income Size Band": field("J4", status="unresolved"),
                },
            },
        ],
    }
)

FINAL = {
    "B2": "Harbour Trust",
    "C2": "1234567",
    "H2": 500000.0,
    "J2": "Medium",
    "B3": "Leeds Aid",  # fixed by revision
    "H3": None,  # cleared by revision
    "J3": None,
    "B4": "Zeta Fund",
    "H4": 1000137.0,  # confident fill of a conflicted value, never fixed
    "J4": None,
}

DRAFT = {
    "B2": "Harbour Trust",
    "C2": "1234567",
    "H2": 500000.0,
    "J2": "Medium",
    "B3": "Wrong Name",  # wrong draft, flagged and fixed
    "H3": 12345.0,  # unsupported fill, flagged and cleared
    "B4": "Zeta Fund",
    "H4": 1000137.0,  # wrong: conflicted value confidently filled
}


def entry(cell, source_file, evidence_types=("direct",), role="filler"):
    return {
        "cell": f"Charity Reports!{cell}",
        "agent_role": role,
        "evidence": [
            {"source_file": source_file, "evidence_type": kind}
            for kind in evidence_types
        ],
    }


PROVENANCE = [
    entry("B2", "aaa1/report.txt"),
    entry("H2", "aaa1/report.txt", evidence_types=("direct", "external_web")),
    entry("J2", "aaa1/report.txt", evidence_types=("rule",)),
    # C2 has no provenance entry: a coverage miss.
    entry("B3", "bbb2/report.txt", role="revision"),
    entry("B4", "ccc3/report.txt"),
    entry("H4", "ccc3/register_extract.txt"),
]

FINDINGS = [
    {"cell": "B3", "verdict": "FAIL"},  # true positive
    {"cell": "H3", "verdict": "FAIL"},  # true positive (unsupported fill)
    {"cell": "H4", "verdict": "UNRESOLVED"},  # true positive (conflict)
    {"cell": "C2", "verdict": "WARN"},  # false positive on a correct cell
    {"cell": "B2", "verdict": "PASS"},  # PASS findings never count
]

DECISIONS = [
    {"cell": "B3", "action": "FIX"},
    {"cell": "H3", "action": "CLEAR"},
    {"cell": "H4", "action": "UNRESOLVED"},  # not a primary edit
]

UNRESOLVED = ["H4"]


def evaluate():
    return compute_metrics(
        LABELS, FINAL, DRAFT, PROVENANCE, FINDINGS, DECISIONS, UNRESOLVED
    )


def ratio(name):
    metric = evaluate()["metrics"][name]
    return metric["numerator"], metric["denominator"], metric["value"]


def test_field_accuracy_over_expected_cells():
    assert ratio("field_accuracy") == (6, 6, 1.0)


def test_missed_data_rate_over_expected_cells():
    assert ratio("missed_data_rate") == (0, 6, 0.0)


def test_unsupported_fill_rate_over_expected_blank_cells():
    assert ratio("unsupported_fill_rate") == (0, 2, 0.0)


def test_provenance_coverage_requires_evidence_from_the_row_folder():
    # 7 labeled cells end up filled; C2 lacks any provenance entry.
    assert ratio("provenance_coverage") == (6, 7, 6 / 7)


def test_review_true_positive_rate_over_wrong_draft_cells():
    # Wrong drafts: B3, H3 (unsupported), H4 (conflict fill) - all flagged.
    assert ratio("review_true_positive_rate") == (3, 3, 1.0)


def test_review_false_positive_rate_over_correct_draft_cells():
    # Correct drafts: B2 C2 H2 J2 J3 B4 J4; only C2 was flagged.
    assert ratio("review_false_positive_rate") == (1, 7, 1 / 7)


def test_revision_correctness_over_primary_edits():
    # FIX B3 landed the expected value; CLEAR H3 restored the blank.
    assert ratio("revision_correctness") == (2, 2, 1.0)


def test_unresolved_count_and_expected_unresolved_escalation():
    result = evaluate()["metrics"]
    assert result["unresolved_count"] == 1
    escalated = result["expected_unresolved_escalated"]
    assert (escalated["numerator"], escalated["denominator"]) == (1, 2)


def test_web_evidence_percentage_over_all_evidence_entries():
    # 7 evidence entries in provenance, one of type external_web.
    assert ratio("web_evidence_percentage") == (1, 7, 1 / 7)


def test_empty_denominators_yield_none_not_zero():
    empty = BenchmarkLabels.model_validate(
        {
            "benchmark": "kleister-charity",
            "sheet": "Charity Reports",
            "seed": 7,
            "rows": [],
        }
    )
    metrics = compute_metrics(empty, {}, {}, [], [], [], [])["metrics"]
    assert metrics["field_accuracy"]["value"] is None
    assert metrics["review_true_positive_rate"]["value"] is None
    assert metrics["unresolved_count"] == 0


def test_per_cell_detail_records_misses():
    cells = {(item["cell"]): item for item in evaluate()["cells"]}
    conflict_fill = cells["H4"]
    assert conflict_fill["status"] == "unresolved"
    assert conflict_fill["final_correct"] is False
    assert conflict_fill["flagged"] is True
    accurate = cells["B2"]
    assert accurate["final_correct"] is True
    assert accurate["draft_correct"] is True
