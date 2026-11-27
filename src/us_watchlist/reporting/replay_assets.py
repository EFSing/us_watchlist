"""Inline styles and interactions for the standalone replay report."""

STYLE = """
:root {
  color-scheme: light;
  --bg: #f3f5f7;
  --surface: #fff;
  --surface-2: #f7f9fa;
  --text: #18232d;
  --muted: #53636f;
  --border: #d9e0e5;
  --accent: #28658a;
  --warning: #855300;
  --radius: 7px;
  --nav-height: 46px;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-variant-numeric: tabular-nums;
}
main { width: min(1440px, 100%); margin: auto; padding: 18px 24px 34px; }
h1, h2, h3, h4, p { margin: 0; }
h1 { font-size: clamp(25px, 3vw, 33px); line-height: 1.3; margin: 4px 0; }
h2 { font-size: 22px; }
h3 { font-size: 17px; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
[hidden] { display: none !important; }
.site-header, .section-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 10px 24px; flex-wrap: wrap;
}
.site-header { padding: 3px 0 13px; }
.eyebrow, .section-kicker { color: var(--accent); font-size: 13px; font-weight: bold; }
.date { color: var(--muted); padding-top: 5px; }
.date strong { color: var(--text); font-size: 18px; }
.muted, .section-note, .note, dt { color: var(--muted); }
.section-note, .note { font-size: 14px; }
.section-note { margin-top: 2px; }
.pills, .ticker-list { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.pill {
  display: inline-block; padding: 2px 9px; border: 1px solid var(--border);
  border-radius: 999px; background: var(--surface); color: var(--muted); font-size: 13px;
}
.pill.warning { color: var(--warning); border-color: #e4c990; }
.section-nav {
  position: sticky; top: 0; z-index: 2; display: flex; gap: 2px;
  overflow-x: auto; overscroll-behavior-inline: contain; background: var(--bg);
  border-block: 1px solid var(--border);
}
.section-nav a {
  flex: 0 0 auto; display: inline-flex; align-items: center; min-height: var(--nav-height);
  padding: 6px 13px; color: var(--muted); font-size: 14px; text-decoration: none;
}
.section-nav a:hover, .section-nav a[aria-current="location"] {
  color: var(--accent); background: var(--surface); box-shadow: inset 0 -2px 0 var(--accent);
}
.panel {
  min-width: 0; margin: 18px 0; padding: 18px; border: 1px solid var(--border);
  border-radius: var(--radius); background: var(--surface);
}
[id] { scroll-margin-top: calc(var(--nav-height) + 8px); }
.section-head { margin-bottom: 13px; }
.overview-grid {
  display: grid; grid-template-columns: 1.3fr 1fr; gap: 1px;
  border: 1px solid var(--border); background: var(--border);
}
.overview-lead, .overview-facts { padding: 14px; min-width: 0; }
.overview-lead { background: var(--surface-2); }
.overview-lead strong { display: block; font-size: 20px; margin: 1px 0 4px; }
.overview-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; background: var(--surface); }
dl { margin: 0; }
dt { font-size: 13px; }
dd { margin: 2px 0 0; font-weight: bold; overflow-wrap: anywhere; }
.overview-facts dd { font-size: 19px; font-variant-numeric: tabular-nums; }
.decision-grid { display: grid; grid-template-columns: repeat(var(--rule-count), minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.decision-grid a {
  display: block; padding: 9px 12px; border: 1px solid var(--border); border-top: 2px solid var(--accent);
  background: var(--surface-2); color: var(--text); text-decoration: none;
}
.decision-grid span, .decision-grid small { display: block; color: var(--muted); }
.decision-grid strong { display: block; font-size: 23px; line-height: 1.3; }
.decision-grid a:hover, .ticker-list a:hover { border-color: var(--accent); background: #eef5f9; }
.callout { margin-top: 12px; padding: 9px 12px; border-left: 3px solid var(--accent); background: #eef5f9; font-size: 14px; }
.callout.warning { border-color: var(--warning); background: #fff8e8; }
.candidate-group { display: grid; grid-template-columns: minmax(180px, 1fr) 4fr; gap: 5px 14px; padding: 9px 0; }
.candidate-group + .candidate-group { border-top: 1px solid var(--border); }
.ticker-list a {
  padding: 0 7px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface-2);
  font-size: 14px; font-weight: bold; text-decoration: none;
}
.rule-group + .rule-group { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }
.watch-list { display: grid; gap: 8px; }
.watch-card { min-width: 0; padding: 11px 13px; border: 1px solid var(--border); border-left: 3px solid var(--accent); }
.watch-card:target { outline: 2px solid var(--accent); }
.watch-head { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 3px 8px; margin-bottom: 9px; }
.watch-head :is(h3, h4) { font-size: 20px; line-height: 1.2; }
.watch-columns { min-width: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.watch-facts, .volume-card { min-width: 0; padding: 8px 10px; border: 1px solid var(--border); background: var(--surface-2); }
.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px 13px; margin-top: 5px; }
.volume-card .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ratio-track { position: relative; display: block; height: 4px; margin-top: 3px; border-radius: 4px; background: #e1e9ee; }
.ratio-track i { display: block; height: 100%; border-radius: inherit; background: var(--accent); }
.ratio-track::after { content: ""; position: absolute; inset: -1px auto -1px 50%; width: 1px; background: var(--warning); }
details > summary { cursor: pointer; color: var(--accent); }
.fold { margin-top: 12px; border: 1px solid var(--border); background: var(--surface-2); }
.fold > summary { padding: 9px 12px; font-weight: bold; }
.fold-content { padding: 0 12px 12px; min-width: 0; overflow-wrap: anywhere; }
.watch-card details { margin-top: 8px; font-size: 14px; }
.watch-card details p { margin: 6px 0 0; }
.empty { padding: 11px 12px; border: 1px dashed var(--border); background: var(--surface-2); color: var(--muted); }
.reason-list { display: flex; flex-wrap: wrap; gap: 5px 16px; margin: 0 0 10px; padding-left: 1.2em; font-size: 14px; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 5px 10px; margin: 8px 0; }
input, button { color: var(--text); font: inherit; }
input[type=search] { width: min(300px, 100%); padding: 7px 9px; border: 1px solid #aebbc4; border-radius: 4px; }
button { padding: 5px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); cursor: pointer; color: var(--accent); }
table { width: 100%; border-collapse: collapse; font-size: 14px; background: var(--surface); }
th, td { padding: 6px 8px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); }
thead th { background: #edf2f5; }
td small { display: block; color: var(--muted); }
.audit-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; margin: 9px 0; border: 1px solid var(--border); background: var(--border); }
.audit-grid div { min-width: 0; padding: 7px 9px; background: var(--surface); }
.audit-grid dd, .raw-error { font-size: 14px; font-weight: normal; overflow-wrap: anywhere; }
code { font-family: inherit; }
@media (max-width: 760px) {
  main { padding: 12px 10px 24px; }
  .panel { padding: 12px; margin: 13px 0; }
  .overview-grid, .candidate-group, .watch-columns, .audit-grid { grid-template-columns: minmax(0, 1fr); }
  .overview-lead, .overview-facts { padding: 10px; }
  .decision-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .date { padding-top: 0; }
  .site-header { gap: 7px; }
}
@media (max-width: 480px) {
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .section-nav a { padding-inline: 10px; }
  th, td { padding: 5px 6px; }
}
"""

RESEARCH_STYLE = """
.research-overview { margin-bottom: 14px; }
.research-lists { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.research-list { padding: 10px 12px; background: #eef5f9; border: 1px solid var(--border); border-top: 3px solid var(--accent); }
.research-list h3 span { display: inline-block; margin-left: 4px; color: var(--accent); }
.research-list .ticker-list { margin-top: 6px; }
.research-list .ticker-list a { padding: 4px 9px; background: var(--surface); }
.research-list .ticker-list a:hover { background: #eef5f9; }
.research-stage {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 12px;
  margin-bottom: 8px; padding: 7px 9px; background: #eef5f9; color: var(--accent);
}
.research-stage p { flex-basis: 100%; }
.watch-research-grid { display: grid; grid-template-columns: minmax(0, 4fr) minmax(0, 6fr); gap: 8px; align-items: start; }
.plan-prices { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; margin: 8px 0; }
.plan-prices div { padding: 5px 7px; background: var(--surface); border: 1px solid var(--border); min-width: 0; }
.plan-prices dd { font-size: 18px; }
.research-metric {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(80px, .65fr) auto;
  grid-template-areas: "label meter value" "explanation explanation explanation" "hypothesis hypothesis hypothesis";
  gap: 2px 10px; margin-top: 7px; padding: 6px 0 0; border-top: 1px solid var(--border);
}
.research-metric dt { grid-area: label; color: var(--text); font-weight: bold; }
.research-metric dd { grid-area: value; margin: 0; }
.research-meter { grid-area: meter; align-self: center; }
.ratio-track.share::after { display: none; }
.research-metric p { grid-area: explanation; }
.research-metric small { grid-area: hypothesis; color: var(--muted); }
.research-coordinate { grid-column: 1 / -1; color: var(--accent); font-size: 13px; }
.research-conclusion { margin-top: 8px; padding: 5px 7px; background: var(--surface); border-left: 2px solid var(--accent); font-size: 14px; }
.research-conclusion p { margin: 2px 0 0; }
@media (max-width: 1000px) {
  .plan-prices { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .research-lists, .watch-research-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 480px) {
  .research-metric { grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: "label value" "meter meter" "explanation explanation" "hypothesis hypothesis"; }
}
"""

WORKBENCH_STYLE = """
.workbench {
  --bg: #eef3f5; --surface-2: #f4f8fa; --text: #112534; --muted: #47616e;
  --border: #d2dfe4; --accent: #13627e; --radius: 12px;
}
.workbench .site-header {
  border-radius: 14px; background: #122c3b; color: #f4faff; padding: 19px 23px; margin-bottom: 10px;
}
.workbench .site-header .eyebrow, .workbench .date { color: #a8ccd7; }
.workbench .date strong { color: #f4faff; }
.workbench .site-header .pill { background: #1a3b4c; border-color: #416477; color: #e2eff7; }
.workbench .section-nav { border-radius: 8px; border-inline: 1px solid var(--border); }
.workbench .panel { box-shadow: 0 2px 5px #183a4e0b; }
.workbench .panel.fold { background: var(--surface); }
.workbench .overview-grid { border-radius: 8px; overflow: hidden; }
.market-pulse { margin-top: 16px; }
.market-state { padding: 3px 10px; border-radius: 6px; background: #e6f1f5; color: #134f67; font-size: 14px; }
.breadth-grid, .style-grid { display: grid; gap: 8px; }
.breadth-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.breadth-grid > div { padding: 9px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; }
.breadth-grid dd { font-size: 21px; }
.breadth-grid small, .style-card small { color: var(--muted); font-size: 12px; font-weight: normal; }
.style-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 8px; }
.style-card, .style-badge { --style-bg: #edf1f4; --style-text: #435665; --style-edge: #9caeb8; }
.defensive { --style-bg: #e5f6ef; --style-text: #14594b; --style-edge: #61ac99; }
.growth { --style-bg: #eeedff; --style-text: #3b3b82; --style-edge: #9291dc; }
.cyclical { --style-bg: #fff3d9; --style-text: #72450d; --style-edge: #d9aa5a; }
.style-card {
  border: 1px solid var(--border); border-top: 3px solid var(--style-edge); border-radius: 8px;
  background: var(--style-bg); padding: 8px 12px;
}
.style-card h4 { color: var(--style-text); }
.style-card dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 8px; margin-top: 4px; }
.style-card dd { font-size: 15px; }
.style-badge {
  display: inline-block; padding: 2px 7px; border: 1px solid var(--style-edge); border-radius: 5px;
  background: var(--style-bg); color: var(--style-text); font-size: 12px; font-weight: 650; white-space: nowrap;
}
.sector-leaders { margin-top: 9px; color: var(--muted); font-size: 14px; }
.sector-leaders strong { color: var(--text); margin-right: 6px; }
.up { color: #096345; }
.down { color: #a6273a; }
.change { font-weight: 650; white-space: nowrap; }
.workbench .decision-grid a { border-radius: 7px; }
.workbench .ticker-list a small { color: var(--muted); font-weight: 500; overflow-wrap: anywhere; }
.workbench-subsection { margin-top: 17px; }
.workbench-subsection > h3 { font-size: 19px; margin-bottom: 7px; }
.count { padding-left: 4px; color: var(--muted); font-weight: 500; font-size: 14px; }
.core-card { padding: 13px 15px; border-left: 1px solid var(--border); border-radius: 9px; }
.pill.signal-fresh { color: #075445; background: #cefae9; border-color: #58aa92; font-weight: 700; }
.pill.signal-continuing { color: #46596a; background: #eff3f6; border-color: #cbd5de; }
.pill.signal-aligned { color: #285478; background: #eaf4fc; border-color: #a5c5de; }
.quote-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; align-items: start; }
.quote-head h4 { font-size: 20px; line-height: 1.25; }
.quote-head .ticker { color: #134e68; font-weight: 800; }
.company-name { font-weight: 650; }
.english-name { color: var(--muted); overflow-wrap: anywhere; }
.quote-labels { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 8px; margin-top: 4px; }
.quote-current { text-align: right; }
.quote-current > strong { font-size: 22px; }
.quote-links { display: flex; flex-wrap: wrap; gap: 0 9px; font-size: 12px; }
.quote-current .quote-links { justify-content: flex-end; }
.selection-flags { margin-top: 7px; }
.workbench-card-grid {
  display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 4fr); gap: 10px; margin-top: 9px; align-items: start;
}
.workbench-card-grid > div, .workbench-study { min-width: 0; }
.mini-chart { margin: 0 0 7px; background: #f4f8fa; border: 1px solid var(--border); border-radius: 7px; }
.mini-chart svg { display: block; width: 100%; height: auto; }
.mini-chart text { fill: var(--muted); font-size: 13px; }
.mini-chart .price-band { fill: #dcebf1; }
.mini-chart .price-close { fill: none; stroke: #075975; stroke-width: 2.3; }
.mini-chart .price-ma20 { fill: none; stroke: #6245ac; stroke-width: 1.7; }
.mini-chart .volumes { fill: #8aabbc; }
.mini-chart .guide { fill: none; stroke: currentColor; stroke-width: 1.3; stroke-dasharray: 4 3; }
.mini-chart .guide-label { fill: currentColor; font-weight: 700; font-size: 16px; }
.mini-chart .platform { color: #17694c; }
.mini-chart .trigger { color: #894f02; }
.mini-chart .stop { color: #a6273a; }
.mini-chart figcaption { display: flex; flex-wrap: wrap; gap: 0 10px; padding: 0 8px 5px; font-size: 12px; }
.mini-chart figcaption span::before { content: ""; display: inline-block; width: 9px; height: 4px; margin-right: 4px; background: var(--key); vertical-align: middle; }
.key-band { --key: #b4d2e1; } .key-close { --key: #075975; } .key-ma20 { --key: #6245ac; } .key-vol { --key: #8aabbc; }
.plan-prices small { color: var(--muted); }
.workbench-study .research-stage { display: block; border-radius: 6px; }
.workbench-study meter { display: block; width: min(200px, 100%); height: 10px; accent-color: var(--accent); }
.workbench-study .research-metric { grid-template-areas: "label meter value"; padding: 5px 0; }
.volume-summary { margin-top: 5px; }
.range-position { margin-top: 3px; }
.raw-details { margin-top: 8px; }
.table-scroll { max-width: 100%; overflow-x: auto; margin-top: 7px; overscroll-behavior-inline: contain; }
.table-scroll table { min-width: 680px; }
.sector-table table { min-width: 580px; }
.table-scroll :is(th, td) { vertical-align: middle; }
.table-scroll th[scope=row] small { display: block; font-weight: 500; }
.table-scroll .number { white-space: nowrap; }
.match-toolbar .filter-buttons { display: flex; flex-wrap: wrap; gap: 4px; }
.match-toolbar [aria-pressed=true] { background: #155f7a; border-color: #155f7a; color: #fff; }
.b-candidate-table th button { padding: 2px 0; background: transparent; border: 0; white-space: nowrap; }
.b-candidate-table tbody:nth-of-type(even) { background: #f6f9fb; }
.b-candidate-table tr:target > * { background: #e4f3fa; }
.row-flags { display: flex; flex-wrap: wrap; gap: 2px 4px; margin-top: 3px; }
.row-flags .pill { font-size: 11px; padding: 0 5px; }
.detail-row td { padding-block: 3px; font-size: 13px; }
.detail-row .workbench-card-grid { max-width: min(100%, calc(100vw - 64px)); padding-bottom: 5px; }
.workbench #c-results .rule-group { padding: 3px 0 0; }
.workbench #c-results .watch-card { border-radius: 7px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
@media (max-width: 760px) {
  .workbench .site-header { padding: 12px 13px; }
  .workbench .section-nav { scrollbar-width: thin; }
  .workbench-card-grid { grid-template-columns: minmax(0, 1fr); }
  .breadth-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .style-card { padding: 7px 8px; }
}
@media (max-width: 480px) {
  .core-card { padding: 9px; }
  .style-grid { grid-template-columns: minmax(0, 1fr); }
  .style-card dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mini-chart .guide-label { font-size: 18px; }
  .workbench-study .research-metric { grid-template-areas: "label value" "meter meter"; }
  .quote-current { text-align: left; }
  .quote-current .quote-links { justify-content: flex-start; }
  .workbench .other-results th:first-child { overflow-wrap: anywhere; }
}
"""

SCRIPT = r"""
const nav = [...document.querySelectorAll('.section-nav a')];
const otherMatches = document.querySelector('.b-candidate-table table');
function syncLocation(hash = location.hash, scroll = true) {
  for (const link of nav) link.removeAttribute('aria-current');
  const target = document.getElementById(hash.slice(1));
  const link = nav.find(item => document.getElementById(item.hash.slice(1))?.contains(target)) || nav[0];
  if (link) link.setAttribute('aria-current', 'location');
  if (!target) return;
  for (let node = target; node; node = node.parentElement) {
    if (node.tagName === 'DETAILS') node.open = true;
  }
  if (target.closest('[data-other-entry]')) {
    const entry = target.closest('[data-other-entry]');
    if (entry.hidden) {
      const toolbar = document.querySelector('.match-toolbar');
      toolbar.querySelector('input').value = '';
      toolbar.querySelector('[data-filter="全部"]').click();
    }
    entry.querySelector('.candidate-details').open = true;
  }
  if (scroll) target.scrollIntoView({block: 'start'});
}
for (const input of document.querySelectorAll('.other-results input[type="search"]')) {
  const toolbar = input.closest('.toolbar');
  const rows = [...toolbar.closest('details').querySelectorAll('tbody tr')];
  const count = toolbar.querySelector('output');
  const filter = () => {
    const terms = input.value.trim().toLowerCase().split(/\s+/);
    let visible = 0;
    for (const row of rows) {
      row.hidden = !terms.every(term => row.dataset.search.includes(term));
      if (!row.hidden) visible++;
    }
    count.textContent = visible ? `显示 ${visible.toLocaleString('zh-CN')} 只` : '没有符合搜索条件的股票';
  };
  input.addEventListener('input', filter);
  toolbar.hidden = false;
  filter();
}

if (otherMatches) {
  const entries = [...otherMatches.tBodies];
  const toolbar = document.querySelector('.match-toolbar');
  const input = toolbar.querySelector('input');
  const count = toolbar.querySelector('output');
  const buttons = [...toolbar.querySelectorAll('[data-filter]')];
  let active = buttons[0].dataset.filter;
  const filter = () => {
    const terms = input.value.trim().toLowerCase().split(/\s+/);
    let shown = 0;
    for (const entry of entries) {
      const row = entry.rows[0].dataset;
      const category = active === '全部' || active === row.style || row.flags.includes(active);
      entry.hidden = !category || !terms.every(term => row.search.includes(term));
      shown += !entry.hidden;
    }
    count.textContent = `显示 ${shown} / ${entries.length} 只`;
  };
  for (const button of buttons) {
    button.addEventListener('click', () => {
      active = button.dataset.filter;
      for (const item of buttons) item.setAttribute('aria-pressed', String(item === button));
      filter();
    });
  }
  input.addEventListener('input', filter);
  const sortButtons = [...otherMatches.querySelectorAll('[data-sort]')];
  for (const button of sortButtons) {
    button.addEventListener('click', () => {
      const header = button.parentElement;
      const ascending = header.getAttribute('aria-sort') !== 'ascending';
      for (const item of sortButtons) {
        item.parentElement.removeAttribute('aria-sort');
        item.querySelector('span').textContent = ' ↕';
      }
      header.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
      button.querySelector('span').textContent = ascending ? ' ↑' : ' ↓';
      const attr = 'data-value-' + button.dataset.sort;
      const direction = ascending ? 1 : -1;
      const sorted = [...entries].sort((a, b) => {
        const first = a.rows[0], second = b.rows[0];
        const x = first.getAttribute(attr), y = second.getAttribute(attr);
        if (!x !== !y) return x ? -1 : 1;
        return (Number(x) - Number(y)) * direction || first.id.localeCompare(second.id);
      });
      otherMatches.append(...sorted);
    });
  }
  toolbar.hidden = false;
  filter();
}
addEventListener('hashchange', () => syncLocation());
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (link && !event.defaultPrevented && event.button === 0 &&
      !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) syncLocation(link.hash, false);
});
syncLocation();

const records = new Map([...document.querySelectorAll('script[type="application/json"]')]
  .map(record => [record.dataset.strategy || record.id, record]));
for (const button of document.querySelectorAll('button[data-record]')) {
  button.addEventListener('click', () => {
    const record = records.get(button.dataset.record);
    const url = URL.createObjectURL(new Blob([record.textContent], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = button.dataset.record + '.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  button.hidden = false;
}
"""
