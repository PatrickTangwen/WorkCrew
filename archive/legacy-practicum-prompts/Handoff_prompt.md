> Archived historical prompt. Not used by the WorkCrew runtime; see `README.md`.

# Generate a Handoff Review Document

You have just completed filling in **"7) Practicum Courses"**.

Now, generate a structured handoff document for another agent to conduct a field-by-field review of your work.

## Document Structure

### 1. Task Summary

Write a 3–5 sentence summary covering:

* What work was completed
* Which folders were used as data sources
* Where the output is located

### 2. Filling Decision Log

Group the decision log by program and document each populated field.

For each program entry (e.g., **India 2008**), include a table in the following format:

| Column          | Filled Value | Supporting Source                                | Confidence | Review Notes                                                |
| --------------- | ------------ | ------------------------------------------------ | ---------- | ----------------------------------------------------------- |
| Project ID      | ...          | Based on the format in`6) Engagement Projects` | High       | —                                                          |
| Main Issue Area | ...          | `[filename]` Specific justification            | Medium     | Original wording is "X"; mapped to "Y". Needs confirmation. |

Definitions:

* **Confidence**

  * **High** — Explicitly stated in the source material
  * **Medium** — Requires inference or category mapping
  * **Low** — Insufficient information; value was filled in with significant uncertainty
* **Review Notes**

  * Complete this field only when confidence is **Medium** or **Low**.
  * Explain the reason for the uncertainty and suggest what the reviewing agent should verify.

### 3. List of Unfilled Fields

List every cell that was left blank and explain why it was not filled.

### 4. Issues Requiring Human Judgment

Document any issues encountered during the filling process that could not be resolved automatically, such as:

* Ambiguous classification mappings
* Conflicting information across documents within the same folder
* Naming or spelling anomalies (e.g., `"Inida 2017"`)

## Formatting Requirements

* Output the handoff document as a **Markdown (`.md`) file**.
* Use a **second-level heading (`##`) for each program** so the reviewing agent can quickly navigate to individual programs.
* When citing files in tables, use the **full relative file path**, for example: `India 2008/xxx.pdf`.
