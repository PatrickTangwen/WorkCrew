# Archived prompts

This directory keeps prompt history outside the runtime prompt package.
Archived prompts are references only and must not be loaded by runtime role
mappings.

- `legacy-practicum-prompts/` contains the original dataset-specific manual
  prompts for the earlier `7) Practicum Courses` task.
- `legacy-runtime-prompts/` contains superseded, formerly version-controlled
  WorkCrew prompt variants that are no longer mapped to runtime roles.

The authoritative active prompt set is the set of filenames referenced by
`src/workflow_app/runtimes/claude_code.py` and
`src/workflow_app/runtimes/codex.py`.
