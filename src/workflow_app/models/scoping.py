"""Scoping contracts (plan section 20, ADR 0032).

The scoping pass returns the derived workbook schema plus a question
list; answers stay free-form markdown edited by the user, so no answer
contract exists. Emitting the schema through the same structured-output
contract is what makes a malformed schema a retryable agent failure
rather than a crash three stages later.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from workflow_app.workbook.schema import WorkbookSchema


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


class ScopingAnswer(BaseModel):
    """One answer: the typed value, plus whatever the operator wanted to add.

    The note exists because a chosen option is often nearly right. It is
    free prose and carries no contract of its own; the scoping pass reads
    it alongside the value.
    """

    model_config = ConfigDict(extra="forbid")

    value: str | list[str] | bool
    note: str | None = None


class ScopingQuestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[ScopingQuestion]


class ScopingQuestionRound(ScopingQuestions):
    """The questions artifact plus its structured workflow round."""

    round: int
    placeholder_token: str


class ScopingResult(BaseModel):
    """What the scoping invocation must return: the schema and the questions."""

    model_config = ConfigDict(extra="forbid")

    workbook_schema: WorkbookSchema
    questions: list[ScopingQuestion]
