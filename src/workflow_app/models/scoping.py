"""Scoping question contracts (plan section 20).

The scoping pass returns only a question list; answers stay free-form
markdown edited by the user, so no answer contract exists.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ScopingOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str


class ScopingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    type: Literal["text", "single_select", "multi_select", "confirm"] = "text"
    options: list[ScopingOption] | None = None


class ScopingQuestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[ScopingQuestion]
