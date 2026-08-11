# ADR 0037: Task images, and runs named by their operator

Date: 2026-08-10

## Context

Two things the operator could not express. A task description was text only,
so a screenshot of the workbook layout or a diagram of the intended row
mapping had to be described in prose. And a run was identified by
`20260810-215131-7d550b` — a timestamp and six random characters, which say
nothing about what the run was.

## Decision

### Images belong to the task description

An image pasted into the task field is part of the operator's statement of
intent, so it travels with it rather than as a separate input:

- A pasted image has no file on the operator's disk, so it reaches the server
  as content (base64, capped at 12 MB per request, restricted to
  png/jpeg/gif/webp) and is materialized exactly once, into
  `input/task_images/`.
- The workspace names the files (`task-image-<n>.<ext>`, numbered by paste
  order). Clipboard file names are not trustworthy input for a path.
- `input/task.md` ends with the list of attached images. An image nobody is
  told to open is an image nobody reads, and `task.md` is what the prompts
  already point every role at.
- Claude roles read them from the workspace. Codex roles get them via
  `codex exec --image`: the read-only sandbox lets Codex open the file, but
  only an attached image is actually seen.
- The CLI takes the same input as files (`--task-image PATH`, repeatable):
  an operator at a terminal already has files, not a clipboard.

### The operator may name the run

The run id is a directory name, a URL segment and a SQLite key at once, so it
stays an ASCII slug: `<name-or-source-folder>-<MMDD-HHMM>`, with `-2`, `-3`
appended if that is taken. An optional Run name leads it; unnamed runs are
named by the source folder.

A name written entirely in non-Latin script slugifies to nothing and falls
back to the source folder, then to a generic stem. Carrying such a name into
the id would mean betting on NFC/NFD normalization surviving every filesystem
and URL it travels through; the display name would have to live outside the
id for that, which is not worth a schema change today.

## Consequences

The task can now carry what a screenshot says in one glance, and the run list
reads as a list of jobs rather than of timestamps. The source folder is
copied into the workspace as before; images are the one input that exists
only inside the run, so re-running the same task means pasting them again.
