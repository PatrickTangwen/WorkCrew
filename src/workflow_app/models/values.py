"""Cell value scalar domain (ADR 0023, amending plan section 18).

Workbook cell values are JSON scalars end to end: dates travel as ISO
strings, and openpyxl-native types never cross an agent contract. The
alias replaces the former `Any` fields: a structured value from a
rogue agent fails contract validation at the agent boundary and is
retried (plan section 37), while persisted artifacts re-validate
against the same contract and fail closed (ADR 0023 records the
pre-change-run consequence).
"""

CellValue = str | int | float | bool | None
