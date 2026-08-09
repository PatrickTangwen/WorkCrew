"""Cell value scalar domain (plan section 18).

Workbook cell values are JSON scalars end to end: dates travel as ISO
strings, and openpyxl-native types never cross an agent contract. The
alias replaces the former `Any` fields, so a structured value from a
rogue agent fails contract validation (and is retried) instead of
reaching the workbook layer.
"""

CellValue = str | int | float | bool | None
