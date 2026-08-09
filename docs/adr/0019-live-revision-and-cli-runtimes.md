# 0019 — Live Revision role and CLI runtime selection

Status: accepted
Date: 2026-08-09
Ticket: #12 (live Revision role and full live pipeline)

## Decisions

### Revision joins the Claude runtime's role table

`revision` maps to `revision.md` + `RevisionResult` in
`ClaudeCodeRuntime.ROLES` — the third invocation kind on the one
Claude runtime (ADR 0014). The adapter needed no other change: the
engine's `claude_revise` node already assembles the restricted inputs
artifact (non-PASS findings, matching proposals and provenance, the
mutation allowlist) at `agent_outputs/revision/inputs.json`, which the
prompt reads as its briefing.

### Confirmation-bias mitigation lives in the prompt

Plan section 27 mandates the debiasing text in the Revision *prompt*
and supplies its wording; `revision.md` carries it verbatim (role
independence, evidence-over-authorship, REBUT reserved for concrete
counter-evidence). The acceptance criterion's "present in the Revision
inputs" is satisfied there: the prompt is an input of every Revision
invocation (ROLES maps the role key to it), and duplicating the text
into inputs.json would create a second divergence-prone copy. The
prompt also encodes the per-verdict action table (ADR 0013) — in
particular that a WARN finding without a `recommended_value` leaves
REBUT as the only legal action, and that CLEAR must carry a
`note_append` preserving the cleared cell's context (user story 21).

### The CLI runs live by default; fake is an explicit switch

`--runtimes {live,fake}` (default `live`) on both `run` and `resume`.
Live wires scoping/filler/revision to one `ClaudeCodeRuntime` and
reviewer/re_review to one `CodexRuntime` — the full section-31 role
map. `fake` replays the walking-skeleton fixtures (plan section 32)
for wiring checks and for the CLI tests, which must never spend agent
quota; it is an existing capability made selectable, not a new mode.
The runtimes choice is per-invocation and not persisted: a run started
live can be resumed with fakes and vice versa — the checkpoint records
progress, not runtime identity.

### Smoke design: structurally forced actions over hoped-for verdicts

The revision-slice test fakes the Filler and Reviewer so the live
Revision's inputs are exact:

- a WARN finding without a recommendation makes REBUT the only action
  `routing.check_decisions` accepts, so the single live re-review
  round is exercised deterministically — the test never depends on a
  live model choosing to rebut;
- a FAIL finding over two genuinely conflicting sources (the brief
  vs. a planted annual-report note) sets up CLEAR + `note_append` as
  the textbook-correct response, which the test then verifies
  end-to-end into the final workbook's Notes cell.

The full-live-run test drives all five roles live through the
pause/resume cycle on the clean sample workspace, with path-independent
assertions (unconditional artifacts plus the per-route families,
provenance-to-workbook sync, PASS cells matching their original
proposals) because live verdicts legitimately vary between runs. The
PASS-freeze check exempts the Notes column: it is the note_append
companion channel, authorized for flagged rows regardless of its own
verdict (plan section 28) — a live run that FIXes a missed cell may
legitimately append to a PASS-verdict Notes cell.
