# Legacy practicum prompts

Archived: 2026-08-10

These four previously uncommitted root-level prompts document the manual
workflow used for the earlier `7) Practicum Courses` fill task. They are
retained as historical references only and are not loaded by the WorkCrew
runtime.

## Contents

| File | Historical purpose | Why it is not runtime-active |
| --- | --- | --- |
| `Filler_agent.md` | Filled the fixed Practicum Courses sheet from named program folders. | It is benchmark-specific and predates the structured proposal contract. |
| `Handoff_prompt.md` | Asked the Filler to write a manual Markdown review handoff. | WorkCrew now builds `handoff.json` and `handoff.md` deterministically in Python. |
| `QA_agent.md` | Reviewed the fixed Practicum Courses dataset using manual tiers. | The Reviewer runtime uses the generic structured independent-review contract. |
| `Revision_prompt.md` | Applied findings from a dated practicum QA report. | The Revision runtime uses generic structured decisions and deterministic mutations. |

## Active workflow mapping

- Claude `scoping` -> `src/workflow_app/prompts/scoping.md`
- Claude `filler` -> `src/workflow_app/prompts/filler_independent.md`
- Codex `reviewer` -> `src/workflow_app/prompts/reviewer_independent.md`
- Claude `revision` -> `src/workflow_app/prompts/revision_independent.md`
- Codex `re_review` -> `src/workflow_app/prompts/re_review.md`
- Handoff generation -> `src/workflow_app/handoff.py`

The archived prompts must not be added to runtime role mappings. If one is
used for comparison or future prompt research, treat its fixed workbook,
folder, taxonomy, and date assumptions as historical task context rather than
general workflow requirements.
