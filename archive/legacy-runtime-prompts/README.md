# Legacy runtime prompts

Archived: 2026-08-10

These files were previously stored in `src/workflow_app/prompts/` but are not
referenced by any current runtime role. They are retained for historical
comparison only.

| Archived file | Superseded by |
| --- | --- |
| `filler.md` | `src/workflow_app/prompts/filler_independent.md` |
| `reviewer.md` | `src/workflow_app/prompts/reviewer_independent.md` |
| `revision.md` | `src/workflow_app/prompts/revision_independent.md` |
| `handoff_independent.md` | Deterministic generation in `src/workflow_app/handoff.py` |

The active prompt package contains only runtime-loaded prompts. Reintroducing
one of these files requires an explicit runtime role mapping and matching
contract tests; copying it back into the active directory alone is not
sufficient.
