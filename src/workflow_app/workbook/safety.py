"""Mutation allowlist (plan section 28).

Cells are identified as "<sheet>!<CELL>"; the cell part is normalized
to upper case so authorization cannot be dodged by case games.
"""


def cell_key(sheet, cell):
    """The canonical "<sheet>!<CELL>" identity used across artifacts."""
    return f"{sheet}!{cell.upper()}"


class Allowlist:
    def __init__(self, cells):
        self._cells = set()
        for entry in cells:
            sheet, _, cell = entry.rpartition("!")
            self._cells.add(cell_key(sheet, cell))

    def permits(self, sheet, cell_ref):
        return cell_key(sheet, cell_ref) in self._cells
