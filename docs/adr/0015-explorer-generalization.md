# 0015 — Review explorer generalization decisions

Status: accepted
Date: 2026-08-08
Ticket: #8 (bilingual review explorer rendering)

The original workflow's explorer hardcoded its workbook: organization
and parent-program columns, folder-to-row assignments, one merged
folder, and a hand-translated Chinese fork. The engine's explorer must
render any target workbook from data it actually has. These are the
generalizations and their consequences.

## Decisions

### Display annotations live in the workbook schema config

`SheetSchema` gained `title_field` (names the row in navigation and
detail) and `overview_fields` (master-table columns); `FieldSpec`
gained `gloss_zh` (ZH label sub-line). All are optional, display-only,
and validated against declared fields; they never affect validation or
mutation. Acceptance criterion 3's "organization, parent program,
issue areas" columns are therefore satisfied *by configuration*: the
hand-authored config for the real Practicum workbook must declare
`title_field` = the organization column and `overview_fields` =
[organization, parent program, issue areas]. Vocabulary values render
as pills wherever `type == "controlled_vocabulary"` — type-driven,
never keyed to a field name — and split into segments only along
declared vocabulary members, so members containing ", " stay whole.

### Folder membership is projected from provenance evidence

A row belongs to every top-level source directory (manifest traversal
order) that any of its provenance evidence cites. Top-level loose
files and non-manifest sources (e.g. external web) create no folder
link; rows with no folder evidence render in a trailing "Ungrouped
rows" group, and manifest folders no row cites stay visible with zero
rows. The overview's folder column shows the row's first evidence
folder in manifest order.

### Merged folders are inferred, and the UI states only the evidence

No contract records the Filler's duplicate-folder merges (plan
section 22 sources findings from handoff.json, which has no duplicates
field). V1 infers: a folder is "merged into" row R when the folder's
entire cited evidence feeds exactly R and R's first-order folder is a
different one. Failure mode: a folder that merely cross-cites one cell
of a row primarily owned by an earlier folder is flagged the same way.
The UI therefore claims only what the data shows — the badge points at
the surviving row ("↦ row N") and the callout reads "all of their
cited evidence feeds this row" — not that the Filler decided a merge.
When a later ticket adds an explicit duplicate/merge declaration to
the Filler outputs, that signal replaces this inference.

### Overview findings are the handoff's attention items

The original explorer's "archival findings" (duplicates, year
contradictions, cohort assignments) were Filler-authored prose. The
engine's counterpart is the handoff's structured attention data:
unreadable sources, ambiguities, source conflicts, and
extra-review recommendations, rendered as callouts in that order.
Instance-specific categories like "year contradiction" arrive as the
text of those items, not as explorer structure.

### Row discovery and the header convention

Rows = draft rows (from `FIRST_DATA_ROW` = 2, row 1 being the header
row the schema config describes columns for) with any schema-column
value, unioned with rows referenced by provenance — so a fully cleared
row stays visible. Row identity is the sheet row number (plan
section 28). The "cells populated" stat is derived from the workbook
being rendered (sum of per-row filled counts), not from the fill-time
handoff figure, so v2 stays exact after revisions change the fill.

### v2 is a pure re-render; no revision-annotation layer

The `_v2` files are the same renderer over the revised draft and
resynced provenance (plan section 22's "matches ... exactly"). The
original explorer's v2 QA badges and revision-summary panel were
process artifacts of the manual workflow and are not part of this
ticket; revision authorship is still visible per cell through the
provenance role.

### One bilingual template, no forked variants

EN and ZH render from one shell with a UI-string table per language
(keys enforced in lockstep by test), ZH-specific CSS injected before
the responsive breakpoint, and identical embedded data. The gloss
sub-lines render only under the ZH document language. Embedded JSON
escapes every "<" so no data value can reach the HTML script-data
tokenizer, and template placeholders substitute in a single pass so
payload content is never rescanned.
