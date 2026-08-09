# 0013 — Review-routing semantics

Status: accepted
Date: 2026-08-08
Ticket: #6 (review, revision, bounded re-review, human fallback)

## Decisions

### UNRESOLVED findings get the FAIL action set

Plan section 27's behavior table lists only FAIL and WARN rows.
UNRESOLVED reviewer findings are non-PASS and reach Revision, so they
need legal actions: {FIX, CLEAR, UNRESOLVED}, same as FAIL. ACCEPT is
excluded (an UNRESOLVED finding carries no endorsed recommendation) and
REBUT is excluded (there is no assessment to rebut).

### note_append requires a primary edit

Plan section 18 describes note_append "used with CLEAR or FIX"; section
28 calls it a companion "alongside its primary cell". check_decisions
therefore rejects note_append on decisions without a primary edit
(allowed: ACCEPT, FIX, CLEAR) — a note on a still-disputed REBUT cell
would editorialize before adjudication.

### Rules reach Revision as a workspace pointer

Section 27 lists "rules relevant to flagged cells" among Revision
inputs. Per section 13, agent boundaries are prompt-instructed and the
agent reads files through its workspace, so the restricted-inputs
artifact carries a `rules_dir` pointer rather than copied rule content.
Prompt-level selection of *relevant* rules lands with #10/#11.

### Renderers live in reports.py; provenance resync in the store

ADR 0009 committed graph.py to pure graph assembly. The markdown
renderings of review, revision log, and human review moved to the new
top-level `reports.py` (the handoff.py precedent), and provenance
resynchronization lives beside build_provenance in
provenance/store.py. Revision-authored provenance entries carry
confidence None — RevisionDecision has no confidence field.

### A rejected revision mutation fails the run loudly

FIX/ACCEPT values pass through the same deterministic safety layer as
fill writes (section 27's FIX trust model: validated, not re-reviewed).
If any revision mutation is rejected there, the run raises instead of
silently dropping the correction; #9's failure classification may relax
this into UNRESOLVED-and-continue.
