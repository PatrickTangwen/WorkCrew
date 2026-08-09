# WorkCrew

WorkCrew is a controlled document-to-workbook workflow that keeps semantic
agent judgments separate from deterministic validation, mutation, and audit
records.

## Language

**Proposal status**:
The outcome of extracting one target cell: proposed, not found, ambiguous, or
conflicting. Status owns absence and uncertainty semantics.
_Avoid_: Result state, confidence state

**Confidence level**:
An ordinal low, medium, or high assessment of the evidence supporting a
proposed value. It is not a probability; non-proposed outcomes have no
confidence level.
_Avoid_: Confidence score, confidence percentage
