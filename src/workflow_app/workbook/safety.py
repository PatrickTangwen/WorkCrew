"""Mutation allowlist (plan section 28).

Cells are identified as "<sheet>!<CELL>"; the cell part is normalized
to upper case so authorization cannot be dodged by case games.
"""


class Allowlist:
    def __init__(self, cells):
        self._cells = {self._normalize(entry) for entry in cells}

    @staticmethod
    def _normalize(entry):
        sheet, _, cell = entry.rpartition("!")
        return f"{sheet}!{cell.upper()}"

    def permits(self, sheet, cell_ref):
        return f"{sheet}!{cell_ref.upper()}" in self._cells
