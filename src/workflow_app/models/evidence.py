"""Evidence contract (plan section 18)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file: str
    source_location: str | None = None
    evidence_text: str
    evidence_type: Literal[
        "direct",
        "cross_reference",
        "rule",
        "derived",
        "external_web",
    ]
