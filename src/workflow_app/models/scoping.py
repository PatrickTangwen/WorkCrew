"""Scoping question contracts (plan section 20).

The scoping pass returns only a question list; answers stay free-form
markdown edited by the user, so no answer contract exists.
"""

from pydantic import BaseModel, ConfigDict


class ScopingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str


class ScopingQuestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[ScopingQuestion]
