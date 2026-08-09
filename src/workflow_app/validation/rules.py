"""Proposal-level deterministic validation (plan sections 20, 25).

Constructed fields (values assembled by naming format) and mapped fields
(values chosen from a controlled vocabulary or judgment scale) are capped
at medium confidence so they always land in prioritized review sampling.
Value-level checks (type, vocabulary, pattern, date) stay in the mutation
safety layer.
"""

from workflow_app.workbook import writer


def is_confidence_capped(field):
    return field.value_kind is not None or field.type == "controlled_vocabulary"


def check_proposal(proposal, schema):
    sheet = schema.sheet_named(proposal.sheet)
    if sheet is None:
        return f"sheet {proposal.sheet!r} is not described by the workbook schema"

    field = sheet.fields.get(proposal.column_name)
    if field is None:
        return f"no field named {proposal.column_name!r} in sheet {proposal.sheet!r}"

    cell_ref = writer.normalize_cell(proposal.cell)
    if cell_ref is None:
        return f"malformed cell address {proposal.cell!r}"

    column = writer.column_of(cell_ref)
    if field.column != column:
        return (
            f"cell {cell_ref} is in column {column}, but field"
            f" {proposal.column_name!r} is declared in column {field.column}"
        )

    row = int(cell_ref[len(column) :])
    if row != proposal.row:
        return f"cell {cell_ref} does not match the declared row {proposal.row}"

    if is_confidence_capped(field) and proposal.confidence == "high":
        kind = field.value_kind or "mapped"
        return (
            f"{kind} field {proposal.column_name!r} is capped at medium"
            f" confidence, got {proposal.confidence}"
        )

    return None
