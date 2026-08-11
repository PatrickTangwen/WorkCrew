"""Unit tests for the explorer HTML shell (plan section 22).

render_explorer_html is a pure function of (data, lang); assertions
inspect the produced source: embedded data integrity, bilingual UI
strings, and the interaction hooks the inline script provides.
"""

import json
import re

from workflow_app.provenance.explorer import STRINGS, render_explorer_html

DATA = {
    "title": "7) Practicum Courses",
    "title_field": "Organization",
    "overview_fields": ["Organization"],
    "rows": [
        {
            "row": 2,
            "title": "Health Org </script> & Co",
            "filled": 1,
            "folders": ["India 2008"],
            "merged_from": [],
            "fields": [
                {
                    "name": "Organization",
                    "column": "B",
                    "value": "Health Org </script> & Co <!--<script>",
                    "role": "filler",
                    "sources": [
                        {
                            "file": "current/workbook.txt",
                            "location": "row 2",
                            "text": "Applied workbook value.",
                            "type": "direct",
                        }
                    ],
                    "pill_values": None,
                    "gloss_zh": "组织名称",
                }
            ],
        }
    ],
    "folders": [{"name": "India 2008", "rows": [2], "merged_into": None}],
    "ungrouped_rows": [],
    "findings": [],
    "field_count": 1,
    "populated_cells": 1,
}


def embedded(html, name):
    match = re.search(rf"const {name} = (.*);$", html, re.MULTILINE)
    assert match, f"missing `const {name} = ...;` in the explorer source"
    return json.loads(match.group(1))


def test_embedded_data_round_trips_and_cannot_break_the_script():
    html = render_explorer_html(DATA, "en")

    # Neither "</script>" nor the "<!--<script>" double-escape opener
    # may reach the script element from data values.
    body = html.split("<script>", 1)[1]
    script_source = body.rsplit("</script>", 1)[0]
    assert "</script>" not in script_source
    assert "<!--" not in script_source
    assert embedded(html, "DATA") == DATA


def test_placeholder_sentinels_inside_data_survive_rendering():
    data = json.loads(json.dumps(DATA))
    data["rows"][0]["fields"][0]["value"] = "literal __STRINGS__ marker"
    html = render_explorer_html(data, "en")
    assert embedded(html, "DATA") == data


def test_language_variants_localize_chrome_not_data():
    en = render_explorer_html(DATA, "en")
    zh = render_explorer_html(DATA, "zh")

    assert '<html lang="en">' in en
    assert '<html lang="zh-CN">' in zh
    assert "PingFang SC" in zh
    assert "PingFang SC" not in en
    # Same embedded data either way; only the UI strings differ.
    assert embedded(en, "DATA") == embedded(zh, "DATA")
    assert embedded(en, "STRINGS") != embedded(zh, "STRINGS")


def test_ui_string_tables_stay_in_lockstep():
    assert STRINGS["en"].keys() == STRINGS["zh"].keys()


def test_shell_provides_the_interaction_hooks():
    html = render_explorer_html(DATA, "en")

    # The page's structural contract: search box, home button, sidebar
    # and main containers, highlight and collapse machinery.
    for hook in (
        'id="q"',
        'id="allrows"',
        'id="nav"',
        'id="main"',
        "<mark>",
        "show-empty",
    ):
        assert hook in html


def test_shell_exposes_proposal_and_final_audit_layers():
    data = json.loads(json.dumps(DATA))
    field = data["rows"][0]["fields"][0]
    field.update(
        {
            "proposal": {
                "status": "conflict",
                "value": "Candidate Org",
                "confidence": None,
                "evidence": [
                    {
                        "file": "source/record.txt",
                        "location": "line 1",
                        "text": "Two claims disagree.",
                        "type": "direct",
                    }
                ],
                "rules_applied": ["SOURCE_AUTHORITY"],
                "review_note": "Requires human adjudication.",
            },
            "review": {
                "verdict": "UNRESOLVED",
                "recommended_value": None,
                "comment": "The conflict remains.",
                "evidence": [],
                "missed_data": False,
            },
            "revision": {
                "action": "REBUT",
                "proposed_value": None,
                "note_append": "Keep unresolved for a human.",
                "justification": "The sources still conflict.",
                "evidence": [],
            },
            "re_review": {
                "verdict": "UPHELD",
                "comment": "The rebuttal does not resolve the conflict.",
            },
            "unresolved_reason": "protected source conflict requires human review",
        }
    )
    data["review_cycle"] = {
        "review_date": "2026-08-02",
        "verdict_counts": {"UNRESOLVED": 1},
        "action_counts": {"REBUT": 1},
        "re_review_counts": {"UPHELD": 1},
        "unresolved_count": 1,
        "change_counts": {
            "filled": 0,
            "revised": 0,
            "cleared": 0,
            "rebutted": 1,
        },
    }

    en = render_explorer_html(data, "en")
    zh = render_explorer_html(data, "zh")

    for marker in (
        "revision-summary",
        "revision-badge",
        "revision-note",
        "decision-audit",
        "audit-toggle",
        "status-badge",
        "proposal-meta",
        "proposal_value",
        "audit-card",
        "unresolved_reason",
        "rules_applied",
    ):
        assert marker in en
    assert "Proposal status" in en
    assert "Proposal value" in en
    assert "QA review & v2 revision ({date})" in en
    assert "This V2 incorporates the independent QA review." in en
    assert "only fields the workflow changed carry a tag" in en
    assert "QA 审阅与 V2 修订（{date}）" in zh
    assert "只有被工作流改动过的字段带标签" in zh
    assert "contains(proposal.value, needle)" in en
    assert "return evidenceHtml(f.sources, STRINGS.current_provenance)" in en
    assert "auditBadge('verdict', f.review.verdict)" in en
    assert "auditBadge('action', f.revision.action)" in en
    assert "auditBadge('re_review', f.re_review.verdict)" in en
    assert "revisionChangeHtml(f.revision_change)" in en
    assert "cycle.change_counts" in en
    assert "compactRevisionHtml(f) + sourcesHtml(f)" in en
    assert "decisionAuditHtml(f)" in en
    assert "提案状态" in zh
    assert "提案值" in zh
    strings = embedded(zh, "STRINGS")
    assert strings["verdict_unresolved"] == "未决"
    assert strings["action_rebut"] == "反驳"
    assert strings["re_review_upheld"] == "维持"
    assert strings["change_filled"] == "填充"
    assert strings["change_revised"] == "修改"
    assert strings["change_cleared"] == "清空"
    assert strings["change_rebutted"] == "反驳"
    assert strings["show_audit"] == "显示决策审计"


def test_v2_field_audit_is_limited_to_fields_the_workflow_changed():
    en = render_explorer_html(DATA, "en", version="v2")
    zh = render_explorer_html(DATA, "zh", version="v2")

    for kind in ("filled", "revised", "cleared", "rebutted"):
        assert embedded(en, "STRINGS")["revision_badge_" + kind]
    assert "function decisionAuditKind(f)" in en
    assert "if (f.revision_change) return f.revision_change.kind;" in en
    assert "f.revision.action === 'REBUT'" in en
    assert "if (!kind) return ''" in en
    assert "VERSION && decisionAuditKind(f) === null" in en
    assert "visibleDecisionAuditMatches(f, needle)" in en
    assert "r.fields.some(f => decisionAuditKind(f) !== null)" in en
    # A filled cell repeats neither an absent before value nor the
    # final value shown directly above its note.
    assert "f.revision_change && f.revision_change.before !== null" in en
    # A cleared cell reads as cleared, not as an ordinary blank.
    assert "f.revision_change.kind === 'cleared'" in en
    assert embedded(en, "STRINGS")["empty_cleared"] == "— cleared in the v2 revision"
    assert embedded(zh, "STRINGS")["empty_cleared"] == "—— 已在 v2 修订中清空"


def test_v2_overview_indexes_every_exception_field():
    en = render_explorer_html(DATA, "en", version="v2")

    assert "function exceptionIndex()" in en
    assert "changes.push(entry(changeDetailHtml(f.revision_change)))" in en
    assert "rebuttals.push(entry(" in en
    assert "unresolved.push(entry(hl(f.unresolved_reason)))" in en
    for key in ("summary_changes", "summary_rebuttals", "summary_unresolved"):
        assert f"exceptionTableHtml('{key}'" in en
    assert 'tr class="clickable" data-row=' in en
