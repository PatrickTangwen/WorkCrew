"""Single-file bilingual review explorer rendering (plan section 22).

Deterministic HTML generation — no agent involvement, no external
resources. The data model from render.build_explorer_data is embedded
as a JSON blob; the inline script renders the overview, per-row detail,
sidebar navigation, and search entirely client-side, so the file opens
directly from disk.
"""

import json
import re

STRINGS = {
    "en": {
        "app_title": "Review explorer",
        "search_placeholder": "Search rows, cells, provenance…",
        "all_rows": "All rows",
        "ungrouped": "Ungrouped rows",
        "merged_badge": "↦ row {n}",
        "merged_jump": "see row {n}",
        "merged_callout": "Folder(s) {names}: declared by the Filler as duplicates merged into this row.",
        "rows_suffix": "{n} rows",
        "stat_folders": "source folders",
        "stat_rows": "rows",
        "stat_fields": "columns",
        "stat_cells": "cells populated",
        "findings_heading": "Findings for review",
        "final_cycle_heading": "Final review cycle",
        "proposal_status": "Proposal status",
        "confidence": "Confidence",
        "applied_rules": "Applied rules",
        "review_note": "Review direction",
        "proposal_evidence": "Proposal evidence",
        "current_provenance": "Current workbook provenance",
        "reviewer": "Reviewer",
        "revision": "Revision",
        "re_review": "Re-review",
        "unresolved": "Unresolved",
        "recommended_value": "Recommended value",
        "proposed_value": "Proposed value",
        "note_append": "Note append",
        "verdicts": "Reviewer verdicts",
        "actions": "Revision actions",
        "re_reviews": "Re-review verdicts",
        "unresolved_items": "Unresolved items",
        "status_proposed": "Proposed",
        "status_not_found": "Not found",
        "status_ambiguous": "Ambiguous",
        "status_conflict": "Conflict · human review",
        "confidence_low": "Low",
        "confidence_medium": "Medium",
        "confidence_high": "High",
        "finding_unreadable_source": "Unreadable source",
        "finding_ambiguity": "Ambiguity",
        "finding_source_conflict": "Source conflict",
        "finding_merge": "Declared duplicate merge",
        "finding_extra_review": "Extra review",
        "col_row": "Row",
        "col_folder": "Folder",
        "col_filled": "Filled",
        "no_rows": "No rows to display.",
        "row_fallback": "Row {n}",
        "sheet_row_label": "Sheet row {n}",
        "fields_filled": "{filled}/{total} fields filled",
        "home": "← All rows",
        "prev": "← Row {n}",
        "next": "Row {n} →",
        "empty_value": "— left blank",
        "show_empty": "Show {n} empty fields",
        "hide_empty": "Hide {n} empty fields",
        "source_note": "",
        "footer_hint": "Generated deterministically from the draft workbook and provenance.",
    },
    "zh": {
        "app_title": "审阅浏览器",
        "search_placeholder": "搜索行、单元格、溯源…",
        "all_rows": "全部行",
        "ungrouped": "未分组行",
        "merged_badge": "↦ 第 {n} 行",
        "merged_jump": "见第 {n} 行",
        "merged_callout": "文件夹 {names}：Filler 声明其为重复来源，已并入本行。",
        "rows_suffix": "{n} 行",
        "stat_folders": "来源文件夹",
        "stat_rows": "行",
        "stat_fields": "列",
        "stat_cells": "已填单元格",
        "findings_heading": "待审阅发现",
        "final_cycle_heading": "最终审查周期",
        "proposal_status": "提案状态",
        "confidence": "置信度",
        "applied_rules": "已应用规则",
        "review_note": "审查方向",
        "proposal_evidence": "提案证据",
        "current_provenance": "当前工作簿溯源",
        "reviewer": "Reviewer 审查",
        "revision": "Revision 修订",
        "re_review": "复审",
        "unresolved": "未决",
        "recommended_value": "建议值",
        "proposed_value": "提议值",
        "note_append": "追加备注",
        "verdicts": "Reviewer 结论",
        "actions": "Revision 操作",
        "re_reviews": "复审结论",
        "unresolved_items": "未决事项",
        "status_proposed": "已提议",
        "status_not_found": "未找到",
        "status_ambiguous": "存在歧义",
        "status_conflict": "来源冲突 · 人工审查",
        "confidence_low": "低",
        "confidence_medium": "中",
        "confidence_high": "高",
        "finding_unreadable_source": "无法读取的来源",
        "finding_ambiguity": "歧义",
        "finding_source_conflict": "来源冲突",
        "finding_merge": "声明的重复合并",
        "finding_extra_review": "建议复核",
        "col_row": "行",
        "col_folder": "文件夹",
        "col_filled": "填充",
        "no_rows": "暂无行可显示。",
        "row_fallback": "第 {n} 行",
        "sheet_row_label": "表格行 {n}",
        "fields_filled": "已填 {filled}/{total} 个字段",
        "home": "← 全部行",
        "prev": "← 第 {n} 行",
        "next": "第 {n} 行 →",
        "empty_value": "—— 留空",
        "show_empty": "显示 {n} 个空字段",
        "hide_empty": "隐藏 {n} 个空字段",
        "source_note": "来源文件为英文原文，证据摘录保留原样。",
        "footer_hint": "由草稿工作簿与溯源数据确定性生成。",
    },
}

_ZH_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Segoe UI",sans-serif;line-height:1.6}
button{font-family:inherit}
h2.sec,table.ovr th{text-transform:none;letter-spacing:0}
.fieldrow{grid-template-columns:225px 1fr}
.fvalue.empty{font-style:normal}
"""

_SHELL = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f7f9;--surface:#fff;--border:#e3e6ea;--ink:#1d2430;--muted:#68717e;
--accent:#2563b0;--accent-soft:#eaf1fa;--accent-border:#c4d7ef;
--amber-bg:#fff7e6;--amber-border:#f0d9a8;--amber-ink:#8a6116;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.55;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.app{display:flex;height:100vh;overflow:hidden}
.side{width:300px;flex-shrink:0;background:var(--surface);border-right:1px solid var(--border);
display:flex;flex-direction:column}
.side-head{padding:14px 16px 8px}
.side-head h1{margin:0;font-size:15px}
.side-head .sub{font-size:11px;color:var(--muted);margin-top:4px}
.vtag{font-size:10px;background:var(--accent-soft);color:var(--accent);
border:1px solid var(--accent-border);border-radius:8px;padding:1px 6px;margin-left:6px}
.search{padding:8px 12px}
.search input{width:100%;padding:6px 9px;border:1px solid var(--border);border-radius:7px;font-size:13px}
.allrows{margin:0 12px 6px;padding:6px 9px;border-radius:7px;cursor:pointer;font-size:13px;
display:flex;gap:6px;align-items:center;border:1px solid transparent}
.allrows:hover{background:var(--accent-soft)}
.allrows.active{background:var(--accent-soft);border-color:var(--accent-border);color:var(--accent)}
.nav{flex:1;overflow-y:auto;padding:0 8px 14px}
.fhead{display:flex;align-items:center;gap:6px;padding:7px 6px;cursor:pointer;
font-size:12.5px;font-weight:600;border-radius:6px}
.fhead:hover{background:var(--accent-soft)}
.fhead .tri{font-size:9px;transition:transform .12s;color:var(--muted)}
.fgroup.open .tri{transform:rotate(90deg)}
.fname{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fbadge{font-size:10px;background:var(--amber-bg);color:var(--amber-ink);
border:1px solid var(--amber-border);border-radius:8px;padding:0 6px;white-space:nowrap}
.fcount{font-size:10.5px;color:var(--muted);white-space:nowrap}
.rowlist{display:none}
.fgroup.open .rowlist{display:block}
.rowitem{display:flex;gap:8px;padding:4px 6px 4px 22px;font-size:12.5px;cursor:pointer;
border-radius:6px;border-left:2px solid transparent;align-items:baseline}
.rowitem:hover{background:var(--accent-soft)}
.rowitem.active{background:var(--accent-soft);border-left-color:var(--accent)}
.rnum{font-family:var(--mono);font-size:11px;color:var(--muted);min-width:24px}
.rorg{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.side-foot{padding:10px 16px;font-size:10.5px;color:var(--muted);border-top:1px solid var(--border)}
.main{flex:1;overflow-y:auto}
.wrap{max-width:1060px;margin:0 auto;padding:22px 28px 60px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:9px;
padding:10px 16px;min-width:110px}
.stat .v{font-size:20px;font-weight:650}
.stat .l{font-size:11px;color:var(--muted)}
h2.sec{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:22px 0 8px}
.callout{background:var(--amber-bg);border:1px solid var(--amber-border);border-radius:8px;
padding:8px 12px;font-size:13px;margin-bottom:8px}
.notecall{background:var(--amber-bg);border:1px solid var(--amber-border);border-radius:8px;
padding:8px 12px;font-size:13px;margin:0 0 14px}
table.ovr{width:100%;border-collapse:collapse;background:var(--surface);
border:1px solid var(--border);border-radius:9px;overflow:hidden;font-size:13px}
table.ovr th{text-align:left;font-size:11px;letter-spacing:.05em;text-transform:uppercase;
color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--border);background:#fbfcfd}
table.ovr td{padding:7px 10px;border-bottom:1px solid var(--border);vertical-align:top}
table.ovr tr:last-child td{border-bottom:none}
tr.clickable{cursor:pointer}
tr.clickable:hover{background:var(--accent-soft)}
.rownum{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.fillnum{font-family:var(--mono);white-space:nowrap}
.pill{display:inline-block;background:var(--accent-soft);color:var(--accent);
border:1px solid var(--accent-border);border-radius:9px;padding:0 8px;font-size:11.5px;
margin:1px 3px 1px 0;white-space:nowrap}
.crumb{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--muted);margin-bottom:10px}
.crumb .home{color:var(--accent);cursor:pointer}
.crumb .home:hover{text-decoration:underline}
.navbtns{margin-left:auto;display:flex;gap:6px}
.navbtns button{border:1px solid var(--border);background:var(--surface);border-radius:7px;
padding:4px 10px;font-size:12px;cursor:pointer}
.navbtns button:hover:not(:disabled){background:var(--accent-soft)}
.navbtns button:disabled{opacity:.4;cursor:default}
.rowtitle h2{margin:0 0 2px;font-size:19px}
.rowtitle .meta{font-size:12px;color:var(--muted)}
.fieldcard{background:var(--surface);border:1px solid var(--border);border-radius:10px;
margin-top:14px;overflow:hidden}
.fieldrow{display:grid;grid-template-columns:215px 1fr;border-bottom:1px solid var(--border)}
.fieldrow:last-child{border-bottom:none}
.fieldrow.hit{background:#fffdf2}
.fname2{padding:9px 12px;font-size:12px;font-weight:600;border-right:1px solid var(--border);
cursor:help;overflow:hidden}
.colno{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);font-weight:400}
.gloss{display:block;font-size:11px;color:var(--muted);font-weight:400}
.fbody{padding:9px 12px;min-width:0}
.fvalue{font-size:13.5px;white-space:pre-wrap;word-break:break-word}
.fvalue.empty{color:var(--muted);font-style:italic;font-size:12.5px}
.srcs{margin-top:7px;padding-top:7px;border-top:1px dashed var(--border)}
.srclabel{font-size:10.5px;color:var(--muted);margin-bottom:4px}
.srcitem{display:flex;gap:8px;font-size:12px;margin-bottom:3px;align-items:baseline}
.srcfile{font-family:var(--mono);font-size:10.5px;background:var(--bg);
border:1px solid var(--border);border-radius:6px;padding:1px 7px;max-width:340px;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex-shrink:0;cursor:default}
.srcreason{color:var(--muted);min-width:0}
.etype{font-family:var(--mono);font-size:9.5px;color:var(--accent);background:var(--accent-soft);
border:1px solid var(--accent-border);border-radius:7px;padding:0 5px;white-space:nowrap}
.proposal-meta{margin-top:8px;padding:8px 10px;background:#fbfcfd;border:1px solid var(--border);
border-radius:8px;font-size:12px}
.meta-line{display:flex;gap:7px;align-items:baseline;margin:3px 0;flex-wrap:wrap}
.meta-label{font-size:10.5px;color:var(--muted);min-width:105px}
.status-badge,.audit-badge{display:inline-block;border-radius:8px;padding:1px 7px;
font-size:10.5px;font-weight:650;background:var(--accent-soft);color:var(--accent);
border:1px solid var(--accent-border)}
.status-conflict,.status-ambiguous,.audit-unresolved{background:var(--amber-bg);
color:var(--amber-ink);border-color:var(--amber-border)}
.rule-chip{display:inline-block;font-family:var(--mono);font-size:10px;background:var(--bg);
border:1px solid var(--border);border-radius:7px;padding:1px 6px;margin-right:3px}
.audit-stack{margin-top:8px;display:grid;gap:6px}
.audit-card{padding:8px 10px;border:1px solid var(--accent-border);border-radius:8px;
background:var(--accent-soft);font-size:12px}
.audit-card.unresolved{border-color:var(--amber-border);background:var(--amber-bg)}
.audit-title{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:650;margin-bottom:3px}
.quality-summary{margin:0 0 18px;padding:12px 14px;border:1px solid var(--accent-border);
background:var(--surface);border-radius:9px}
.quality-summary h2{font-size:13px;margin:0 0 8px}
.summary-group{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:5px}
.summary-label{font-size:10.5px;color:var(--muted);min-width:120px}
.summary-chip{font-size:10.5px;border:1px solid var(--border);background:var(--bg);
border-radius:8px;padding:1px 7px}
.hiddenrows{display:none}
.fieldcard.show-empty .hiddenrows{display:block}
.togglebar{padding:8px 12px;font-size:12px;color:var(--accent);cursor:pointer;
border-top:1px solid var(--border);background:#fbfcfd}
.togglebar:hover{background:var(--accent-soft)}
mark{background:#ffe9a8;padding:0 1px;border-radius:2px}
__ZH_CSS__
@media (max-width:860px){
.app{flex-direction:column}
.side{width:100%;max-height:45vh}
.fieldrow{grid-template-columns:1fr}
.fname2{border-right:none;border-bottom:1px solid var(--border)}
}
</style>
</head>
<body>
<div class="app">
<aside class="side">
  <div class="side-head"><h1 id="side-title"></h1><div class="sub" id="side-sub"></div></div>
  <div class="search"><input id="q" type="search" placeholder="__SEARCH_PLACEHOLDER__"></div>
  <div class="allrows" id="allrows"><span>⌂</span><span>__ALL_ROWS__</span></div>
  <nav class="nav" id="nav"></nav>
  <div class="side-foot">__FOOTER_HINT__</div>
</aside>
<main class="main" id="scroller"><div class="wrap" id="main"></div></main>
</div>
<script>
const DATA = __DATA__;
const STRINGS = __STRINGS__;
const VERSION = __VERSION__;
const ZH = document.documentElement.lang === 'zh-CN';

const t = (key, vars) => Object.entries(vars || {}).reduce(
  (s, [k, v]) => s.replaceAll('{' + k + '}', String(v)), STRINGS[key]);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const rowByNum = {};
for (const r of DATA.rows) rowByNum[r.row] = r;
const rowTitle = r => r.title === null ? t('row_fallback', {n: r.row}) : String(r.title);

const state = {row: null, query: '', closed: new Set()};

// Highlight matches, escaping around them — never escape before matching.
function hl(text) {
  const s = String(text), q = state.query.trim();
  if (!q) return esc(s);
  const lower = s.toLowerCase(), needle = q.toLowerCase();
  let out = '', i = 0;
  while (true) {
    const j = lower.indexOf(needle, i);
    if (j < 0) { out += esc(s.slice(i)); break; }
    out += esc(s.slice(i, j)) + '<mark>' + esc(s.slice(j, j + q.length)) + '</mark>';
    i = j + q.length;
  }
  return out;
}

const contains = (text, needle) =>
  text !== null && text !== undefined &&
  String(text).toLowerCase().includes(needle);

const sourceMatches = (s, needle) =>
  contains(s.text, needle) || contains(s.file, needle) || contains(s.location, needle) ||
  contains(s.type, needle);
const evidenceMatches = (items, needle) =>
  (items || []).some(item => sourceMatches(item, needle));
const auditMatches = (item, needle) => item && (
  Object.values(item).some(value => !Array.isArray(value) && contains(value, needle)) ||
  evidenceMatches(item.evidence, needle));
function rowMatches(r, q) {
  if (!q) return true;
  const needle = q.toLowerCase();
  if (contains(r.title, needle)) return true;
  if (r.folders.some(f => contains(f, needle))) return true;
  return r.fields.some(f => fieldMatches(f, q));
}
const fieldMatches = (f, q) => {
  if (!q) return false;
  const needle = q.toLowerCase();
  const proposal = f.proposal;
  return contains(f.name, needle) || contains(f.value, needle) ||
    evidenceMatches(f.sources, needle) ||
    (proposal && (contains(proposal.status, needle) ||
      contains(proposal.confidence, needle) ||
      contains(proposal.review_note, needle) ||
      proposal.rules_applied.some(rule => contains(rule, needle)) ||
      evidenceMatches(proposal.evidence, needle))) ||
    auditMatches(f.review, needle) || auditMatches(f.revision, needle) ||
    auditMatches(f.re_review, needle) || contains(f.unresolved_reason, needle);
};

function groupHtml(name, label, badge, items) {
  const open = state.closed.has(name) ? '' : ' open';
  return '<div class="fgroup' + open + '" data-folder="' + esc(name) + '">' +
    '<div class="fhead"><span class="tri">▶</span><span class="fname">' + hl(label) +
    '</span>' + badge + '</div><div class="rowlist">' + items + '</div></div>';
}
const rowItemHtml = (r, prefix) =>
  '<div class="rowitem' + (state.row === r.row ? ' active' : '') + '" data-row="' + r.row +
  '"><span class="rnum">' + (prefix || '') + r.row + '</span><span class="rorg">' +
  hl(rowTitle(r)) + '</span></div>';

function renderNav() {
  const q = state.query.trim();
  let html = '';
  for (const folder of DATA.folders) {
    if (folder.merged_into !== null) {
      const target = rowByNum[folder.merged_into];
      if (q && !rowMatches(target, q) && !contains(folder.name, q.toLowerCase())) continue;
      const badge = '<span class="fbadge">' +
        esc(t('merged_badge', {n: target.row})) + '</span>';
      const reason = folder.merge_reason ? ' ' + folder.merge_reason : '';
      const jump = '<div class="rowitem' + (state.row === target.row ? ' active' : '') +
        '" data-row="' + target.row + '" title="' +
        esc(t('merged_callout', {names: folder.name}) + reason) + '"><span class="rnum">→' +
        target.row + '</span><span class="rorg">' +
        esc(t('merged_jump', {n: target.row})) + ' · ' + hl(rowTitle(target)) +
        '</span></div>';
      html += groupHtml(folder.name, folder.name, badge, jump);
      continue;
    }
    const rows = folder.rows.map(n => rowByNum[n]).filter(r => rowMatches(r, q));
    if (q && !rows.length && !contains(folder.name, q.toLowerCase())) continue;
    const count = '<span class="fcount">' + t('rows_suffix', {n: rows.length}) + '</span>';
    html += groupHtml(folder.name, folder.name, count,
      rows.map(r => rowItemHtml(r)).join(''));
  }
  const ungrouped = DATA.ungrouped_rows.map(n => rowByNum[n])
    .filter(r => rowMatches(r, q));
  if (ungrouped.length) {
    const count = '<span class="fcount">' + t('rows_suffix', {n: ungrouped.length}) + '</span>';
    html += groupHtml('', STRINGS.ungrouped, count,
      ungrouped.map(r => rowItemHtml(r)).join(''));
  }
  const nav = document.getElementById('nav');
  nav.innerHTML = html;
  for (const head of nav.querySelectorAll('.fhead')) {
    head.addEventListener('click', () => {
      const name = head.parentElement.dataset.folder;
      if (state.closed.has(name)) state.closed.delete(name);
      else state.closed.add(name);
      render();
    });
  }
  for (const item of nav.querySelectorAll('.rowitem')) {
    item.addEventListener('click', () => { state.row = Number(item.dataset.row); render(); });
  }
}

const pillsHtml = values => values
  .map(part => '<span class="pill">' + hl(part) + '</span>').join('');

function valueHtml(f) {
  if (f.value === null) return '<div class="fvalue empty">' + esc(STRINGS.empty_value) + '</div>';
  if (f.pill_values) return '<div class="fvalue">' + pillsHtml(f.pill_values) + '</div>';
  return '<div class="fvalue">' + hl(f.value) + '</div>';
}
function evidenceHtml(items, heading) {
  if (!items || !items.length) return '';
  const sourceNote = STRINGS.source_note
    ? '<div class="srclabel">' + esc(STRINGS.source_note) + '</div>' : '';
  const label = heading
    ? '<div class="srclabel">' + esc(heading) + '</div>' : sourceNote;
  return '<div class="srcs">' + label + items.map(s => {
    const chip = s.file
      ? '<span class="srcfile" title="' + esc(s.file) + '">' + hl(s.file) + '</span>' : '';
    const type = s.type ? '<span class="etype">' + hl(s.type) + '</span>' : '';
    const location = s.location ? hl(s.location) + ' — ' : '';
    return '<div class="srcitem">' + chip + type + '<span class="srcreason">' + location +
      hl(s.text) + '</span></div>';
  }).join('') + '</div>';
}
function sourcesHtml(f) {
  if (f.proposal && f.role === 'filler') return '';
  return evidenceHtml(f.sources, STRINGS.current_provenance);
}
const enumLabel = (prefix, value) => {
  if (value === null || value === undefined) return '—';
  return STRINGS[prefix + '_' + String(value).toLowerCase()] || String(value);
};
function proposalMetaHtml(f) {
  const p = f.proposal;
  if (!p) return '';
  const rules = p.rules_applied.length
    ? p.rules_applied.map(rule => '<span class="rule-chip">' + hl(rule) + '</span>').join('')
    : '—';
  return '<div class="proposal-meta">' +
    '<div class="meta-line"><span class="meta-label">' + esc(STRINGS.proposal_status) +
    '</span><span class="status-badge status-' + esc(p.status) + '">' +
    esc(enumLabel('status', p.status)) + '</span></div>' +
    '<div class="meta-line"><span class="meta-label">' + esc(STRINGS.confidence) +
    '</span><span>' + esc(enumLabel('confidence', p.confidence)) + '</span></div>' +
    '<div class="meta-line"><span class="meta-label">' + esc(STRINGS.applied_rules) +
    '</span><span>' + rules + '</span></div>' +
    '<div class="meta-line"><span class="meta-label">' + esc(STRINGS.review_note) +
    '</span><span>' + hl(p.review_note || '—') + '</span></div>' +
    evidenceHtml(p.evidence, STRINGS.proposal_evidence) + '</div>';
}
const auditBadge = value => '<span class="audit-badge">' + esc(value) + '</span>';
function auditHtml(f) {
  const cards = [];
  if (f.review) {
    const recommended = f.review.recommended_value === null ? '' :
      '<div><b>' + esc(STRINGS.recommended_value) + ':</b> ' +
      hl(f.review.recommended_value) + '</div>';
    cards.push('<div class="audit-card"><div class="audit-title">' +
      esc(STRINGS.reviewer) + auditBadge(f.review.verdict) + '</div>' +
      '<div>' + hl(f.review.comment) + '</div>' + recommended +
      evidenceHtml(f.review.evidence, '') + '</div>');
  }
  if (f.revision) {
    const proposed = f.revision.proposed_value === null ? '' :
      '<div><b>' + esc(STRINGS.proposed_value) + ':</b> ' +
      hl(f.revision.proposed_value) + '</div>';
    const note = f.revision.note_append === null ? '' :
      '<div><b>' + esc(STRINGS.note_append) + ':</b> ' + hl(f.revision.note_append) + '</div>';
    cards.push('<div class="audit-card"><div class="audit-title">' +
      esc(STRINGS.revision) + auditBadge(f.revision.action) + '</div>' +
      '<div>' + hl(f.revision.justification) + '</div>' + proposed + note +
      evidenceHtml(f.revision.evidence, '') + '</div>');
  }
  if (f.re_review) {
    cards.push('<div class="audit-card"><div class="audit-title">' +
      esc(STRINGS.re_review) + auditBadge(f.re_review.verdict) + '</div><div>' +
      hl(f.re_review.comment) + '</div></div>');
  }
  if (f.unresolved_reason) {
    cards.push('<div class="audit-card unresolved"><div class="audit-title">' +
      esc(STRINGS.unresolved) + '<span class="audit-badge audit-unresolved">!</span></div>' +
      '<div>' + hl(f.unresolved_reason) + '</div></div>');
  }
  return cards.length ? '<div class="audit-stack">' + cards.join('') + '</div>' : '';
}
const fieldRowHtml = f =>
  '<div class="fieldrow' + (fieldMatches(f, state.query.trim()) ? ' hit' : '') + '">' +
  '<div class="fname2" title="' + esc(f.name) + '"><span class="colno">' +
  (f.column ? 'col ' + esc(f.column) : '—') + '</span>' + esc(f.name) +
  (f.gloss_zh && ZH ? '<span class="gloss">' + esc(f.gloss_zh) + '</span>' : '') +
  '</div><div class="fbody">' + valueHtml(f) + proposalMetaHtml(f) + sourcesHtml(f) +
  auditHtml(f) + '</div></div>';

function renderRow(r) {
  const index = DATA.rows.indexOf(r);
  const prev = DATA.rows[index - 1], next = DATA.rows[index + 1];
  const visible = r.fields.filter(f => f.value !== null || f.proposal || f.review ||
    f.revision || f.re_review || f.unresolved_reason);
  const empty = r.fields.filter(f => !visible.includes(f));

  let html = '<div class="crumb"><span class="home" id="homelink">' + esc(STRINGS.home) +
    '</span><span>/</span><span>' + esc(r.folders[0] || STRINGS.ungrouped) +
    '</span><span class="navbtns">' +
    '<button id="prevb"' + (prev ? '' : ' disabled') + '>' +
    (prev ? t('prev', {n: prev.row}) : '·') + '</button>' +
    '<button id="nextb"' + (next ? '' : ' disabled') + '>' +
    (next ? t('next', {n: next.row}) : '·') + '</button></span></div>';

  html += '<div class="rowtitle"><h2>' + hl(rowTitle(r)) + '</h2><div class="meta">' +
    t('sheet_row_label', {n: r.row}) + ' · ' +
    t('fields_filled', {filled: r.filled, total: DATA.field_count}) + '</div></div>';

  if (r.merged_from.length) {
    const reasons = r.merged_from.map(n => {
      const f = DATA.folders.find(x => x.name === n);
      return f && f.merge_reason ? ' ' + f.merge_reason : '';
    }).join('');
    html += '<div class="notecall">' +
      esc(t('merged_callout', {names: r.merged_from.join(', ')}) + reasons) + '</div>';
  }

  // A search hit inside a collapsed empty field must be visible.
  const revealEmpty = empty.some(f => fieldMatches(f, state.query.trim()));
  html += '<div class="fieldcard' + (revealEmpty ? ' show-empty' : '') + '" id="fcard">' +
    visible.map(fieldRowHtml).join('') +
    (empty.length
      ? '<div class="hiddenrows">' + empty.map(fieldRowHtml).join('') + '</div>' +
        '<div class="togglebar" id="tgl">' +
        t(revealEmpty ? 'hide_empty' : 'show_empty', {n: empty.length}) + '</div>'
      : '') + '</div>';

  const main = document.getElementById('main');
  main.innerHTML = html;
  document.getElementById('homelink').addEventListener('click', () => { state.row = null; render(); });
  if (prev) document.getElementById('prevb').addEventListener('click', () => { state.row = prev.row; render(); });
  if (next) document.getElementById('nextb').addEventListener('click', () => { state.row = next.row; render(); });
  const card = document.getElementById('fcard'), toggle = document.getElementById('tgl');
  if (toggle) toggle.addEventListener('click', () => {
    card.classList.toggle('show-empty');
    toggle.textContent = card.classList.contains('show-empty')
      ? t('hide_empty', {n: empty.length}) : t('show_empty', {n: empty.length});
  });
}

function summaryGroupHtml(label, counts) {
  const chips = Object.entries(counts).map(([name, count]) =>
    '<span class="summary-chip">' + esc(name) + ' · ' + count + '</span>').join('');
  return '<div class="summary-group"><span class="summary-label">' + esc(label) +
    '</span>' + (chips || '<span class="summary-chip">0</span>') + '</div>';
}
function qualitySummaryHtml() {
  const cycle = DATA.review_cycle;
  if (!cycle) return '';
  return '<section class="quality-summary"><h2>' + esc(STRINGS.final_cycle_heading) +
    '</h2>' + summaryGroupHtml(STRINGS.verdicts, cycle.verdict_counts) +
    summaryGroupHtml(STRINGS.actions, cycle.action_counts) +
    summaryGroupHtml(STRINGS.re_reviews, cycle.re_review_counts) +
    '<div class="summary-group"><span class="summary-label">' +
    esc(STRINGS.unresolved_items) + '</span><span class="summary-chip">' +
    cycle.unresolved_count + '</span></div></section>';
}

function renderOverview() {
  let html = '<div class="stats">' + [
    [DATA.folders.length, STRINGS.stat_folders],
    [DATA.rows.length, STRINGS.stat_rows],
    [DATA.field_count, STRINGS.stat_fields],
    [DATA.populated_cells, STRINGS.stat_cells],
  ].map(([v, l]) => '<div class="stat"><div class="v">' + v + '</div><div class="l">' +
    esc(l) + '</div></div>').join('') + '</div>';

  html += qualitySummaryHtml();

  if (DATA.findings.length) {
    html += '<h2 class="sec">' + esc(STRINGS.findings_heading) + '</h2>';
    html += DATA.findings.map(f =>
      '<div class="callout"><b>' + esc(STRINGS['finding_' + f.kind]) + ':</b> ' +
      hl(f.ref) + (f.detail ? ' — ' + hl(f.detail) : '') + '</div>').join('');
  }

  const headers = ['<th>' + esc(STRINGS.col_row) + '</th>', '<th>' + esc(STRINGS.col_folder) + '</th>']
    .concat(DATA.overview_fields.map(name => '<th>' + esc(name) + '</th>'))
    .concat(['<th>' + esc(STRINGS.col_filled) + '</th>']);
  const body = DATA.rows.length ? DATA.rows.map(r => {
    const cells = ['<td class="rownum">' + r.row + '</td>',
      '<td>' + esc(r.folders[0] || '—') + '</td>'];
    for (const name of DATA.overview_fields) {
      const f = r.fields.find(x => x.name === name);
      const value = f && f.value !== null
        ? (f.pill_values ? pillsHtml(f.pill_values) : hl(f.value)) : '—';
      cells.push('<td>' + value + '</td>');
    }
    cells.push('<td class="fillnum">' + r.filled + '/' + DATA.field_count + '</td>');
    return '<tr class="clickable" data-row="' + r.row + '">' + cells.join('') + '</tr>';
  }).join('') : '<tr><td colspan="' + headers.length + '">' + esc(STRINGS.no_rows) + '</td></tr>';

  const main = document.getElementById('main');
  main.innerHTML = html + '<h2 class="sec">' + esc(DATA.title) + '</h2>' +
    '<table class="ovr"><thead><tr>' + headers.join('') + '</tr></thead><tbody>' +
    body + '</tbody></table>';
  for (const tr of main.querySelectorAll('tr.clickable')) {
    tr.addEventListener('click', () => { state.row = Number(tr.dataset.row); render(); });
  }
}

function render() {
  renderNav();
  const home = document.getElementById('allrows');
  const current = state.row !== null ? rowByNum[state.row] : undefined;
  home.classList.toggle('active', !current);
  if (current) renderRow(current); else renderOverview();
  document.getElementById('scroller').scrollTop = 0;
}

document.getElementById('side-title').innerHTML = esc(STRINGS.app_title) +
  (VERSION ? '<span class="vtag">' + esc(VERSION) + '</span>' : '');
document.getElementById('side-sub').textContent = DATA.title;
document.getElementById('q').addEventListener('input', event => {
  state.query = event.target.value;
  render();
});
document.getElementById('allrows').addEventListener('click', () => { state.row = null; render(); });
render();
</script>
</body>
</html>
"""


def _embed_json(value):
    # Escaping every "<" as < keeps "</script>", "<!--", and
    # "<script" sequences inside data from ever reaching the HTML
    # script-data tokenizer states.
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def render_explorer_html(data, lang, version=""):
    strings = STRINGS[lang]
    title = f"{data['title']} — {strings['app_title']}"
    if version:
        title += f" · {version}"
    payload = {
        "LANG": "zh-CN" if lang == "zh" else "en",
        "TITLE": title,
        "ZH_CSS": _ZH_CSS if lang == "zh" else "",
        "SEARCH_PLACEHOLDER": strings["search_placeholder"],
        "ALL_ROWS": strings["all_rows"],
        "FOOTER_HINT": strings["footer_hint"],
        "DATA": _embed_json(data),
        "STRINGS": _embed_json(strings),
        "VERSION": _embed_json(version),
    }
    # Single pass, so substituted payloads are never rescanned for
    # placeholder sentinels that data values might contain.
    return re.sub(r"__([A-Z_]+?)__", lambda match: payload[match.group(1)], _SHELL)
