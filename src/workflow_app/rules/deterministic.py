"""Hardcoded deterministic value validators (plan section 17).

V1 keeps this rule set small and in Python: type checks, controlled
vocabulary, ID patterns, date formats. Semantic judgments belong to the
agents. check_value returns None on pass, a reason string on violation.
"""

import re
from datetime import datetime

DEFAULT_DATE_FORMAT = "%Y-%m-%d"


def check_value(spec, value):
    if value is None:
        # Clearing a cell is always type-safe.
        return None
    checker = _CHECKERS[spec.type]
    return checker(spec, value)


def _check_string(spec, value):
    if not isinstance(value, str):
        return f"expected a string, got {type(value).__name__}"
    return None


def _check_number(spec, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"expected a number, got {type(value).__name__}"
    return None


def _check_boolean(spec, value):
    if not isinstance(value, bool):
        return f"expected a boolean, got {type(value).__name__}"
    return None


def _check_date(spec, value):
    if not isinstance(value, str):
        return f"expected a date string, got {type(value).__name__}"
    date_format = spec.date_format or DEFAULT_DATE_FORMAT
    try:
        # Format check only — the parsed datetime is discarded, so
        # timezone-awareness is irrelevant here.
        datetime.strptime(value, date_format)  # noqa: DTZ007
    except ValueError:
        return f"date {value!r} does not match format {date_format!r}"
    return None


def _check_id(spec, value):
    if not isinstance(value, str):
        return f"expected an id string, got {type(value).__name__}"
    if spec.pattern is not None and re.fullmatch(spec.pattern, value) is None:
        return f"id {value!r} does not match pattern {spec.pattern!r}"
    return None


def _check_vocabulary(spec, value):
    # The schema layer guarantees vocabulary fields declare values.
    if not isinstance(value, str) or value not in spec.values:
        return f"value {value!r} is not in the controlled vocabulary"
    return None


_CHECKERS = {
    "string": _check_string,
    "number": _check_number,
    "boolean": _check_boolean,
    "date": _check_date,
    "id": _check_id,
    "controlled_vocabulary": _check_vocabulary,
}
