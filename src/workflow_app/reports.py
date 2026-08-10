"""Human-readable renderings of review-cycle artifacts.

Machine state lives in the JSON artifacts; these markdown companions
exist for inspection (plan sections 26, 29). Non-PASS findings state
what evidence was checked, and human-review items carry both agents'
evidence so the V1 flow — read human_review.md, edit final.xlsx — needs
no other file.
"""


def _evidence_lines(evidence, indent="  "):
    return [
        f"{indent}- Evidence: {item.source_file}"
        + (f" ({item.source_location})" if item.source_location else "")
        + f" [{item.evidence_type}] — {item.evidence_text}"
        for item in evidence
    ]


def verdict_counts(findings):
    order = ("FAIL", "WARN", "PASS", "UNRESOLVED")
    counts = {verdict: 0 for verdict in order}
    for finding in findings:
        counts[finding.verdict] += 1
    return [(verdict, counts[verdict]) for verdict in order if counts[verdict]]


def action_counts(decisions):
    counts = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
    return sorted(counts.items())


def render_scoping_questions_md(questions):
    lines = [
        "# Scoping questions",
        "",
        "The Filler needs these answered before extraction starts.",
        "Write your answers into scoping_answers.md next to this file,",
        "then resume the run with the command printed when it paused.",
        "",
    ]
    for question in questions.questions:
        lines += [f"## {question.id}", "", question.question, ""]
    return "\n".join(lines)


def render_scoping_answers_template(questions):
    lines = [
        "# Scoping answers",
        "",
        "Replace each placeholder with your answer, then resume the run.",
        "",
    ]
    for question in questions.questions:
        lines += [
            f"## {question.id}",
            "",
            f"> {question.question}",
            "",
            "(your answer here)",
            "",
        ]
    return "\n".join(lines)


def render_no_scoping_questions():
    # The filler always reads an answers document; this is what it gets
    # when the scoping pass decided it had nothing to ask.
    return (
        "# Scoping answers\n\n"
        "The scoping pass had no questions: the task, sources, and\n"
        "workbook answered everything it needed.\n"
    )


def render_scoping_answers(questions, answers):
    lines = ["# Scoping answers", ""]
    for question in questions.questions:
        option_labels = {
            option.value: option.label for option in question.options or []
        }
        answer = answers[question.id]
        if isinstance(answer, list):
            rendered = [f"- {option_labels.get(value, value)}" for value in answer]
        elif isinstance(answer, bool):
            rendered = ["Yes" if answer else "No"]
        else:
            rendered = [option_labels.get(answer, answer)]
        lines += [
            f"## {question.id}",
            "",
            f"> {question.question}",
            "",
            *rendered,
            "",
        ]
    return "\n".join(lines)


def render_review_md(review):
    lines = ["# Review", ""]
    for verdict, count in verdict_counts(review.findings):
        lines.append(f"- {verdict}: {count}")
    lines.append("")
    for finding in review.findings:
        lines += [f"## {finding.cell} — {finding.verdict}", ""]
        if finding.recommended_value is not None:
            lines.append(f"- Recommended: {finding.recommended_value}")
        lines.append(f"- {finding.reviewer_comment}")
        if finding.verdict != "PASS":
            lines += _evidence_lines(finding.evidence, indent="")
        lines.append("")
    return "\n".join(lines)


def render_revision_log_md(decisions, outcomes):
    applied_refs = {
        outcome.mutation.source_ref
        for outcome in outcomes
        if outcome.status == "applied"
    }
    lines = ["# Revision log", ""]
    for index, decision in enumerate(decisions):
        marker = "applied" if f"decisions[{index}]" in applied_refs else "no write"
        lines.append(f"- {decision.cell} — {decision.action} ({marker})")
        lines.append(f"  - {decision.justification}")
        if decision.note_append is not None:
            lines.append(f"  - Note appended: {decision.note_append}")
    lines.append("")
    return "\n".join(lines)


def render_human_review_md(items):
    lines = ["# Human review", ""]
    if not items:
        lines.append("Nothing unresolved.")
    for item in items:
        reviewer = item["reviewer"]
        revision = item["revision"]
        lines += [
            f"## {item['cell']}",
            "",
            f"- Current value: {item['current_value']!r}",
            f"- Why automation stopped: {item['reason']}",
        ]
        if reviewer is not None:
            lines.append(
                f"- Reviewer ({reviewer['verdict']}):"
                f" recommended {reviewer['recommended_value']!r}"
                f" — {reviewer['comment']}"
            )
            lines += [
                f"  - Evidence: {e['source_file']}"
                + (f" ({e['source_location']})" if e.get("source_location") else "")
                + f" [{e['evidence_type']}] — {e['evidence_text']}"
                for e in reviewer["evidence"]
            ]
        if revision is not None:
            lines.append(
                f"- Revision ({revision['action']}):"
                f" proposed {revision['proposed_value']!r}"
                f" — {revision['justification']}"
            )
            lines += [
                f"  - Evidence: {e['source_file']}"
                + (f" ({e['source_location']})" if e.get("source_location") else "")
                + f" [{e['evidence_type']}] — {e['evidence_text']}"
                for e in revision["evidence"]
            ]
        if item["re_review"] is not None:
            lines.append(
                f"- Re-review: {item['re_review']['verdict']}"
                f" — {item['re_review']['comment']}"
            )
        lines.append("")
    return "\n".join(lines)
