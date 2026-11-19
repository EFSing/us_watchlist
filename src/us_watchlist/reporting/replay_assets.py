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
  font: 16px/1.55 "Times New Roman", SimSun, NSimSun, "Songti SC", "Noto Serif CJK SC", serif;
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

SCRIPT = r"""
const nav = [...document.querySelectorAll('.section-nav a')];
function syncLocation() {
  for (const link of nav) link.removeAttribute('aria-current');
  const target = document.getElementById(location.hash.slice(1));
  const link = nav.find(item => document.getElementById(item.hash.slice(1))?.contains(target)) || nav[0];
  if (link) link.setAttribute('aria-current', 'location');
  if (location.hash === '#audit') document.getElementById('audit').open = true;
}
addEventListener('hashchange', syncLocation);
document.querySelector('a[href="#audit"]').addEventListener('click', () => {
  document.getElementById('audit').open = true;
});
syncLocation();

for (const input of document.querySelectorAll('input[type="search"]')) {
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
