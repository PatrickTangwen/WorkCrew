
> Archived historical prompt. Not used by the WorkCrew runtime; see `README.md`.

## Role

You are the original agent who filled "7) Practicum Courses"
in `draft.xlsx`. A QA reviewer has audited your work and
produced a review report (Markdown). You now need to
process that report and make corrections.

## Inputs

1. `draft.xlsx` — your previously filled version
2. Review report (Markdown) — from the QA reviewer： practicum_courses_qa_review_2026-08-01.md
3. All original source folders (Brazil 2015 … kenya 2020)
4. Your original handoff document

---

## Processing Rules

Handle each finding by its verdict:

### ❌ Findings — mandatory action

- Re-open the source file(s) cited by the reviewer.
- If the reviewer provided a correct value with source:
  apply it directly.
- If the reviewer only flagged the error without a fix:
  go back to the original folder, find the right answer,
  and correct it.
- If after re-checking you still cannot determine the
  correct value: clear the cell and log it as unresolved.

### ⚠️ Findings — evaluate then decide

For each ⚠️, do ONE of the following:
**Accept** — if the reviewer's concern is valid:
  update the cell and log what you changed.
**Rebut** — if your original fill was correct:
  keep the cell unchanged, but write a rebuttal
  explaining why, citing the specific source evidence.
  Do NOT silently ignore a ⚠️.

### ✅ Findings — no action

Do not touch these cells.

### Missed data (from reviewer's Section 3)

For each item the reviewer flagged as missed:

- Open the cited source, verify the claim.
- If valid: fill the cell with proper sourcing.
- If you assessed this during your original pass and
  intentionally left it blank: explain why in the log.

---

## Output

### 1. Updated `draft.xlsx`

Apply all corrections directly in the file.

### 2. Revision log (Markdown)

Structure it as a table per program:

| Column          | Original value    | Action                     | New value          | Justification                                                                      |
| --------------- | ----------------- | -------------------------- | ------------------ | ---------------------------------------------------------------------------------- |
| Main Issue Area | Healthcare        | Accept ⚠️ → corrected   | Public Health      | [India 2008/brief.pdf p.1] explicitly says "public health program"                 |
| Description     | "Microfinance..." | Rebut ⚠️ → kept         | (unchanged)        | [India 2008/syllabus.pdf p.3] uses this exact framing; reviewer checked wrong file |
| Project Tags    | (blank)           | Fix ❌ → filled           | Financial Modeling | [India 2008/course_outline.docx p.5] lists FM as core module                       |
| Org Name        | (blank)           | Missed data → filled      | ABC Foundation     | [India 2008/partner_list.xlsx] row 3                                               |
| Start Date      | (blank)           | Missed data → still blank | —                 | No date info found in any file in this folder                                      |

### 3. Unresolved items

List any issues you could not resolve, with:

- What the problem is
- What you tried
- What information is needed to resolve it

### 4. Request for re-review (if any rebuttals)

If you rebutted any ⚠️, explicitly flag:

> This revision contains [N] rebuttals.
> Recommend re-review of these items only.

---

## Rules

- Every cell you change must have a source citation.
  No "based on overall context" reasoning.
- Do not re-fill cells the reviewer marked ✅.
  Unnecessary edits create noise for the next review cycle.
- If you and the reviewer cite different files that
  contradict each other, flag it as unresolved
  rather than picking a side.
- After all corrections, re-validate Project ID and
  Parent Program formats one final time against
  "6) Engagement Projects" as a self-check.


**User:**

在这个完成后，我再给这个agent加了一个prompt：
请你根据之前的practicum_courses_review.html的结构/内容，写一版新的html v2(both english和Chinese)


**Bot:**

这是agent给我的output-

v2 完全沿用 v1 的结构（侧栏导航、总览表、逐行逐字段溯源、搜索），数据层换成修订后的工作簿状态，并新增了一个修订层：

总览页顶部多了 **"QA 审查与 v2 修订"** 区块——摘要 chips（1 处 ❌ 修正、2 处修订、3 处清空、7 条反驳、775 个溯源单元格）、6 项单元格改动明细表，以及可展开的反驳清单和 8 条未决事项。行详情页里，本轮涉及的每个字段都带彩色标签和说明：绿色"已补填"（B-ABLE 员工数）、琥珀色"已修订"（Rui、SNEHA 及 4 处 Notes 追加）、灰色"已清空"（Anudip/ONergy 服务人数、Hello Tractor 地区，空值提示也改为"移入 Notes"而非"无法确定"）、蓝色"保留 · 已反驳"（4 个 Medium、KKPKP、FY16 归属等）、浅色"保留 · 与建议一致"。改动过的单元格溯源条目也同步更新（如 B-ABLE 新增 slide 3 引用）。

中文版界面和修订说明为中文，单元格值与溯源原文保持英文（与 v1 一致）；两个文件都在无头浏览器里实测渲染无报错。
