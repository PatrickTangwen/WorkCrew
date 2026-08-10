"""Review policy configuration (plan section 25).

Hand-authored YAML controlling review depth: coverage is sampled or full,
strict fields are always verified, confidence levels route directly, and
per-record spot checks cover high-confidence values. The deterministic
routing module turns this configuration into the Reviewer's target ledger.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class ReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage: Literal["sampled", "full"] = "sampled"
    strict_fields: list[str] = []
    high_confidence_sampling_per_record: int = 2

    @model_validator(mode="after")
    def _check_sampling(self):
        if self.high_confidence_sampling_per_record < 0:
            raise ValueError("high_confidence_sampling_per_record must not be negative")
        return self


def load_review_policy(path):
    """Load the policy YAML; no path means the default policy."""
    if path is None:
        return ReviewPolicy()
    text = Path(path).read_text()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"review policy is not valid YAML: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"review"}:
        raise ValueError(
            "review policy must be a mapping with the single top-level"
            f" key 'review' (plan section 25): {path}"
        )
    return ReviewPolicy.model_validate(data["review"])


def check_strict_fields(policy, schema):
    """Fail fast on strict fields the workbook schema does not declare."""
    declared = set(schema.target_sheet().fields)
    unknown = [name for name in policy.strict_fields if name not in declared]
    if unknown:
        raise ValueError(
            f"review policy strict_fields not in the workbook schema: {unknown}"
        )
