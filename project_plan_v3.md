# Project Plan v3 — Local-First Claude Code + Codex Document-to-Workbook Workflow

> Status: Implementation-ready architecture plan
> Version: 3.1
> Date: 2026-08-08
> v3.1 amendments (2026-08-08, after comparison against the original Cowork "Practicum courses" workflow): REBUT now triggers one bounded targeted re-review round; added pre-extraction scoping pause; added medium-confidence cap for constructed/mapped fields; added `note_append` companion mutation; added deterministic bilingual review-explorer rendering (EN/ZH single-file HTML, regenerated post-revision).
> Supersedes: `project_plan2.md` and `project_plan_v2_amendments.md`
> Process: V2 base plan + adversarial grilling session (29 design-tree decisions)

---

# 1. Executive Summary

Build a **local-first multi-agent document-to-workbook workflow** that automates an existing human-orchestrated process:

```text
Source Documents
      ↓
Claude Code Filler
      ↓
Validated Structured Proposals
      ↓
Deterministic Excel Writer
      ↓
Draft Workbook + Provenance + Handoff
      ↓
Codex Independent Reviewer
      ↓
Claude Code Revision
      ↓
Final Workbook + Audit Trail
```

The core architecture:

> **Claude Code and Codex are treated as full agent runtimes, not as raw LLMs.**

They already provide their own inner agent harness: planning, local file inspection, search/grep, shell/tool execution, context management, and native subagent delegation.

This project MUST NOT rebuild a competing low-level agent harness.

Instead, the application owns only a **thin, deterministic outer workflow harness** responsible for:

- workflow state,
- agent role boundaries,
- input/output contracts,
- workbook mutation safety,
- provenance requirements,
- review/revision routing,
- retries/resume,
- audit logging,
- and termination conditions.

The application controls **what must happen and what outputs are valid**.

Claude Code and Codex control **how they perform their assigned reasoning task internally**.

---

# 2. Problem Being Automated

The original workflow was manually orchestrated by a human:

```text
Human
  ↓
give source files + rules + workbook to Filler
  ↓
Filler populates data
  ↓
Human collects workbook + handoff
  ↓
Human gives all materials to Reviewer
  ↓
Reviewer audits work
  ↓
Human gives review back to Filler
  ↓
Filler fixes / accepts findings
  ↓
Final workbook
```

This project removes that manual orchestration:

```text
User
  ↓
Select source folder + workbook + rules
  ↓
Run
  ↓
Thin Python Workflow Harness
  ├── Claude Code Filler
  ├── deterministic validation/write
  ├── Codex Reviewer
  ├── Claude Code Revision
  └── human fallback when unresolved
  ↓
Final artifacts
```

---

# 3. Product Goal

The user should be able to select:

1. a local source folder containing heterogeneous files,
2. an Excel workbook defining target fields,
3. rule/reference files defining naming and business conventions,

then start the workflow.

Supported source material:

```text
.txt
.md
.docx
.pptx
.xlsx
.csv
.pdf
images when needed
```

The workflow should:

1. inventory the source workspace,
2. load the workbook schema,
3. load deterministic rules,
4. delegate extraction to Claude Code,
5. validate the structured result,
6. safely write the draft workbook,
7. produce cell-level provenance,
8. delegate independent QA to Codex,
9. route findings to Claude Code for bounded revision,
10. generate explicit human-review items if still unresolved,
11. finalize workbook and audit artifacts.

---

# 4. Product Form

## V1 — CLI-first local application

```bash
workflow run \
  --source ./source_documents \
  --workbook ./template.xlsx \
  --rules ./rules
```

```bash
workflow resume \
  --run-id <run_id>
```

The workflow engine must be fully usable without a GUI.

## V2 — Desktop application

After the engine is trustworthy:

```text
Tauri + React + TypeScript
          │
          ▼
 Thin Local Python Workflow Harness
          │
          ▼
 Claude Code + Codex
```

The frontend must not contain core business logic.

CLI and Desktop must call the same Python workflow package.

---

# 5. Core Architectural Principle

There are **two different harness layers**.

## 5.1 Inner Agent Harness — DO NOT BUILD

Claude Code / Codex own this.

```text
Claude Code / Codex
       │
       ├── planning
       ├── file discovery
       ├── local search
       ├── shell/tools
       ├── context management
       ├── iterative agent loop
       └── optional native subagents
```

Do NOT implement a home-grown:

```text
planner agent
file-search agent
research agent manager
tool-selection loop
context compaction engine
subagent scheduler
generic ReAct loop
```

## 5.2 Outer Workflow Harness — REQUIRED

Our Python application owns:

```text
workflow state machine
agent role assignment
task boundaries
input/output schemas
artifact locations
validation
Excel mutation
provenance
audit logging
review routing
revision allowlists
retry/resume
termination
```

This layer must remain deterministic and inspectable.

Core rule:

> Claude Code / Codex decide HOW to complete an assigned task.
> The workflow decides WHAT task they are assigned, WHAT they may access, WHAT they must return, and WHAT happens next.

---

# 6. Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                       CLI / Desktop UI                       │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                THIN PYTHON WORKFLOW HARNESS                  │
│                                                              │
│                 Python + thin LangGraph                      │
│                                                              │
│   State │ Contracts │ Validation │ Routing │ Progress        │
│   Audit │ Resume    │ Excel Safety│ Provenance │ Finalize    │
│                                                              │
└────────────────────────────┬─────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│       CLAUDE CODE        │   │            CODEX             │
│                          │   │                              │
│ Filler                   │   │ Independent Reviewer         │
│ Revision                 │   │                              │
│                          │   │ Native agent runtime         │
│ Native agent runtime     │   │ ├─ local file tools         │
│ ├─ local file tools      │   │ ├─ search                   │
│ ├─ search                │   │ ├─ shell/tools              │
│ ├─ shell/tools           │   │ ├─ planning                 │
│ ├─ planning              │   │ ├─ web research             │
│ ├─ web research          │   │ └─ subagents if useful      │
│ └─ subagents if useful   │   └──────────────┬───────────────┘
└────────────┬─────────────┘                  │
             │                                │
             └──────────────┬─────────────────┘
                            ▼
                  Structured JSON Contracts
                            │
                            ▼
                 Deterministic Python Layer
                 ├─ Pydantic validation
                 ├─ rule validation
                 ├─ mutation authorization
                 └─ openpyxl workbook writes
```

---

# 7. Technology Stack

## Core

- **Python ≥ 3.12**
- **uv** — package management
- **LangGraph** — thin state-machine/orchestration layer only
- **langgraph-checkpoint-sqlite** — persistent checkpoint backend
- **Pydantic / JSON Schema** — structured contracts
- **openpyxl** — deterministic workbook access and writes
- **SQLite** — audit/state index
- **JSON / JSONL** — portable machine-readable artifacts
- **Markdown** — human-readable reports

## Agent runtimes

```text
Filler                Claude Code    (claude --print --json-schema)
Revision              Claude Code    (claude --print --json-schema)

Reviewer              Codex          (codex exec --output-schema)
```

## Development tooling

```text
pytest                testing
ruff                  linting + formatting
```

## Later frontend

```text
Tauri + React + TypeScript
```

---

# 8. Agent Runtime Philosophy

Claude Code and Codex should be invoked as **high-level workers**.

Bad:

```python
for file in files:
    run_file_search_agent(file)

for field in fields:
    run_field_agent(field)
```

This micromanages the native runtime.

Preferred:

```text
Assign Claude Code:

"Populate the target records from this workspace.
You may inspect files, search, use tools, and delegate to
native subagents where useful.

Return extraction.json conforming to schema X."
```

Claude Code may internally decide:

```text
Main Filler
  ├─ inspect workbook context
  ├─ inspect source folders
  ├─ delegate India 2008 research
  ├─ delegate India 2009 research
  ├─ independently check organization names
  └─ synthesize structured result
```

The outer workflow does not need to know how many internal subagents were used.

The Filler receives a single invocation. The agent decides whether and how to decompose the work internally.

---

# 9. Native Subagent Policy

Native subagents are allowed but **not mandatory**.

Do not force:

```text
one subagent per folder
one subagent per field
one subagent per document
```

The main Claude Code / Codex runtime should decide whether delegation improves task execution.

The prompt may state:

> You may use native subagents when useful for parallel investigation or independent verification.

But the workflow should not require them unless future benchmarks demonstrate a clear benefit.

---

# 10. Billing / Authentication Policy

For the local personal-use V1, default to **subscription authentication**, not API billing.

## Enforcement level

| Runtime | Enforcement | Mechanism |
|---|---|---|
| Codex | Runtime-enforced | Uses `auth.json` from `codex login`; do not set `CODEX_API_KEY` |
| Claude Code | Best-effort | `env.pop("ANTHROPIC_API_KEY")`; normal OAuth/keychain mode |

Claude Code's subscription-vs-API distinction cannot be reliably verified at the CLI level. This is a known limitation.

## Startup diagnostic

```text
Claude Code auth: OAuth (subscription - best effort)
Codex auth: ChatGPT subscription (auth.json)
API key env vars: cleared
```

If subscription auth cannot be reasonably verified, the application **warns** (not fails). The user decides whether to proceed.

Record this limitation in ADR `0005-subscription-auth-policy.md`.

---

# 11. Web Access Policy

## Default: ON

```yaml
network:
  filler_web_access: true
  reviewer_web_access: true
  revision_web_access: true
```

All agent roles have identical network permissions by default. Agents may supplement local evidence with web research when local sources are insufficient.

## Provenance tracking requirement

Web access is permitted, but **provenance must be transparent**. Every piece of evidence must be tagged with its source type via the `evidence_type` field. Web-sourced evidence must be tagged as `external_web`.

Local and external provenance must never be silently mixed in the audit trail.

## Optional restriction

Network access can be disabled per-role via configuration:

```yaml
network:
  filler_web_access: false
```

---

# 12. Workspace Sandbox

Every run uses a dedicated local workspace.

```text
runs/
└── <run_id>/
    ├── input/
    │   ├── sources/
    │   ├── rules/
    │   └── workbook/
    │
    ├── working/
    │   └── draft.xlsx
    │
    ├── agent_outputs/
    │   ├── filler/
    │   ├── reviewer/
    │   └── revision/
    │
    ├── artifacts/
    │
    ├── output/
    │   └── final.xlsx
    │
    ├── state/
    │   └── audit.sqlite
    │
    └── logs/
```

Agents should receive the relevant workspace path. They should not receive unrestricted access to `$HOME`, `/Desktop`, `/Documents`, or `/` unless explicitly required.

---

# 13. Agent Permissions

Agent permissions (READ/WRITE boundaries) are enforced via **prompt instructions only** for Claude Code. Codex retains OS-level sandbox enforcement via `--sandbox`.

The application does not use `--allowedTools` to restrict Claude Code's tool access.

## Claude Code Filler

```text
Prompt-instructed boundaries:
READ: source workspace, rules, workbook schema
WRITE: designated agent output directory only
NO direct workbook mutation
```

## Codex Reviewer

```text
Runtime-enforced (--sandbox read-only):
READ: original sources, rules, draft workbook, provenance, handoff
WRITE: review output directory only
NO workbook mutation
```

## Claude Code Revision

```text
Prompt-instructed boundaries:
READ: source material, review findings, original proposals, rules, mutation allowlist
WRITE: revision output directory only
NO direct unrestricted workbook mutation
```

---

# 14. Deterministic Workbook Boundary

This is non-negotiable.

Agents do not get to save arbitrary edits into `final.xlsx`.

```text
Claude / Codex
      ↓
structured JSON
      ↓
Pydantic validation
      ↓
rule validation
      ↓
mutation authorization
      ↓
openpyxl
      ↓
workbook
```

Example proposal:

```json
{
  "sheet": "7) Practicum Courses",
  "cell": "G12",
  "proposed_value": "Healthcare",
  "confidence": 0.93,
  "evidence": [...]
}
```

Python decides whether:

```text
G12 is valid
G12 is writable
value type is valid
rule requirements pass
mutation is authorized
```

Only then: `ws["G12"] = "Healthcare"`

---

# 15. File Manifest

Before calling agents, build `artifacts/manifest.json`.

Example entry:

```json
{
  "path": "India 2008/Project_Brief.pdf",
  "sha256": "a1b2c3...",
  "type": "pdf",
  "size_bytes": 2034332
}
```

The manifest records every file in the source workspace at run start. Agents read original source files directly using their native file inspection capabilities. No Docling preprocessing in V1.

Never silently omit files with status:

```text
UNSUPPORTED
ENCRYPTED
CORRUPT
```

The Filler and Reviewer must be informed about source files they may not be able to inspect.

### Future: Docling normalization

If post-V1 evaluation shows agents handle certain file types poorly (complex PDF tables, scanned images), Docling can be introduced as an optional normalization layer. The manifest schema reserves a `normalized_path` field for forward compatibility.

---

# 16. Workbook Schema

V1 uses a **manually authored** `workbook_schema.json` configuration file. No automatic schema detection from the workbook.

Capture:

- sheet names,
- target sheets,
- headers,
- writable columns,
- formulas,
- key fields,
- reference sheets,
- controlled values,
- existing values,
- field-specific rules.

Example:

```json
{
  "sheet": "7) Practicum Courses",
  "fields": {
    "Project ID*": {
      "required": true,
      "type": "string",
      "reference": "6) Engagement Projects",
      "writable": true
    },
    "Main Issue Area(s)": {
      "type": "controlled_vocabulary",
      "reference": "Main Issue Area Codes.Standardized Format"
    }
  }
}
```

Auto-detection may be added in a future version.

---

# 17. Rule Architecture

V1 hardcodes a small set of core deterministic rules in Python:

```text
required field validation
controlled vocabulary checks
ID pattern validation
date format validation
type checks
```

Semantic rules (organization entity resolution, classification from narrative evidence, tag selection, name normalization) are handled entirely by agents via prompt instructions.

If the rule set grows beyond ~20 rules, implement a data-driven rule loader.

---

# 18. Core Data Contracts

## Evidence

```python
class Evidence(BaseModel):
    source_file: str
    source_location: str | None = None
    evidence_text: str
    evidence_type: Literal[
        "direct",
        "cross_reference",
        "rule",
        "derived",
        "external_web"
    ]
```

`external_web` must be used for any web-sourced evidence. This is enforced via prompt instructions and validated post-hoc.

## Cell Proposal

```python
class CellProposal(BaseModel):
    sheet: str
    row: int
    column_name: str
    cell: str

    value: Any | None

    evidence: list[Evidence]
    rules_applied: list[str]

    confidence: float

    status: Literal[
        "proposed",
        "not_found",
        "ambiguous",
        "conflict"
    ]

    notes: str | None = None
```

## Review Finding

```python
class ReviewFinding(BaseModel):
    cell: str

    verdict: Literal[
        "PASS",
        "WARN",
        "FAIL",
        "UNRESOLVED"
    ]

    issue_type: str | None = None

    current_value: Any | None = None
    recommended_value: Any | None = None

    evidence: list[Evidence]
    reviewer_comment: str

    missed_data: bool = False
```

## Revision Decision

```python
class RevisionDecision(BaseModel):
    cell: str

    action: Literal[
        "ACCEPT",
        "FIX",
        "REBUT",
        "CLEAR",
        "NO_CHANGE",
        "UNRESOLVED"
    ]

    original_value: Any | None = None
    proposed_value: Any | None = None

    note_append: str | None = None

    evidence: list[Evidence]
    justification: str
```

### Action semantics

```text
ACCEPT       adopt Reviewer's recommendation
FIX          found a better correction independently
REBUT        disagrees with Reviewer → one targeted re-review round
CLEAR        clear cell value (correct value undeterminable)
NO_CHANGE    PASS cells, no action needed
UNRESOLVED   cannot determine correct action
```

`note_append` optionally carries explanatory text to append to the same row's Notes cell as part of the same authorized mutation. It is used with CLEAR or FIX when prose does not belong in a data field but must be preserved (e.g. clearing a proxy value and moving it, with its citation, into Notes).

## Re-Review Verdict

```python
class ReReviewVerdict(BaseModel):
    cell: str

    verdict: Literal[
        "WITHDRAWN",
        "UPHELD"
    ]

    reviewer_comment: str
```

---

# 19. Cell-Level Provenance

Every AI-generated workbook mutation must have traceable provenance.

Minimum record:

```json
{
  "cell": "7) Practicum Courses!G12",
  "value": "Healthcare",
  "agent_role": "filler",
  "agent_runtime": "claude-code",
  "evidence": [
    {
      "source_file": "India 2008/brief.pdf",
      "source_location": "page 2",
      "evidence_text": "...",
      "evidence_type": "direct"
    }
  ],
  "rules_applied": ["MAIN_ISSUE_AREA_STANDARDIZATION"],
  "confidence": 0.93,
  "run_id": "..."
}
```

Markdown summaries are not sufficient. Machine-readable JSON is the authoritative provenance record.

---

# 20. Filler Contract — Claude Code

## Goal

Extract all supportable target workbook data within the assigned scope.

## Inputs

- run workspace path,
- source manifest,
- original source files (accessed via native file tools),
- workbook schema,
- rules,
- canonical registries,
- target rows/records,
- output JSON schema.

## Invocation

Two invocations: a scoping pass, then the extraction pass. In each, the agent decides whether and how to decompose work internally (including native subagent delegation).

## Scoping pass (first invocation)

Before extraction, the Filler inspects the workspace and returns only a scoping question list (`scoping_questions.json` + `scoping_questions.md`): row granularity, program/period mapping per source folder, scope completeness ("are these folders the full authoritative set?"), and any convention the rules do not already cover.

The workflow then pauses (LangGraph interrupt). The user answers by editing `scoping_answers.md` and runs `workflow resume`. The answers are passed to the extraction pass as an explicit input artifact and recorded in the audit trail.

If `scoping_answers.md` is already provided at run start (a re-run on a known dataset), the scoping pass is skipped.

## Filler MUST

- return structured proposals conforming to the output schema,
- distinguish not-found vs ambiguous vs conflicting,
- provide evidence with `evidence_type` tags,
- provide confidence scores,
- cap confidence at **medium** for constructed fields (values assembled by naming format, e.g. Project ID, Parent Program) and mapped fields (values chosen from a controlled vocabulary or judgment scale, e.g. Main Issue Area(s), Project Tags, Maturity, Project Success) — this forces them into prioritized review sampling,
- tag web-sourced evidence as `external_web`.

## Filler MUST NOT

- edit original source files,
- directly edit the target workbook,
- return unsupported values merely to increase fill rate.

---

# 21. Filler Outputs

Required:

```text
extraction.json
provenance.json
handoff.json
handoff.md
```

`handoff.md` is generated for inspection/review convenience.

Machine state must depend on structured JSON.

---

# 22. Handoff Content

Include:

- processed source summary,
- files that could not be parsed,
- records evaluated,
- populated fields,
- source evidence summary,
- confidence distribution,
- missing fields,
- ambiguity,
- source conflicts,
- areas recommended for extra review.

The Reviewer receives the handoff but must not treat it as authoritative.

## Review explorer (deterministic rendering)

Alongside the handoff, the deterministic Python layer (no agent involvement) renders a **bilingual review explorer** from `draft.xlsx` + `provenance.json`, in two language variants (EN / ZH). Requirements mirror the original workflow's explorer:

- Single self-contained HTML file, no external dependencies; opens directly from disk (double-click).
- **Sidebar**: source folders in traversal order, expandable to their rows (sheet row numbers shown). Duplicate/merged folders carry a "merged ↦" marker linking to the surviving row, which shows an explanatory callout.
- **Overview page**: archival findings (duplicates, year contradictions, cohort assignments — sourced from `handoff.json`) at top; below, a master table of all rows (row number, folder, organization, parent program, issue areas, fill rate), each linking to its detail page.
- **Row detail**: every column listed with its Excel column letter (full header on hover); cell value plus provenance beneath a divider (source-file chip + specific reason). Empty fields collapsed behind "Show N empty fields". Prev/next paging by row number.
- **Search** across organization names, folder names, and any cell or provenance text, with hit highlighting.

Generated after WRITE_DRAFT (for Reviewer and human inspection) and regenerated after APPLY_ALLOWED_REVISIONS as `_v2` files, so the final explorer matches the revised workbook and updated provenance exactly.

---

# 23. Reviewer Contract — Codex

The Reviewer is an **independent verifier**, deliberately run on a different vendor (Codex / OpenAI) than the Filler (Claude Code / Anthropic) for adversarial design.

## Inputs

```text
original source material (accessed via native file tools)
rules
workbook schema
draft workbook / snapshot
extraction.json
provenance.json
handoff
review policy
```

## Invocation

Single `codex exec` call with `--sandbox read-only` and `--output-schema`.

## Reviewer MUST assess

```text
correctness
rule compliance
completeness
consistency
provenance quality
```

## Reviewer MUST NOT

```text
edit workbook
silently correct workbook
blindly trust handoff
invent missing values
```

## Targeted re-review invocation

When Revision produces REBUT decisions, Codex is invoked once more on the rebutted cells only. Inputs: the rebutted findings, the corresponding revision decisions with their evidence, and source access. For each cell it returns a `ReReviewVerdict`: `WITHDRAWN` (the rebuttal stands; finding closed, original value kept) or `UPHELD` (the disagreement stands; the cell escalates to UNRESOLVED and human fallback). Exactly one such round runs per workflow; the re-review cannot mutate the workbook or add new findings.

---

# 24. Review Verdicts

```text
PASS
WARN
FAIL
UNRESOLVED
```

**PASS** — Evidence and rules support current value.

**WARN** — Potential concern requiring explicit Revision response.

**FAIL** — Incorrect, unsupported, or missing when correct data is reasonably determinable.

**UNRESOLVED** — Available evidence does not permit reliable adjudication.

---

# 25. Review Depth

Review policy is configuration, not agent whim.

Example:

```yaml
review:
  strict_fields:
    - Project ID*
    - Parent Program*

  low_confidence_threshold: 0.60
  medium_confidence_threshold: 0.85

  high_confidence_sampling_per_record: 2
```

Conceptual policy:

```text
strict fields       → mandatory verification
low confidence      → full verification
medium confidence   → prioritized verification
high confidence     → configured spot check
completeness        → source-folder audit
```

---

# 26. Reviewer Outputs

Required:

```text
review.json
review.md
```

Every non-PASS finding should state:

```text
what is wrong
what evidence was checked
recommended correction if determinable
why the verdict was assigned
```

---

# 27. Revision Contract — Claude Code

## Inputs

Revision receives **only non-PASS findings**:

- FAIL, WARN, UNRESOLVED review findings,
- the corresponding original proposals for those cells,
- the corresponding provenance entries,
- rules relevant to flagged cells,
- workspace path for on-demand source file access,
- explicit mutation allowlist.

Revision does **not** receive:

- PASS findings,
- the complete extraction.json,
- the complete provenance.json,
- pre-loaded source file contents.

The agent accesses source files on demand via its native file tools.

## Behavior

```text
FAIL
  → FIX / CLEAR / UNRESOLVED

WARN
  → ACCEPT or REBUT

PASS
  → NO_CHANGE (not sent to Revision)

MISSED DATA
  → independently verify → fill if valid
```

## REBUT semantics

REBUT triggers **exactly one targeted re-review round**: Codex re-examines only the rebutted cells (see the Reviewer contract). If the re-review withdraws the finding, the original value stands and the finding is closed. If the re-review upholds the finding, the cell escalates to UNRESOLVED and human fallback — no second rebuttal, no further automated adjudication, and no automatic value change.

This mirrors the original workflow's "recommend re-review of rebutted items only" step while keeping the loop strictly bounded, and preserves the audit distinction between "cannot determine" and "actively disagrees".

## FIX trust model

When Revision produces a FIX action with a new proposed value, the value is written to the workbook after passing Python-layer deterministic validation. It does not undergo a second Codex review.

## Confirmation bias mitigation

Filler and Revision both use Claude Code (same vendor). The Revision prompt must include explicit debiasing instructions:

```text
You are the Revision Agent — an independent role, separate from the Filler.

Do not assume the Filler's original value is correct merely because it was
proposed. Evaluate each Reviewer finding on its own evidence merits.

If the Reviewer's evidence is stronger than the Filler's original evidence,
you MUST choose ACCEPT or FIX, not REBUT.

REBUT is reserved for cases where you have concrete counter-evidence that
the Reviewer's assessment is factually wrong.
```

---

# 28. Bounded Mutation

The workflow generates a mutation allowlist:

```json
{
  "allowed_cells": [
    "7) Practicum Courses!G12",
    "7) Practicum Courses!H12"
  ]
}
```

The allowlist automatically includes the Notes cell of every flagged row, so a `note_append` companion edit is always authorized alongside its primary cell.

Claude Code may reason freely about those findings.

It may NOT modify or propose unrelated workbook changes outside the allowed scope.

PASS cells are frozen by default.

## Row identity

Cell addresses (e.g. `G12`) are used directly. The workflow assumes the user does not modify the workbook during a run. Row numbers are stable within a single run.

---

# 29. Human Fallback

If UNRESOLVED items remain after Revision and the targeted re-review round (including rebuttals the re-review upheld):

```text
human_review.json
human_review.md
```

Include:

- affected cell,
- current value,
- competing interpretations,
- source evidence,
- Reviewer argument,
- Revision argument,
- reason automation could not resolve.

V1: user reads `human_review.md` and manually edits `final.xlsx`.

V2 may add interactive approval/edit controls.

---

# 30. Workflow Graph

LangGraph should remain deliberately small.

```text
INIT
 ↓
PREPARE_WORKSPACE
 ↓
DISCOVER + BUILD_MANIFEST
 ↓
LOAD_SCHEMA
 ↓
LOAD_RULES
 ↓
CLAUDE_SCOPE
 ↓
AWAIT_SCOPING_ANSWERS   ← pause; skipped when answers pre-provided
 ↓
CLAUDE_FILL
 ↓
VALIDATE
 ↓
WRITE_DRAFT
 ↓
CODEX_REVIEW
 ↓
ISSUES?
 ├─ NO → FINALIZE
 └─ YES
      ↓
   CLAUDE_REVISE
      ↓
   APPLY_ALLOWED_REVISIONS
      ↓
   REBUTTALS?
   ├─ YES → CODEX_REREVIEW (once, rebutted cells only)
   └─ NO
      ↓
   UNRESOLVED?
   ├─ NO → FINALIZE
   └─ YES → HUMAN_REVIEW → FINALIZE
```

LangGraph is NOT responsible for decomposing document research into tiny agent calls.

## State serialization

LangGraph state stores **file paths**, never in-memory objects:

```python
class WorkflowState(TypedDict):
    run_id: str
    workspace_path: str
    draft_xlsx_path: str
    manifest_path: str
    schema_path: str
    scoping_questions_path: str | None
    scoping_answers_path: str | None
    extraction_path: str | None
    review_path: str | None
    revision_path: str | None
    re_review_path: str | None
    phase: str
```

Workbook objects (`openpyxl.Workbook`) are loaded on demand within each node function, operated on, and saved back to disk. They never enter the LangGraph state.

## Checkpoint backend

`langgraph-checkpoint-sqlite` (SqliteSaver) for persistent resume capability.

---

# 31. Agent Runtime Adapter

Keep runtime-specific invocation behind a small interface.

```python
class AgentRuntime(Protocol):
    def run(self, request: AgentRequest) -> AgentResult:
        ...
```

Implement:

```text
ClaudeCodeRuntime    claude --print --json-schema --output-format json
CodexRuntime         codex exec --output-schema --json -o
FakeAgentRuntime     return fixture JSON
```

Responsibilities of runtime adapters:

```text
launch agent process
configure workspace path
configure auth (clear API keys if needed)
capture structured result
capture process status
map runtime failures
```

Do not put business workflow logic inside the adapter.

---

# 32. Fake Runtime First

Before live agent integration:

```text
Fake Claude Filler
Fake Codex Reviewer
Fake Claude Revision
```

Run the entire system with fixture JSON.

This verifies:

```text
state transitions
schema validation
workbook mutation safety
review routing
bounded revision
artifact generation
resume behavior
```

without model variability or subscription consumption.

Only then connect real agents.

---

# 33. Progress Output

The CLI outputs stage-level progress to stderr during execution:

```text
[workflow] Starting run abc123...
[workflow] Building file manifest... 12 files found
[workflow] Loading workbook schema...
[workflow] Starting scoping pass (Claude Code)...
[workflow] Scoping questions written. Answer scoping_answers.md, then run: workflow resume --run-id abc123
[workflow] Starting Filler (Claude Code)...
[workflow] Filler complete: 42 proposals
[workflow] Validating proposals...
[workflow] Writing draft workbook...
[workflow] Rendering review explorer (EN/ZH)...
[workflow] Starting Reviewer (Codex)...
[workflow] Review complete: 3 FAIL, 2 WARN, 37 PASS
[workflow] Starting Revision (Claude Code)...
[workflow] Revision complete: 2 FIX, 1 ACCEPT, 2 UNRESOLVED
[workflow] Applying authorized revisions...
[workflow] Starting targeted re-review (Codex): 2 rebutted cells...
[workflow] Generating human review artifacts...
[workflow] Run complete. Output: output/final.xlsx
```

No progress bars, no TUI. Simple `print(..., file=sys.stderr)`.

---

# 34. Repository Structure

```text
document-workbook-workflow/
│
├── README.md
├── pyproject.toml
├── .env.example
│
├── src/
│   └── workflow_app/
│       ├── cli.py
│       ├── config.py
│       │
│       ├── workflow/
│       │   ├── graph.py
│       │   ├── state.py
│       │   └── routing.py
│       │
│       ├── runtimes/
│       │   ├── base.py
│       │   ├── fake.py
│       │   ├── claude_code.py
│       │   └── codex.py
│       │
│       ├── roles/
│       │   ├── filler.py
│       │   ├── reviewer.py
│       │   └── revision.py
│       │
│       ├── prompts/
│       │   ├── scoping.md
│       │   ├── filler.md
│       │   ├── reviewer.md
│       │   ├── re_review.md
│       │   └── revision.md
│       │
│       ├── ingestion/
│       │   ├── discover.py
│       │   └── manifest.py
│       │
│       ├── workbook/
│       │   ├── schema.py
│       │   ├── mutations.py
│       │   ├── writer.py
│       │   └── safety.py
│       │
│       ├── rules/
│       │   └── deterministic.py
│       │
│       ├── models/
│       │   ├── evidence.py
│       │   ├── extraction.py
│       │   ├── review.py
│       │   ├── revision.py
│       │   └── run.py
│       │
│       ├── validation/
│       │   ├── schemas.py
│       │   └── rules.py
│       │
│       ├── provenance/
│       │   ├── store.py
│       │   ├── render.py
│       │   └── explorer.py
│       │
│       └── audit/
│           ├── db.py
│           └── events.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   ├── fixtures/
│   └── golden/
│
├── docs/
│   └── adr/
│
└── examples/
```

Key structural choice:

```text
runtimes/ = Claude Code / Codex execution adapters
roles/    = our workflow-level Filler/Reviewer/Revision contracts
```

This reflects that Claude Code and Codex already contain their own inner agent systems.

---

# 35. Run Workspace

```text
runs/
└── <run_id>/
    ├── input/
    │   ├── sources/
    │   ├── rules/
    │   └── workbook/
    │
    ├── working/
    │   └── draft.xlsx
    │
    ├── state/
    │   ├── workflow_state.json
    │   └── audit.sqlite
    │
    ├── agent_outputs/
    │   ├── filler/
    │   ├── reviewer/
    │   └── revision/
    │
    ├── artifacts/
    │   ├── manifest.json
    │   ├── workbook_schema.json
    │   ├── scoping_questions.json
    │   ├── scoping_questions.md
    │   ├── scoping_answers.md
    │   ├── extraction.json
    │   ├── provenance.json
    │   ├── handoff.json
    │   ├── handoff.md
    │   ├── review_explorer.html
    │   ├── review_explorer_zh.html
    │   ├── review_explorer_v2.html
    │   ├── review_explorer_zh_v2.html
    │   ├── review.json
    │   ├── review.md
    │   ├── revision.json
    │   ├── revision_log.md
    │   ├── re_review.json
    │   ├── unresolved.json
    │   ├── human_review.json
    │   ├── human_review.md
    │   └── run_summary.md
    │
    ├── output/
    │   └── final.xlsx
    │
    └── logs/
```

---

# 36. Persistence / Audit

SQLite tracks:

## Run

```text
run_id
status
start/end
configuration
input hashes
auth mode
network policy
runtime metadata
```

## Stage

```text
stage
start/end
status
retry count
artifact IDs
```

## Mutation

```text
cell
old value
new value
actor role
source proposal
timestamp
```

## Finding

```text
review verdict
revision action
```

## Runtime events

Only operational/structured data.

Do NOT log private hidden chain-of-thought.

---

# 37. Retry / Resume

## Retry strategy

Lenient:

```text
schema validation failure    → retry up to 2 times
runtime process failure      → retry up to 2 times
temporary invocation failure → retry up to 2 times

after 2 retries             → mark as UNRESOLVED, continue
```

## Do not blindly retry

```text
contradictory evidence
invalid workbook structure
deterministic business-rule failure
```

## Resume

Persist state via LangGraph SqliteSaver around external agent calls.

A restarted run must not duplicate workbook mutations. The deterministic Python layer checks "has this cell already been written in this run?" before applying mutations.

---

# 38. Usage Control

Native subagents can increase subscription/token consumption.

Therefore:

- allow agents to use them,
- do not force them,
- record high-level runtime usage metadata when available.

Support configuration:

```yaml
agent_behavior:
  allow_native_subagents: true
```

Optional mode for debugging or usage conservation:

```yaml
agent_behavior:
  allow_native_subagents: false
```

---

# 39. Prompts

Prompts live in version-controlled files.

Every prompt defines:

```text
role
goal
workspace
permissions
available artifacts
required output schema
evidence policy (including evidence_type tagging)
confidence policy (including the medium cap for constructed/mapped fields)
uncertainty policy
mutation policy
subagent permission
confirmation bias mitigation (Revision only)
```

Example Filler instruction:

```text
You are the Filler Agent.

Use the provided local workspace to populate all supportable target
fields according to the workbook schema and rules.

You may inspect files, search locally, use safe tools, use native
subagents if useful, and research online when local sources are
insufficient.

Do not directly edit the target workbook.

Tag every piece of evidence with its source type. If you find
information from the web, tag evidence_type as "external_web".

Return a result conforming exactly to the provided extraction schema.
```

Do NOT prescribe every search or tool step.

---

# 40. No Reliance on Conversational Memory

Each role invocation must be self-contained.

Do not assume:

```text
Claude remembers previous Claude run
Codex remembers previous Codex run
Reviewer knows Filler's hidden reasoning
```

Pass explicit structured artifacts.

---

# 41. Testing Strategy

## Unit

Focus on deterministic boundaries:

```text
file manifest
workbook schema parsing
Pydantic contracts
rule validation
mutation allowlist
writer
routing
auth config
```

## Integration

Use fake runtimes:

```text
sources
 ↓
fake filler
 ↓
draft
 ↓
fake reviewer
 ↓
fake revision
 ↓
final
```

## Runtime contract tests

Run minimal live smoke tests separately for:

```text
Claude Code structured output
Codex structured output
subscription auth behavior
workspace restrictions
```

Normal CI should not require paid/limited agent usage.

---

# 42. Evaluation

Build a labeled benchmark from manually verified historical work.

For each expected field:

```text
expected value
expected evidence
expected blank/unresolved status
```

Metrics:

```text
field accuracy
unsupported fill rate
missed data rate
provenance coverage
review true-positive rate
review false-positive rate
revision correctness
unresolved count
web-sourced evidence percentage
```

Also compare:

```text
native subagents enabled  vs  disabled
web access enabled        vs  disabled
```

on accuracy, runtime, usage, and review quality.

---

# 43. Implementation Milestones

## Milestone 0 — Contracts + Skeleton

Build:

```text
Python package (uv + pyproject.toml)
CLI (run + resume)
config
Pydantic models
workspace
SQLite audit schema
fake runtimes
```

No live models.

## Milestone 1 — Workbook Safety Layer

Build:

```text
load workbook schema (from hand-written config)
copy workbook
mutation API
allowlist
audit
save/reopen validation
```

Acceptance: only authorized cells can be mutated.

## Milestone 2 — Ingestion / Rules

Build:

```text
file discovery
manifest (hash + metadata)
hardcoded deterministic validators
```

## Milestone 3 — Full Fake Workflow

Implement complete:

```text
fill → validate → write draft → review → revision → human fallback → finalize
```

using fixture outputs.

Also implement the deterministic review-explorer rendering (bilingual, single-file HTML) from fixture draft + provenance, including the post-revision `_v2` regeneration.

Acceptance: entire state machine works without Claude/Codex.

## Milestone 4 — Claude Code Runtime + Filler

Build:

```text
ClaudeCodeRuntime (claude --print --json-schema)
subscription auth (best-effort)
workspace path
structured output capture
scoping pass + pause/resume for answers
Filler role integration
```

Acceptance: Claude Code produces valid extraction artifacts.

## Milestone 5 — Codex Runtime + Reviewer

Build:

```text
CodexRuntime (codex exec --output-schema --sandbox)
ChatGPT subscription auth
read-only sandbox
Reviewer role integration
```

Acceptance: Codex independently produces valid review artifacts.

## Milestone 6 — Revision

Build:

```text
Claude Code bounded Revision
confirmation bias mitigation prompt
REBUT → single Codex targeted re-review round
unresolved escalation + human fallback artifact generation
```

## Milestone 7 — Persistence / Resume

Build:

```text
LangGraph SqliteSaver checkpoints
resume command
idempotent mutation application
failure classification
lenient retry (2x → UNRESOLVED)
```

## Milestone 8 — Evaluation

Benchmark real historical data.

Evaluate:

```text
accuracy
review effectiveness
subagent behavior
usage/quota pressure
provenance quality
web evidence impact
```

## Milestone 9 — Desktop UI

Only after engine reliability.

```text
Tauri + React + TypeScript
folder/workbook/rules picker
run progress
review summary
human-review queue
open artifacts
```

---

# 44. Frozen Architectural Decisions

Treat these as fixed unless implementation proves a concrete blocker:

```text
Local-first                                  YES

Backend                                      Python ≥ 3.12
Package manager                              uv

Workflow orchestration                       Thin LangGraph
Checkpoint backend                           SqliteSaver
LangGraph state serialization                FILE PATHS ONLY

Agent runtime harness                        DO NOT BUILD

Filler                                       Claude Code
Revision                                     Claude Code
Reviewer                                     Codex
Dual-vendor motivation                       ADVERSARIAL DESIGN

Targeted Re-review                           ONE BOUNDED ROUND (REBUT cells only)
REBUT behavior                               RE-REVIEW ONCE → UNRESOLVED IF UPHELD

Native agent tools                           USE
Native subagents                             ALLOW, NOT FORCE

Structured contracts                         Pydantic / JSON Schema
Workbook mutation                            deterministic openpyxl
Direct agent workbook mutation               NO

Cell-level provenance                        REQUIRED
Reviewer independent source access           REQUIRED
Reviewer workbook write access               NO
Bounded revision                             REQUIRED

Pre-extraction scoping pause                 REQUIRED (skipped when answers pre-provided)
Constructed/mapped-field confidence cap      MEDIUM
Bilingual review explorer (EN/ZH HTML)       DETERMINISTIC RENDER (single-file, offline)

Human fallback                               REQUIRED (files only in V1)

Default Web access                           ON
Evidence boundary                            ALL (with evidence_type tracking)

V1 auth mode                                 subscription (best-effort)
Automatic API billing fallback               NO (best-effort enforcement)

V1 Docling                                   DEFERRED
V1 workbook schema detection                 MANUAL
V1 rule engine                               HARDCODED
V1 agent tool restriction (allowedTools)     NONE

V1 interface                                 CLI (run + resume)
Later interface                              Tauri + React desktop
```

---

# 45. Explicitly Removed from V1

Do NOT build:

```text
custom general-purpose agent harness
custom planner
custom tool-routing framework
custom subagent framework
one-agent-per-document architecture
custom browser/research agent
vector database without demonstrated need
unbounded re-review / dispute loop (one targeted round IS allowed)
Docling normalization layer
automatic workbook schema detection
config-driven rule engine
cloud deployment
multi-user SaaS
direct arbitrary workbook editing
```

---

# 46. Resolved Questions

The following were open in v2 and are now resolved:

| Question | Resolution |
|---|---|
| Claude Code non-interactive invocation | `claude --print --json-schema --output-format json` |
| Codex invocation | `codex exec --output-schema --json -o` |
| Subscription-vs-API auth verification | Best-effort; cannot be fully verified at CLI level |
| Agent access to input files | Direct access via workspace path; no copied files |
| Docling vs native runtime inspection | V1: native only; Docling deferred |
| Review sampling configuration | Configurable via review policy YAML |
| Web access for verification | Default ON for all roles |
| Runtime/subagent usage metadata | Record when available; do not force |
| Row identity strategy | Cell addresses; assume no mid-run workbook edits |
| Desktop/Python IPC | Deferred to V2 |

---

# 47. ADRs

Create:

```text
docs/adr/
├── 0001-thin-workflow-harness.md
├── 0002-native-agent-runtime.md
├── 0003-workbook-mutation-boundary.md
├── 0004-subagent-policy.md
├── 0005-subscription-auth-policy.md
├── 0006-web-access-policy.md
├── 0007-provenance-schema.md
└── 0008-review-revision-protocol.md
```

---

# 48. Implementation Tasks

Follow this order.

## Task 1

Scaffold repository and Python package (uv + pyproject.toml).

## Task 2

Define Pydantic contracts (Evidence, CellProposal, ReviewFinding, RevisionDecision).

## Task 3

Implement run workspace, sandbox-path layout, and SQLite audit schema.

## Task 4

Implement deterministic workbook mutation layer with tests (load schema, copy workbook, mutation API, allowlist, audit).

## Task 5

Implement source manifest (file discovery, hashing, metadata).

## Task 6

Implement hardcoded deterministic validators (required fields, controlled vocabulary, ID patterns, date formats, type checks).

## Task 7

Implement `AgentRuntime` protocol plus `FakeAgentRuntime`.

## Task 8

Implement the full thin workflow graph using only fake agent outputs. Test bounded revision using fake artifacts.

## Task 9

Implement `ClaudeCodeRuntime`, the scoping pass with pause/resume, and the Claude Filler role.

## Task 10

Implement `CodexRuntime` and Codex Reviewer role.

## Task 11

Implement Claude Revision role (with confirmation bias mitigation, REBUT → single Codex targeted re-review round, unresolved escalation, human fallback artifacts).

## Task 12

Add resume / idempotency / retries.

## Task 13

Run a small manually verified benchmark.

Do NOT build the desktop UI before these pass.

---

# 49. Implementation Guardrails

Any coding agent implementing this plan MUST:

1. Treat Claude Code and Codex as full agent runtimes.
2. Avoid rebuilding their inner agent harness.
3. Keep the outer workflow deterministic.
4. Keep runtime-specific behavior behind adapters.
5. Allow but not force native subagents.
6. Tag web-sourced evidence as `external_web` in provenance.
7. Never silently fall back to usage-billed APIs in subscription-only mode.
8. Never allow Reviewer to modify the workbook.
9. Never allow Revision unrestricted workbook access.
10. Never use Markdown as the sole workflow state.
11. Validate every structured agent result.
12. Route workbook changes through deterministic Python.
13. Preserve cell-level provenance.
14. Preserve original input workbook/files.
15. Freeze PASS cells during revision.
16. Require ACCEPT or REBUT for WARN; route REBUT through exactly one targeted re-review round, then escalate to UNRESOLVED if upheld.
17. Emit UNRESOLVED instead of guessing.
18. Test deterministic components without live agents.
19. Avoid unnecessary custom RAG/vector infrastructure.
20. Keep CLI/Desktop separated from engine logic.
21. Never log hidden model chain-of-thought.
22. Record material architecture changes with ADRs.
23. Include explicit confirmation bias mitigation in Revision prompt.
24. Cap confidence at medium for constructed and mapped fields.
25. Pause for scoping answers before extraction unless answers are pre-provided.

---

# 50. Definition of Done — Engine V1

The engine is complete when:

1. User can specify local sources, workbook, and rules.
2. A safe run workspace is created.
3. Files are inventoried with manifest.
4. Workbook schema is loaded from hand-written config.
5. Deterministic rules are loaded.
6. Claude Code receives a high-level Filler task.
7. Claude Code may internally use tools/subagents/web without outer micromanagement.
8. Claude returns schema-valid proposals.
9. Python validates and writes only authorized workbook cells.
10. Every written AI value has provenance with evidence_type tags.
11. Codex independently reviews source evidence and completeness.
12. Codex may internally use native subagents and web research.
13. Reviewer cannot modify workbook.
14. Claude Revision receives only non-PASS findings.
15. PASS cells remain untouched.
16. WARN findings become ACCEPT or REBUT (REBUT → one targeted re-review → UNRESOLVED → human if upheld).
17. Python applies authorized revisions after deterministic validation.
18. Remaining ambiguity becomes a human-review artifact.
19. User reads human_review.md and manually edits final.xlsx.
20. Final workbook and all audit artifacts are produced.
21. Run can resume after interruption without duplicated mutations.
22. Subscription-only mode does not silently produce API billing (best-effort).
23. Stage-level progress is output to stderr.
24. Extraction is preceded by a scoping question/answer pause, unless answers were pre-provided.
25. A bilingual (EN/ZH), single-file, offline review explorer is rendered deterministically from the draft workbook and provenance, and regenerated after revisions so it matches the final workbook exactly.

---

# 51. Required Final Artifacts

```text
output/
└── final.xlsx

artifacts/
├── manifest.json
├── workbook_schema.json
├── scoping_questions.json
├── scoping_questions.md
├── scoping_answers.md
├── extraction.json
├── provenance.json
├── handoff.json
├── handoff.md
├── review_explorer.html
├── review_explorer_zh.html
├── review_explorer_v2.html
├── review_explorer_zh_v2.html
├── review.json
├── review.md
├── revision.json
├── revision_log.md
├── re_review.json
├── unresolved.json
├── human_review.json
├── human_review.md
└── run_summary.md

state/
└── audit.sqlite
```

---

# 52. Architecture Summary

```text
                 USER
                  │
        Select folder/workbook/rules
                  │
                  ▼
        THIN WORKFLOW HARNESS
         Python + LangGraph
                  │
     ┌────────────┴─────────────┐
     │                          │
     ▼                          ▼
CLAUDE CODE                   CODEX
Filler / Revision            Reviewer
     │                          │
     │ native planning          │ native planning
     │ local tools              │ local tools
     │ file search              │ file search
     │ web research             │ web research
     │ optional subagents       │ optional subagents
     │                          │
     └────────────┬─────────────┘
                  │
          Structured contracts
                  │
                  ▼
        Deterministic Python
      validation + Excel writer
                  │
                  ▼
       Provenance + Audit Trail
       (with evidence_type tags)
                  │
                  ▼
              final.xlsx
```

The fundamental separation:

```text
Claude Code / Codex
= HOW to investigate, reason, search, and internally delegate

Our Workflow
= WHAT role runs, WHAT it may access, WHAT it must return,
  WHAT changes are authorized, and WHAT happens next
```

---

# 53. Product / Resume-Level Description

Target description after implementation:

> Built a local-first document-to-workbook AI workflow that uses Claude Code and Codex as autonomous agent runtimes for structured extraction and independent adversarial cross-vendor verification; implemented a thin Python/LangGraph orchestration layer with deterministic Excel writes, cell-level provenance with source-type tracking, subscription-safe execution, bounded revision with confirmation-bias mitigation, and resumable audit state.

Only claim features externally after they are actually implemented.
